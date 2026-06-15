"""Managed journal recovery service.

Restores a previously recorded environment journal. The recovery flow is
deterministic and only re-applies journal-derived state through registered
controllers. It does not execute journal-provided paths, commands, or values
that bypass the controller protocol.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from arm64_probe.backends.base import HostBackend
from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.environment.journal import JournalStore
from arm64_probe.environment.locking import MutationLock
from arm64_probe.environment.models import (
    EnvironmentJournal,
    JournalFailure,
)
from arm64_probe.errors import ExitCode, ProbeError


class EnvironmentRecovery:
    def __init__(
        self,
        journal_factory: Callable[[], tuple[Path, JournalStore, int, str]],
        observer: Callable[[tuple[str, str]], None] | None = None,
        lock_factory: Callable[[Path, int], MutationLock] | None = None,
    ) -> None:
        self._factory = journal_factory
        self._observer = observer
        self._lock_factory = lock_factory or (
            lambda root, uid: MutationLock(root, required_owner_uid=uid)
        )

    def restore(
        self,
        transaction_id: str,
        backend: HostBackend,
        allow_mutation: bool,
        expected_backend_id: str | None = None,
        expected_repository_id: str = REPOSITORY_ID,
    ) -> EnvironmentJournal:
        if not allow_mutation:
            raise ProbeError(
                ExitCode.MUTATION_AUTHORIZATION,
                "mutation-authorization",
                "restore requires --allow-mutation",
            )

        root, store, required_uid, repository_id = self._factory()
        self._emit(("preflight-managed-path", ""))

        candidate = self._candidate_path(root, store, transaction_id)
        lock = self._lock_factory(root, required_uid)
        with _RecoveryLock(lock, self._observer):
            self._emit(("acquire-lock", ""))
            return self._restore_locked(
                candidate,
                store,
                backend,
                expected_backend_id=expected_backend_id,
                expected_repository_id=expected_repository_id,
            )

    # ----- helpers -------------------------------------------------------

    def _emit(self, event: tuple[str, str]) -> None:
        if self._observer is not None:
            self._observer(event)

    def _restore_locked(
        self,
        candidate: Path,
        store: JournalStore,
        backend: HostBackend,
        *,
        expected_backend_id: str | None,
        expected_repository_id: str,
    ) -> EnvironmentJournal:
        journal: EnvironmentJournal | None = None
        try:
            self._emit(("reread-journal", ""))
            journal = store.read(candidate)
            self._emit(("authoritative-validation", ""))
            self._validate(
                journal,
                expected_backend_id=expected_backend_id or backend.id,
                expected_repository_id=expected_repository_id,
            )
            if journal.state == "restored":
                self._emit(("persist-restored", ""))
                return journal

            controllers = {controller.id: controller for controller in backend.controllers()}

            self._emit(("restore-active-controller-if-present", ""))
            if journal.active_controller is not None:
                self._restore_one(journal, journal.active_controller, controllers)

            self._emit(("restore-applied-controllers-in-reverse", ""))
            for controller_id in reversed(journal.applied):
                if controller_id == journal.active_controller:
                    continue
                self._restore_one(journal, controller_id, controllers)

            self._emit(("verify-restored", ""))
            after_states: list = []
            for controller_id in self._all_restore_targets(journal):
                controller = controllers.get(controller_id)
                if controller is None:
                    continue
                before_state = next(
                    state for state in journal.before if state.controller_id == controller_id
                )
                after_states.append(controller.verify_restored(before_state))

            final = dataclasses.replace(
                journal,
                after=tuple(sorted(after_states, key=lambda state: state.controller_id)),
                applied=(),
                active_controller=None,
                restoration_status="succeeded",
                state="restored",
                failures=(),
                updated_at=self._now(),
            )
            # First transition into restoring, then into restored.
            intermediate = dataclasses.replace(
                journal,
                active_controller=None,
                state="restoring",
                restoration_status="in-progress",
                updated_at=self._now(),
            )
            store.update(intermediate)
            store.update(final)
            self._emit(("persist-restored", ""))
            return final
        except ProbeError as error:
            if journal is not None:
                self._record_failure(store, journal, error)
            raise
        except Exception as error:  # noqa: BLE001
            wrapped = ProbeError(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                f"recovery failed: {error}",
            )
            if journal is not None:
                self._record_failure(store, journal, wrapped)
            raise wrapped from error

    def _record_failure(
        self,
        store: JournalStore,
        journal: EnvironmentJournal,
        error: ProbeError,
    ) -> None:
        try:
            # Move through restoring first to satisfy the journal state graph.
            intermediate = dataclasses.replace(
                journal,
                active_controller=None,
                state="restoring",
                restoration_status="in-progress",
                updated_at=self._now(),
            )
            store.update(intermediate)
            persisted = dataclasses.replace(
                intermediate,
                state="restore-failed",
                restoration_status="failed",
                failures=intermediate.failures
                + (JournalFailure("restore", error.category, error.message),),
                updated_at=self._now(),
            )
            store.update(persisted)
        except ProbeError:
            pass

    def _candidate_path(self, root: Path, store: JournalStore, transaction_id: str) -> Path:
        try:
            return store.validate_managed_path(root / "journals" / f"{transaction_id}.json")
        except ProbeError as error:
            raise ProbeError(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                f"unsafe journal path: {transaction_id}",
                hint="pass a canonical 32-hex transaction id under STATE_ROOT/journals/",
            ) from error

    def _validate(
        self,
        journal: EnvironmentJournal,
        *,
        expected_backend_id: str,
        expected_repository_id: str,
    ) -> None:
        if journal.repository_id != expected_repository_id:
            raise ProbeError(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                "journal repository identity does not match this checkout",
            )
        if journal.backend_id != expected_backend_id:
            raise ProbeError(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                f"journal backend {journal.backend_id} does not match active backend {expected_backend_id}",
            )

    def _restore_one(
        self,
        journal: EnvironmentJournal,
        controller_id: str,
        controllers: dict,
    ) -> None:
        controller = controllers.get(controller_id)
        if controller is None:
            raise ProbeError(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                f"controller {controller_id} is unavailable for restore",
            )
        before_state = next(
            (state for state in journal.before if state.controller_id == controller_id),
            None,
        )
        if before_state is None:
            raise ProbeError(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                f"journal missing before state for {controller_id}",
            )
        controller.restore(before_state)

    def _all_restore_targets(self, journal: EnvironmentJournal) -> tuple[str, ...]:
        targets: list[str] = []
        if journal.active_controller is not None and journal.active_controller not in targets:
            targets.append(journal.active_controller)
        for controller_id in reversed(journal.applied):
            if controller_id not in targets:
                targets.append(controller_id)
        return tuple(targets)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class _RecoveryLock:
    """Acquire the mutation lock and emit a release event on exit."""

    def __init__(
        self,
        lock: MutationLock,
        observer: Callable[[tuple[str, str]], None] | None,
    ) -> None:
        self._lock = lock
        self._observer = observer

    def __enter__(self) -> "_RecoveryLock":
        self._lock.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self._observer is not None:
                self._observer(("release-lock", ""))
        finally:
            self._lock.__exit__(exc_type, exc_value, traceback)


__all__ = ["EnvironmentRecovery"]
