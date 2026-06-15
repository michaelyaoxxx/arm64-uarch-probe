"""Tests for the managed journal recovery service."""

from __future__ import annotations

import dataclasses
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.environment.journal import JournalStore
from arm64_probe.environment.models import (
    ControllerRequest,
    ControllerState,
    EnvironmentJournal,
)
from arm64_probe.environment.recovery import EnvironmentRecovery
from arm64_probe.errors import ExitCode, ProbeError
from tests.support.fake_controllers import FakeBackend, FakeController


FIXED_TIME = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)


class _Harness:
    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "state"
        self.uid = os.getuid()
        self.store = JournalStore(
            self.root,
            repository_id=REPOSITORY_ID,
            required_owner_uid=self.uid,
            clock=lambda: FIXED_TIME,
            transaction_id_factory=lambda: "a" * 32,
        )

    def close(self) -> None:
        self.tmp.cleanup()


def _build_journal(store: JournalStore, *, with_active: bool = True) -> EnvironmentJournal:
    request = ControllerRequest("linux.cpufreq", (("governor", "performance"),))
    before = ControllerState(
        "linux.cpufreq", "available", (("governor", "powersave"),), ()
    )
    journal = store.new("linux-arm64", "gb10", (request,), (before,))
    journal = store.create(journal)
    journal = store.read(journal)
    journal = store.update(
        dataclasses.replace(journal, state="applying", active_controller="linux.cpufreq")
    )
    return store.read(journal)


class RecoveryLifecycleTests(unittest.TestCase):
    def test_unrestored_journal_is_recovered_in_documented_order(self):
        harness = _Harness()
        try:
            controller = FakeController(
                "linux.cpufreq",
                "linux.cpufreq",
                before_values=(("governor", "powersave"),),
                applied_values=(("governor", "performance"),),
            )
            backend = FakeBackend(controllers=(controller,), backend_id="linux-arm64")
            journal = _build_journal(harness.store)

            events: list[tuple[str, str]] = []
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, harness.store, harness.uid, REPOSITORY_ID),
                observer=events.append,
            )
            final = recovery.restore(journal.transaction_id, backend, allow_mutation=True)
        finally:
            harness.close()

        self.assertEqual(
            [event[0] for event in events],
            [
                "preflight-managed-path",
                "acquire-lock",
                "reread-journal",
                "authoritative-validation",
                "restore-active-controller-if-present",
                "restore-applied-controllers-in-reverse",
                "verify-restored",
                "persist-restored",
                "release-lock",
            ],
        )
        self.assertEqual(final.state, "restored")
        self.assertEqual(final.restoration_status, "succeeded")
        self.assertEqual(final.active_controller, None)
        self.assertEqual(controller.events, [("restore", "linux.cpufreq"), ("verify-restored", "linux.cpufreq")])

    def test_already_restored_journal_is_successful_noop(self):
        harness = _Harness()
        try:
            controller = FakeController("linux.cpufreq", "linux.cpufreq")
            backend = FakeBackend(controllers=(controller,), backend_id="linux-arm64")
            journal = _build_journal(harness.store)
            # Walk the journal through restoring -> restored to satisfy the
            # state-transition graph.
            current = harness.store.read(
                harness.root / "journals" / f"{journal.transaction_id}.json"
            )
            for next_state, status in (("restoring", "in-progress"), ("restored", "succeeded")):
                harness.store.update(
                    dataclasses.replace(
                        current,
                        state=next_state,
                        active_controller=None,
                        restoration_status=status,
                        updated_at=FIXED_TIME.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    )
                )
                current = harness.store.read(
                    harness.root / "journals" / f"{journal.transaction_id}.json"
                )

            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, harness.store, harness.uid, REPOSITORY_ID)
            )
            final = recovery.restore(journal.transaction_id, backend, allow_mutation=True)
        finally:
            harness.close()

        self.assertEqual(final.state, "restored")
        self.assertEqual(controller.events, [])

    def test_authorization_required_before_state_changes(self):
        harness = _Harness()
        try:
            controller = FakeController("linux.cpufreq", "linux.cpufreq")
            backend = FakeBackend(controllers=(controller,), backend_id="linux-arm64")
            journal = _build_journal(harness.store)
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, harness.store, harness.uid, REPOSITORY_ID)
            )
            with self.assertRaises(ProbeError) as error:
                recovery.restore(journal.transaction_id, backend, allow_mutation=False)
        finally:
            harness.close()

        self.assertEqual(error.exception.code, ExitCode.MUTATION_AUTHORIZATION)

    def test_backend_mismatch_is_rejected_before_host_writes(self):
        harness = _Harness()
        try:
            controller = FakeController("linux.cpufreq", "linux.cpufreq")
            backend = FakeBackend(controllers=(controller,), backend_id="linux-arm64")
            journal = _build_journal(harness.store)
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, harness.store, harness.uid, REPOSITORY_ID)
            )
            with self.assertRaises(ProbeError) as error:
                recovery.restore(
                    journal.transaction_id, backend, allow_mutation=True, expected_backend_id="other-backend"
                )
        finally:
            harness.close()

        self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_RESTORE)
        self.assertEqual(controller.events, [])

    def test_repository_identity_mismatch_is_rejected(self):
        harness = _Harness()
        try:
            controller = FakeController("linux.cpufreq", "linux.cpufreq")
            backend = FakeBackend(controllers=(controller,), backend_id="linux-arm64")
            journal = _build_journal(harness.store)
            wrong_store = JournalStore(
                harness.root,
                repository_id="different-repository",
                required_owner_uid=harness.uid,
                clock=lambda: FIXED_TIME,
                transaction_id_factory=lambda: "a" * 32,
            )
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, wrong_store, harness.uid, REPOSITORY_ID)
            )
            with self.assertRaises(ProbeError) as error:
                recovery.restore(journal.transaction_id, backend, allow_mutation=True)
        finally:
            harness.close()

        self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_RESTORE)
        self.assertEqual(controller.events, [])

    def test_unsupported_controller_is_rejected(self):
        harness = _Harness()
        try:
            controller = FakeController("linux.cpufreq", "linux.cpufreq")
            backend = FakeBackend(controllers=(), backend_id="linux-arm64")
            journal = _build_journal(harness.store)
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, harness.store, harness.uid, REPOSITORY_ID)
            )
            with self.assertRaises(ProbeError) as error:
                recovery.restore(journal.transaction_id, backend, allow_mutation=True)
        finally:
            harness.close()

        self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_RESTORE)

    def test_journal_path_outside_managed_directory_is_rejected(self):
        harness = _Harness()
        try:
            controller = FakeController("linux.cpufreq", "linux.cpufreq")
            backend = FakeBackend(controllers=(controller,), backend_id="linux-arm64")
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, harness.store, harness.uid, REPOSITORY_ID)
            )
            with self.assertRaises(ProbeError) as error:
                recovery.restore("../../etc/passwd", backend, allow_mutation=True)
        finally:
            harness.close()

        self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_RESTORE)
        self.assertEqual(controller.events, [])

    def test_restore_failure_returns_13_and_preserves_journal(self):
        harness = _Harness()
        try:
            controller = FakeController(
                "linux.cpufreq",
                "linux.cpufreq",
                raise_on_restore=ProbeError(
                    ExitCode.ENVIRONMENT_RESTORE, "restore", "kernel refused"
                ),
            )
            backend = FakeBackend(controllers=(controller,), backend_id="linux-arm64")
            journal = _build_journal(harness.store)
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (harness.root, harness.store, harness.uid, REPOSITORY_ID)
            )
            with self.assertRaises(ProbeError) as error:
                recovery.restore(journal.transaction_id, backend, allow_mutation=True)
            final = harness.store.read(harness.root / "journals" / f"{journal.transaction_id}.json")
        finally:
            harness.close()

        self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_RESTORE)
        self.assertEqual(final.state, "restore-failed")
        self.assertEqual(final.restoration_status, "failed")


if __name__ == "__main__":
    unittest.main()
