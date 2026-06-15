"""Recoverable environment transaction coordinator.

The coordinator owns the host-wide mutation lock, the durable journal, and the
deterministic apply/restore ordering for capability-driven controllers. It is
intentionally platform-independent: it never imports Linux paths, platform
names, or experiment-specific code.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Protocol

from arm64_probe.backends.base import HostBackend, MutationController
from arm64_probe.environment.constants import CONTROLLER_ORDER
from arm64_probe.environment.journal import JournalStore
from arm64_probe.environment.locking import MutationLock
from arm64_probe.environment.models import (
    ControllerRequest,
    ControllerState,
    EnvironmentJournal,
    JournalFailure,
)
from arm64_probe.environment.signals import CommonSignalScope, TransactionInterrupted
from arm64_probe.errors import ExitCode, ProbeError


# Map of capability_id -> controller apply order. Built from CONTROLLER_ORDER
# but expressed as a sequence the coordinator can reuse.
APPLY_ORDER: tuple[str, ...] = CONTROLLER_ORDER


class JournalFactory(Protocol):
    def __call__(self) -> tuple[Path, JournalStore, int, str]: ...


class EnvironmentCoordinator:
    def __init__(
        self,
        journal_factory: JournalFactory,
        signal_scope: CommonSignalScope | None = None,
        observer: Callable[[tuple[str, str]], None] | None = None,
        failure_observer: Callable[[JournalFailure], None] | None = None,
        lock_factory: Callable[[Path, int], MutationLock] | None = None,
    ) -> None:
        self._factory = journal_factory
        self._signal_scope = signal_scope or CommonSignalScope()
        self._observer = observer
        self._failure_observer = failure_observer
        self._lock_factory = lock_factory or (
            lambda root, uid: MutationLock(root, required_owner_uid=uid)
        )

    def execute(
        self,
        backend: HostBackend,
        platform_id: str,
        requests: tuple[ControllerRequest, ...],
        work: Callable[[], object],
        allow_mutation: bool,
    ) -> EnvironmentJournal:
        if not requests:
            work()
            now = self._now()
            return EnvironmentJournal(
                schema_version=1,
                transaction_id="0" * 32,
                repository_id="n/a",
                backend_id=backend.id,
                platform_id=platform_id,
                state="restored",
                created_at=now,
                updated_at=now,
                requested=(),
                before=(),
                applied=(),
                active_controller=None,
                effective=(),
                after=(),
                restoration_status="not-applicable",
                failures=(),
            )

        if not allow_mutation:
            raise ProbeError(
                ExitCode.MUTATION_AUTHORIZATION,
                "mutation-authorization",
                "transaction requires --allow-mutation",
            )

        root, store, required_uid, repository_id = self._factory()
        lock = self._lock_factory(root, required_uid)
        observer = self._observer
        with _LockContext(lock, observer):
            self._emit(("rediscover-journals", ""))
            unfinished = store.unfinished()
            if unfinished:
                raise ProbeError(
                    ExitCode.ENVIRONMENT_BUSY,
                    "environment-busy",
                    "unfinished journal blocks new transaction",
                    (
                        ("transaction", unfinished[0].transaction_id),
                        ("state", unfinished[0].state),
                    ),
                )

            controllers = {controller.id: controller for controller in backend.controllers()}
            ordered_requests = self._order_requests(requests, controllers)

            inspected = self._inspect_controllers(ordered_requests, controllers)
            self._validate_controllers(ordered_requests, controllers)
            self._preflight_writable(controllers, ordered_requests)

            journal = store.new(backend.id, platform_id, ordered_requests, inspected)
            self._emit(("journal:created", ""))
            journal_path = store.create(journal)
            journal = store.read(journal_path)

            applied: list[str] = []
            effective: list[ControllerState] = []
            failures: list[JournalFailure] = []
            original_failure: ProbeError | None = None

            for request in ordered_requests:
                controller = controllers[request.controller_id]
                journal, transitioned = self._set_active(
                    store, journal, request.controller_id, journal_path
                )
                if transitioned:
                    self._emit(("journal:applying", ""))
                self._emit(("journal:active", request.controller_id))
                try:
                    controller.apply(request)
                except ProbeError as error:
                    self._record_failure(failures, "apply", error)
                    original_failure = original_failure or error
                    break
                except Exception as error:  # noqa: BLE001
                    wrapped = ProbeError(
                        ExitCode.ENVIRONMENT_APPLY,
                        "apply",
                        str(error) or type(error).__name__,
                    )
                    self._record_failure(failures, "apply", wrapped)
                    original_failure = original_failure or wrapped
                    break
                self._emit(("apply", request.controller_id))
                applied.append(request.controller_id)
                journal = self._mark_applied(store, journal, request.controller_id, journal_path)
                self._emit(("journal:applied", request.controller_id))

            for request in ordered_requests:
                if request.controller_id not in applied:
                    continue
                controller = controllers[request.controller_id]
                effective.append(self._verify_controller(controller, request))

            # Capture the most recent active controller before any subsequent
            # state transitions clear it.
            pending_active = journal.active_controller
            journal = self._persist_state(store, journal, "prepared", journal_path)
            self._emit(("journal:prepared", ""))

            interrupted: TransactionInterrupted | None = None
            try:
                with self._signal_scope:
                    if original_failure is None:
                        try:
                            work()
                        except TransactionInterrupted:
                            raise
                        except ProbeError as error:
                            self._record_failure(failures, "work", error)
                            original_failure = original_failure or error
                        except Exception as error:  # noqa: BLE001
                            wrapped = ProbeError(
                                ExitCode.ENVIRONMENT_APPLY,
                                "work",
                                str(error) or type(error).__name__,
                            )
                            self._record_failure(failures, "work", wrapped)
                            original_failure = original_failure or wrapped
            except TransactionInterrupted as signal_error:
                self._record_failure(
                    failures,
                    "signal",
                    ProbeError(
                        ExitCode.ENVIRONMENT_APPLY,
                        "signal",
                        f"received signal {signal_error.signum}",
                    ),
                )
                interrupted = signal_error

            journal = self._persist_state(store, journal, "restoring", journal_path)
            self._emit(("journal:restoring", ""))
            restoration_failure: ProbeError | None = None

            # Recover any active_controller recorded before the failure.
            restore_ids: list[str] = []
            if pending_active is not None and pending_active not in restore_ids:
                restore_ids.append(pending_active)
            for controller_id in reversed(applied):
                if controller_id not in restore_ids:
                    restore_ids.append(controller_id)

            after_states: list[ControllerState] = []
            restore_errors: dict[str, ProbeError] = {}
            for controller_id in restore_ids:
                controller = controllers.get(controller_id)
                if controller is None:
                    continue
                before_state = next(state for state in journal.before if state.controller_id == controller_id)
                try:
                    controller.restore(before_state)
                    self._emit(("restore", controller_id))
                except ProbeError as error:
                    self._record_failure(failures, "restore", error)
                    restoration_failure = restoration_failure or error
                    restore_errors[controller_id] = error
                except Exception as error:  # noqa: BLE001
                    wrapped = ProbeError(
                        ExitCode.ENVIRONMENT_RESTORE,
                        "restore",
                        str(error) or type(error).__name__,
                    )
                    self._record_failure(failures, "restore", wrapped)
                    restoration_failure = restoration_failure or wrapped
                    restore_errors[controller_id] = wrapped

            for controller_id in restore_ids:
                if controller_id in restore_errors:
                    continue
                controller = controllers.get(controller_id)
                if controller is None:
                    continue
                before_state = next(state for state in journal.before if state.controller_id == controller_id)
                verified = controller.verify_restored(before_state)
                self._emit(("verify-restored", controller_id))
                after_states.append(verified)

            restoration_status = "failed" if restoration_failure else "succeeded"
            journal = dataclasses.replace(
                journal,
                after=tuple(sorted(after_states, key=lambda state: state.controller_id)),
                effective=tuple(sorted(effective, key=lambda state: state.controller_id)),
                applied=tuple(applied),
                active_controller=None,
                restoration_status=restoration_status,
                failures=tuple(failures),
                state="restored" if not restoration_failure else "restore-failed",
                updated_at=self._now(),
            )
            store.update(journal)
            self._emit(("journal:restored", ""))
            if self._observer is not None:
                self._observer(("unlock", "release"))

        if restoration_failure is not None:
            raise restoration_failure
        if interrupted is not None and original_failure is None:
            raise ProbeError(
                ExitCode.ENVIRONMENT_APPLY,
                "signal",
                f"transaction interrupted by signal {interrupted.signum}",
            )
        if original_failure is not None:
            raise original_failure
        return journal

    # ----- helpers -------------------------------------------------------

    def _emit(self, event: tuple[str, str]) -> None:
        if self._observer is not None:
            self._observer(event)

    def _record_failure(self, failures: list[JournalFailure], stage: str, error: ProbeError) -> None:
        failure = JournalFailure(stage, error.category, error.message)
        failures.append(failure)
        if self._failure_observer is not None:
            self._failure_observer(failure)

    def _order_requests(
        self,
        requests: tuple[ControllerRequest, ...],
        controllers: dict[str, MutationController],
    ) -> tuple[ControllerRequest, ...]:
        order = {controller_id: index for index, controller_id in enumerate(APPLY_ORDER)}
        seen: set[str] = set()
        result: list[ControllerRequest] = []
        for request in requests:
            if request.controller_id not in controllers:
                raise ProbeError(
                    ExitCode.CONFIG,
                    "configuration",
                    f"controller {request.controller_id} is not available on backend",
                )
            if request.controller_id in seen:
                raise ProbeError(
                    ExitCode.CONFIG,
                    "configuration",
                    f"duplicate controller request: {request.controller_id}",
                )
            seen.add(request.controller_id)
            if request.controller_id not in order:
                raise ProbeError(
                    ExitCode.CONFIG,
                    "configuration",
                    f"unsupported controller order: {request.controller_id}",
                )
            result.append(request)
        return tuple(sorted(result, key=lambda item: order[item.controller_id]))

    def _inspect_controllers(
        self,
        requests: tuple[ControllerRequest, ...],
        controllers: dict[str, MutationController],
    ) -> tuple[ControllerState, ...]:
        states: list[ControllerState] = []
        for request in requests:
            controller = controllers[request.controller_id]
            self._emit(("inspect", request.controller_id))
            states.append(controller.inspect())
        return tuple(states)

    def _validate_controllers(
        self,
        requests: tuple[ControllerRequest, ...],
        controllers: dict[str, MutationController],
    ) -> None:
        for request in requests:
            controller = controllers[request.controller_id]
            self._emit(("validate", request.controller_id))
            try:
                controller.validate_request(request)
            except ProbeError:
                raise
            except Exception as error:  # noqa: BLE001
                raise ProbeError(
                    ExitCode.HOST_INSPECTION,
                    "host-inspection",
                    f"controller {request.controller_id} rejected request: {error}",
                ) from error

    def _verify_controller(
        self,
        controller: MutationController,
        request: ControllerRequest,
    ) -> ControllerState:
        self._emit(("verify", request.controller_id))
        return controller.verify(request)

    def _preflight_writable(
        self,
        controllers: dict[str, MutationController],
        requests: tuple[ControllerRequest, ...],
    ) -> None:
        # Capability-driven preflight: required controllers must be available
        # and not degraded/permission-denied. Per-controller permission checks
        # are implemented in the controller's apply/validate methods.
        for request in requests:
            controller = controllers[request.controller_id]
            state = controller.inspect()
            if state.status not in {"available"}:
                raise ProbeError(
                    ExitCode.HOST_INSPECTION,
                    "host-inspection",
                    f"controller {request.controller_id} is {state.status}",
                )

    def _set_active(
        self,
        store: JournalStore,
        journal: EnvironmentJournal,
        controller_id: str,
        journal_path: Path,
    ) -> tuple[EnvironmentJournal, bool]:
        transitioned = False
        if journal.state == "created":
            pending = dataclasses.replace(journal, state="applying")
            store.update(pending)
            journal = store.read(journal_path)
            transitioned = True
        next_journal = dataclasses.replace(
            journal,
            active_controller=controller_id,
            updated_at=self._now(),
        )
        store.update(next_journal)
        return store.read(journal_path), transitioned

    def _mark_applied(
        self,
        store: JournalStore,
        journal: EnvironmentJournal,
        controller_id: str,
        journal_path: Path,
    ) -> EnvironmentJournal:
        next_journal = dataclasses.replace(
            journal,
            applied=journal.applied + (controller_id,),
            active_controller=None,
            updated_at=self._now(),
        )
        store.update(next_journal)
        return store.read(journal_path)

    def _persist_state(
        self,
        store: JournalStore,
        journal: EnvironmentJournal,
        state: str,
        journal_path: Path,
    ) -> EnvironmentJournal:
        next_journal = dataclasses.replace(
            journal,
            state=state,
            active_controller=None,
            updated_at=self._now(),
        )
        store.update(next_journal)
        return store.read(journal_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class _LockContext:
    """Acquires the lock and emits acquire/release events to an observer."""

    def __init__(
        self,
        lock: MutationLock,
        observer: Callable[[tuple[str, str]], None] | None,
    ) -> None:
        self._lock = lock
        self._observer = observer

    def __enter__(self) -> "_LockContext":
        self._lock.__enter__()
        if self._observer is not None:
            self._observer(("lock", "acquire"))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._lock.__exit__(exc_type, exc_value, traceback)


def default_journal_factory(
    root: Path, store: JournalStore, required_owner_uid: int, repository_id: str
) -> tuple[Path, JournalStore, int, str]:
    return root, store, required_owner_uid, repository_id


__all__ = [
    "APPLY_ORDER",
    "EnvironmentCoordinator",
    "JournalFactory",
    "TransactionInterrupted",
    "default_journal_factory",
]
