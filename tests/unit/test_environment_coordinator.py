"""Lifecycle and fault-injection tests for the environment transaction coordinator."""

from __future__ import annotations

import dataclasses
import os
import tempfile
import threading
import unittest
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.environment.coordinator import (
    EnvironmentCoordinator,
    TransactionInterrupted,
)
from arm64_probe.environment.journal import JournalStore
from arm64_probe.environment.models import (
    ControllerRequest,
    ControllerState,
    EnvironmentJournal,
    JournalFailure,
)
from arm64_probe.environment.signals import CommonSignalScope
from arm64_probe.errors import ExitCode, ProbeError
from tests.support.fake_controllers import FakeBackend, FakeController


FIXED_TIME = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)


def _fixed_clock() -> datetime:
    return FIXED_TIME


def _fixed_transaction_id() -> str:
    return "a" * 32


class _Harness:
    """Bundle common coordinator test dependencies."""

    def __init__(self, *, request_status: str = "available") -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "state"
        self.uid = os.getuid()
        self.store = JournalStore(
            self.root,
            repository_id=REPOSITORY_ID,
            required_owner_uid=self.uid,
            clock=_fixed_clock,
            transaction_id_factory=_fixed_transaction_id,
        )
        self.controller_a = FakeController(
            "linux.cpufreq",
            "linux.cpufreq",
            inspect_status=request_status,
            before_values=(("governor", "powersave"),),
            applied_values=(("governor", "performance"),),
        )
        self.controller_b = FakeController(
            "linux.hugepage",
            "linux.hugepage",
            inspect_status=request_status,
            before_values=(("count", 0),),
            applied_values=(("count", 4),),
        )
        self.backend = FakeBackend(controllers=(self.controller_a, self.controller_b))
        self.signal_scope = CommonSignalScope()
        self.events: list[tuple[str, str]] = []
        self.observed_failures: list[JournalFailure] = []
        self.coordinator = EnvironmentCoordinator(
            journal_factory=self._factory,
            signal_scope=self.signal_scope,
            observer=self.events.append,
            failure_observer=self.observed_failures.append,
        )

    def _factory(self) -> tuple[Path, JournalStore, int, str]:
        return self.root, self.store, self.uid, REPOSITORY_ID

    def close(self) -> None:
        self.tmp.cleanup()

    def request_a(self) -> ControllerRequest:
        return ControllerRequest("linux.cpufreq", (("governor", "performance"),))

    def request_b(self) -> ControllerRequest:
        return ControllerRequest("linux.hugepage", (("count", 4),))

    def work(self) -> str:
        self.events.append(("work", ""))
        return "done"


class CoordinatorLifecycleTests(unittest.TestCase):
    EXPECTED_EVENTS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("lock", "acquire"),
        ("rediscover-journals", ""),
        ("inspect", "linux.cpufreq"),
        ("inspect", "linux.hugepage"),
        ("validate", "linux.cpufreq"),
        ("validate", "linux.hugepage"),
        ("journal:created", ""),
        ("journal:applying", ""),
        ("journal:active", "linux.cpufreq"),
        ("apply", "linux.cpufreq"),
        ("journal:applied", "linux.cpufreq"),
        ("journal:active", "linux.hugepage"),
        ("apply", "linux.hugepage"),
        ("journal:applied", "linux.hugepage"),
        ("verify", "linux.cpufreq"),
        ("verify", "linux.hugepage"),
        ("journal:prepared", ""),
        ("work", ""),
        ("journal:restoring", ""),
        ("restore", "linux.hugepage"),
        ("restore", "linux.cpufreq"),
        ("verify-restored", "linux.hugepage"),
        ("verify-restored", "linux.cpufreq"),
        ("journal:restored", ""),
        ("unlock", "release"),
    )

    def test_full_lifecycle_records_events_and_finalizes_journal(self):
        harness = _Harness()
        try:
            journal = harness.coordinator.execute(
                backend=harness.backend,
                platform_id="gb10",
                requests=(harness.request_a(), harness.request_b()),
                work=harness.work,
                allow_mutation=True,
            )
            self.assertEqual(harness.events, list(self.EXPECTED_EVENTS))
            self.assertEqual(journal.state, "restored")
            self.assertEqual(journal.applied, ("linux.cpufreq", "linux.hugepage"))
            self.assertEqual(journal.active_controller, None)
            self.assertEqual(journal.restoration_status, "succeeded")
            self.assertEqual(journal.failures, ())
        finally:
            harness.close()

    def test_no_authorization_blocks_before_lock_or_journal(self):
        harness = _Harness()
        try:
            with self.assertRaises(ProbeError) as error:
                harness.coordinator.execute(
                    backend=harness.backend,
                    platform_id="gb10",
                    requests=(harness.request_a(),),
                    work=lambda: None,
                    allow_mutation=False,
                )
            self.assertEqual(error.exception.code, ExitCode.MUTATION_AUTHORIZATION)
            self.assertEqual(harness.events, [])
            self.assertEqual(harness.store.unfinished(), ())
        finally:
            harness.close()

    def test_unfinished_journal_blocks_new_transaction(self):
        harness = _Harness()
        try:
            blocker = harness.store.create(
                harness.store.new(
                    "fake-backend",
                    "gb10",
                    (harness.request_a(),),
                    (
                        ControllerState(
                            "linux.cpufreq",
                            "available",
                            (("governor", "powersave"),),
                            (),
                        ),
                    ),
                )
            )
            with self.assertRaises(ProbeError) as error:
                harness.coordinator.execute(
                    backend=harness.backend,
                    platform_id="gb10",
                    requests=(harness.request_a(),),
                    work=lambda: None,
                    allow_mutation=True,
                )
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_BUSY)
            self.assertEqual(
                harness.events,
                [("lock", "acquire"), ("rediscover-journals", "")],
            )
            self.assertEqual(
                harness.store.unfinished()[0].transaction_id,
                blocker.name.removesuffix(".json"),
            )
        finally:
            harness.close()


class CoordinatorFaultInjectionTests(unittest.TestCase):
    def test_apply_failure_restores_in_reverse_and_records_original(self):
        harness = _Harness()
        try:
            harness.controller_b.raise_on_apply = ProbeError(
                ExitCode.ENVIRONMENT_APPLY, "apply", "kernel rejection"
            )
            with self.assertRaises(ProbeError) as error:
                harness.coordinator.execute(
                    backend=harness.backend,
                    platform_id="gb10",
                    requests=(harness.request_a(), harness.request_b()),
                    work=lambda: None,
                    allow_mutation=True,
                )
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)
            self.assertEqual(error.exception.message, "kernel rejection")
            self.assertEqual(harness.observed_failures[0].category, "apply")

            final = harness.store.read(harness.root / "journals" / (("a" * 32) + ".json"))
            self.assertEqual(final.state, "restored")
            self.assertEqual(final.applied, ("linux.cpufreq",))
            self.assertEqual(final.restoration_status, "succeeded")
            restore_sequence = [event for event in harness.controller_b.events if event[0] == "restore"]
            restore_sequence_a = [event for event in harness.controller_a.events if event[0] == "restore"]
            self.assertEqual(restore_sequence, [("restore", "linux.hugepage")])
            self.assertEqual(restore_sequence_a, [("restore", "linux.cpufreq")])
        finally:
            harness.close()

    def test_active_controller_is_restored_first_even_when_apply_fails(self):
        harness = _Harness()
        try:
            harness.controller_a.raise_on_apply = ProbeError(
                ExitCode.ENVIRONMENT_APPLY, "apply", "interrupted mid-apply"
            )
            with self.assertRaises(ProbeError):
                harness.coordinator.execute(
                    backend=harness.backend,
                    platform_id="gb10",
                    requests=(harness.request_a(), harness.request_b()),
                    work=lambda: None,
                    allow_mutation=True,
                )
            self.assertEqual(
                harness.controller_a.events,
                [
                    ("validate", "linux.cpufreq"),
                    ("apply", "linux.cpufreq"),
                    ("restore", "linux.cpufreq"),
                    ("verify-restored", "linux.cpufreq"),
                ],
            )
            self.assertEqual(harness.controller_b.events, [("validate", "linux.hugepage")])
            final = harness.store.read(harness.root / "journals" / (("a" * 32) + ".json"))
            self.assertEqual(final.active_controller, None)
            self.assertEqual(final.applied, ())
            self.assertEqual(final.restoration_status, "succeeded")
        finally:
            harness.close()

    def test_restore_failure_returns_13_and_preserves_original_failure(self):
        harness = _Harness()
        try:
            harness.controller_b.raise_on_apply = ProbeError(
                ExitCode.ENVIRONMENT_APPLY, "apply", "kernel rejection"
            )
            harness.controller_a.raise_on_restore = ProbeError(
                ExitCode.ENVIRONMENT_RESTORE, "restore", "still busy"
            )
            with self.assertRaises(ProbeError) as error:
                harness.coordinator.execute(
                    backend=harness.backend,
                    platform_id="gb10",
                    requests=(harness.request_a(), harness.request_b()),
                    work=lambda: None,
                    allow_mutation=True,
                )
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_RESTORE)
            self.assertEqual(error.exception.message, "still busy")
            categories = [failure.category for failure in harness.observed_failures]
            self.assertIn("apply", categories)
            self.assertIn("restore", categories)
            final = harness.store.read(harness.root / "journals" / (("a" * 32) + ".json"))
            self.assertEqual(final.state, "restore-failed")
            self.assertEqual(final.restoration_status, "failed")
        finally:
            harness.close()

    def test_unsupported_required_capability_fails_before_journal_creation(self):
        harness = _Harness(request_status="unsupported")
        try:
            with self.assertRaises(ProbeError) as error:
                harness.coordinator.execute(
                    backend=harness.backend,
                    platform_id="gb10",
                    requests=(harness.request_a(),),
                    work=lambda: None,
                    allow_mutation=True,
                )
            self.assertEqual(error.exception.code, ExitCode.HOST_INSPECTION)
            self.assertEqual(harness.store.unfinished(), ())
        finally:
            harness.close()

    def test_work_failure_restores_and_reports_apply_exit_code_12(self):
        harness = _Harness()
        try:
            def failing_work() -> None:
                raise ProbeError(ExitCode.ENVIRONMENT_APPLY, "work", "user failure")

            with self.assertRaises(ProbeError) as error:
                harness.coordinator.execute(
                    backend=harness.backend,
                    platform_id="gb10",
                    requests=(harness.request_a(), harness.request_b()),
                    work=failing_work,
                    allow_mutation=True,
                )
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)
            self.assertEqual(error.exception.message, "user failure")
            final = harness.store.read(harness.root / "journals" / (("a" * 32) + ".json"))
            self.assertEqual(final.state, "restored")
            self.assertEqual(final.applied, ("linux.cpufreq", "linux.hugepage"))
        finally:
            harness.close()

    def test_no_controllers_runs_work_without_state_or_authorization(self):
        harness = _Harness()
        try:
            journal = harness.coordinator.execute(
                backend=harness.backend,
                platform_id="gb10",
                requests=(),
                work=lambda: harness.events.append(("work", "free")),
                allow_mutation=False,
            )
            self.assertEqual(harness.events, [("work", "free")])
            self.assertEqual(journal.state, "restored")
            self.assertEqual(journal.applied, ())
            self.assertEqual(journal.restoration_status, "not-applicable")
        finally:
            harness.close()


class CoordinatorSourceBoundaryTests(unittest.TestCase):
    def test_coordinator_source_has_no_linux_path_or_platform_branch(self):
        from pathlib import Path as _Path

        text = _Path(__file__).resolve().parents[2].joinpath("arm64_probe", "environment", "coordinator.py").read_text()
        for forbidden in ("/sys/", "/proc/", "gb10", "m4", "arm64_probe.experiments", "arm64_probe.backends.linux"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, text)


class CommonSignalScopeTests(unittest.TestCase):
    def test_scope_refuses_reentry_on_main_thread(self):
        scope = CommonSignalScope(signals=())
        scope.__enter__()
        try:
            with self.assertRaises(RuntimeError):
                scope.__enter__()
        finally:
            scope.__exit__(None, None, None)

    def test_scope_refuses_non_main_thread(self):
        import threading as _threading

        scope = CommonSignalScope()
        result: list[Exception] = []

        def worker() -> None:
            try:
                scope.__enter__()
            except RuntimeError as error:
                result.append(error)
            except Exception as error:  # noqa: BLE001
                result.append(error)

        thread = _threading.Thread(target=worker)
        thread.start()
        thread.join(2.0)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], RuntimeError)

    def test_interrupt_raises_inside_scope_on_main_thread(self):
        scope = CommonSignalScope(signals=(2,))  # SIGINT
        with self.assertRaises(TransactionInterrupted):
            with scope:
                scope.raise_for_test(2)


if __name__ == "__main__":
    unittest.main()
