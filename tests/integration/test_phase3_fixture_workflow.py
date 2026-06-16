"""Fixture workflow: Runner + FakeBackend + FakeAdapter for probe run."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from arm64_probe.domain.models import (
    Case,
    Plan,
    ResolvedValue,
    RunResult,
)
from arm64_probe.environment.coordinator import EnvironmentCoordinator
from arm64_probe.execution.adapters.chase_pmu import ChasePmuAdapter
from arm64_probe.execution.result_store import ResultStore
from arm64_probe.execution.runner import Runner


class Phase3FixtureWorkflowTests(unittest.TestCase):
    """Runner against fake backend produces valid RunResult for smoke profile."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.result_store = ResultStore(self.results_dir)
        self.coordinator = MagicMock(spec=EnvironmentCoordinator)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fixture_workflow_with_environment_phase(self):
        """Runner should execute cases through coordinator with phases."""
        from arm64_probe.domain.models import EnvironmentPhase, EnvironmentRequirement

        case = Case(
            id="cache-latency.l1-latency@gb10.x925.c0.32kib.default",
            scenario_id="cache-latency.l1-latency",
            platform_id="gb10",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("working-set", ResolvedValue("32KB", "platform-default")),
                ("samples", ResolvedValue(7, "platform-default")),
            ),
            execution_requirements=(
                EnvironmentRequirement(
                    "cpu-frequency",
                    "linux.cpufreq",
                    "host",
                    (("governor", "performance"),),
                    mutation=True,
                    requires_privilege=True,
                ),
            ),
        )
        phase = EnvironmentPhase(
            id="phase-1",
            case_ids=(case.id,),
            host_requirements=case.execution_requirements,
        )
        plan = Plan(
            platform_id="gb10",
            profile_id="smoke",
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(phase,),
            skip_unavailable=False,
        )

        executor = _RecordingExecutor(
            stdout="""=== chase_pmu v2.7.3 ===
size=32 KB  n_lines=512  warm=5  meas_rounds=50  seed=42  hugepage=0
Warming 5 pass(es)...
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
""")

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters={"chase_pmu": ChasePmuAdapter()},
            command_executor=executor,
        )

        # Capture coordinator calls
        coordinator_calls = []

        def execute_work(**kwargs):
            coordinator_calls.append(kwargs)
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        result = runner.run(plan, allow_mutation=True)

        # Coordinator should have been called
        self.assertTrue(coordinator_calls, "Coordinator was not called")
        self.assertIsInstance(result, RunResult)

    def test_fixture_workflow_without_mutation(self):
        """Runner without environment phases should not call coordinator."""
        case = Case(
            id="test-case-1",
            scenario_id="cache-latency.l1-latency",
            platform_id="gb10",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("working-set", ResolvedValue("32KB", "platform-default")),
            ),
        )
        plan = Plan(
            platform_id="gb10",
            profile_id="smoke",
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters={"chase_pmu": ChasePmuAdapter()},
            command_executor=_RecordingExecutor(
                stdout="""=== chase_pmu v2.7.3 ===
size=32 KB  n_lines=512  warm=5  meas_rounds=50  seed=42  hugepage=0
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
"""),
        )

        self.coordinator.execute.side_effect = RuntimeError("should not be called")
        result = runner.run(plan, allow_mutation=False)

        self.assertIsInstance(result, RunResult)
        self.assertEqual(len(result.samples), 1)


class _RecordingExecutor:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.calls = []
        self._stdout = stdout
        self._stderr = stderr
        self._returncode = returncode

    def execute(self, command, cwd=None, timeout=None):
        self.calls.append((tuple(command), timeout))
        return self._returncode, self._stdout, self._stderr


if __name__ == "__main__":
    unittest.main()
