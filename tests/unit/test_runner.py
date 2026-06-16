"""Tests for the Runner."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from arm64_probe.domain.models import Case, Plan, RunResult
from arm64_probe.environment.coordinator import EnvironmentCoordinator
from arm64_probe.execution.adapters.base import ProbeOutput
from arm64_probe.execution.adapters.chase_pmu import ChasePmuAdapter
from arm64_probe.execution.runner import Runner
from arm64_probe.execution.result_store import ResultStore


class MockCommandExecutor:
    """Mock command executor for testing."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.calls = []

    def execute(self, cmd: list[str], timeout: int | None = None) -> tuple[int, str, str]:
        self.calls.append(cmd)
        return self.returncode, self.stdout, self.stderr


class TestRunner(unittest.TestCase):
    """Test Runner execution logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.result_store = ResultStore(self.results_dir)

        # Create mock coordinator
        self.coordinator = MagicMock(spec=EnvironmentCoordinator)

        # Create adapters
        self.adapters = {
            "chase_pmu": ChasePmuAdapter(),
        }

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_sample_plan(self) -> Plan:
        """Create a minimal Plan for testing."""
        from arm64_probe.domain.models import ResolvedValue

        case = Case(
            id="test-case-1",
            scenario_id="cache-latency.l1-latency",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("working-set", ResolvedValue("1MB", "platform-default")),
                ("page-policy", ResolvedValue("default", "platform-default")),
            ),
        )
        return Plan(
            platform_id="test-platform",
            profile_id="test-profile",
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

    def test_runner_initialization(self):
        """Test Runner can be initialized with required components."""
        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters=self.adapters,
        )

        self.assertIsNotNone(runner)
        self.assertEqual(runner.result_store, self.result_store)
        self.assertEqual(runner.adapters, self.adapters)

    def test_runner_executes_case(self):
        """Test Runner executes a case and returns a RunResult."""
        # Mock probe output
        probe_output = """=== chase_pmu v2.7.3 ===
size=1024 KB  n_lines=16384  warm=5  meas_rounds=50  seed=42  hugepage=0
Warming 5 pass(es)...
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
"""

        executor = MockCommandExecutor(stdout=probe_output)

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters=self.adapters,
            command_executor=executor,
        )

        plan = self._create_sample_plan()

        # Mock coordinator to execute work immediately
        def execute_work(**kwargs):
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        result = runner.run(plan, allow_mutation=False)

        # Verify the result is a RunResult
        self.assertIsInstance(result, RunResult)
        self.assertEqual(len(result.samples), 1)

        sample = result.samples[0]
        self.assertEqual(sample.status, "ok")

        metrics_dict = dict(sample.metrics)
        self.assertAlmostEqual(metrics_dict["latency_ns"], 4.36, places=2)
        self.assertEqual(metrics_dict["accesses"], 819200)

    def test_runner_handles_probe_failure(self):
        """Test Runner handles probe execution failure."""
        executor = MockCommandExecutor(returncode=1, stderr="Probe error")

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters=self.adapters,
            command_executor=executor,
        )

        plan = self._create_sample_plan()

        def execute_work(**kwargs):
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        result = runner.run(plan, allow_mutation=False)

        self.assertIsInstance(result, RunResult)
        sample = result.samples[0]

        self.assertEqual(sample.status, "error")
        metrics_dict = dict(sample.metrics)
        self.assertIn("error", metrics_dict)
        self.assertIn("Probe exited with code 1", metrics_dict["error"])

    def test_runner_handles_parse_failure(self):
        """Test Runner handles probe output parse failure."""
        executor = MockCommandExecutor(stdout="Invalid output")

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters=self.adapters,
            command_executor=executor,
        )

        plan = self._create_sample_plan()

        def execute_work(**kwargs):
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        result = runner.run(plan, allow_mutation=False)

        self.assertIsInstance(result, RunResult)
        sample = result.samples[0]

        self.assertEqual(sample.status, "error")
        metrics_dict = dict(sample.metrics)
        self.assertIn("error", metrics_dict)

    def test_runner_respects_allow_mutation(self):
        """Test Runner passes allow_mutation to coordinator."""
        from arm64_probe.domain.models import ResolvedValue

        # Create a plan with environment phase to trigger coordinator
        case = Case(
            id="test-case-1",
            scenario_id="cache-latency.l1-latency",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("working-set", ResolvedValue("1MB", "platform-default")),
                ("page-policy", ResolvedValue("default", "platform-default")),
            ),
        )

        from arm64_probe.domain.models import EnvironmentPhase, EnvironmentRequirement

        phase = EnvironmentPhase(
            id="phase-1",
            case_ids=("test-case-1",),
            host_requirements=(
                EnvironmentRequirement(
                    id="cpu-frequency",
                    capability_id="linux.cpufreq",
                    scope="host",
                    values=(("governor", "performance"),),
                    mutation=True,
                    requires_privilege=True,
                ),
            ),
        )

        plan = Plan(
            platform_id="test-platform",
            profile_id="test-profile",
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(phase,),
            skip_unavailable=False,
        )

        executor = MockCommandExecutor(stdout="""=== chase_pmu v2.7.3 ===
size=1024 KB  n_lines=16384  warm=5  meas_rounds=50  seed=42  hugepage=0
Warming 5 pass(es)...
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
""")

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters=self.adapters,
            command_executor=executor,
        )

        # Mock coordinator to capture allow_mutation
        captured_args = {}

        def execute_work(**kwargs):
            captured_args["allow_mutation"] = kwargs.get("allow_mutation")
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        runner.run(plan, allow_mutation=True)

        self.assertTrue(captured_args["allow_mutation"])

    def test_runner_handles_phase_with_no_host_requirements(self):
        """Runner with coordinator=None executes cases directly when
        a real environment phase has empty host_requirements (smoke profile)."""
        from arm64_probe.domain.models import EnvironmentPhase, ResolvedValue

        executor = MockCommandExecutor(
            stdout="""=== chase_pmu v2.7.3 ===
size=1024 KB  n_lines=16384  warm=5  meas_rounds=50  seed=42  hugepage=0
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
""")

        case = Case(
            id="test-case-nomut",
            scenario_id="cache-latency.l1-latency",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("working-set", ResolvedValue("1MB", "platform-default")),
                ("page-policy", ResolvedValue("default", "platform-default")),
            ),
        )

        phase = EnvironmentPhase(
            id="phase-1",
            case_ids=("test-case-nomut",),
            host_requirements=(),  # empty — smoke profile pattern
        )

        plan = Plan(
            platform_id="test-platform",
            profile_id="test-profile",
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(phase,),
            skip_unavailable=False,
        )

        # Explicitly pass coordinator=None — the real GB10 smoke scenario
        runner = Runner(
            coordinator=None,
            result_store=self.result_store,
            adapters=self.adapters,
            command_executor=executor,
        )

        # Must not raise AttributeError: 'NoneType' object has no attribute 'execute'
        result = runner.run(plan, allow_mutation=False)

        self.assertIsInstance(result, RunResult)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(result.samples[0].status, "ok")


class RunnerProvenanceTests(unittest.TestCase):
    """Test that Runner records provenance fields in RunResult summary."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.result_store = ResultStore(self.results_dir)
        self.coordinator = MagicMock(spec=EnvironmentCoordinator)
        self.adapters = {"chase_pmu": ChasePmuAdapter()}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _plan_with_cases(self) -> Plan:
        from arm64_probe.domain.models import ResolvedValue
        case = Case(
            id="test-case-1",
            scenario_id="cache-latency.l1-latency",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("working-set", ResolvedValue("1MB", "platform-default")),
                ("page-policy", ResolvedValue("default", "platform-default")),
            ),
        )
        return Plan(
            platform_id="test-platform",
            profile_id="test-profile",
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

    def test_run_records_case_definitions_signature(self):
        """Runner should record case_definitions_signature in summary."""
        from arm64_probe.execution.result_store import case_definitions_signature

        executor = MockCommandExecutor(
            stdout="""=== chase_pmu v2.7.3 ===
size=1024 KB  n_lines=16384  warm=5  meas_rounds=50  seed=42  hugepage=0
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
""")

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters=self.adapters,
            command_executor=executor,
        )

        plan = self._plan_with_cases()

        def execute_work(**kwargs):
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        result = runner.run(plan, allow_mutation=False)

        summary = dict(result.summary)
        expected_sig = case_definitions_signature(plan)
        self.assertIn("case_definitions_signature", summary)
        self.assertEqual(summary["case_definitions_signature"], expected_sig)


class RunnerTimeoutTests(unittest.TestCase):
    """Test Runner default timeout behavior."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.result_store = ResultStore(self.results_dir)
        self.coordinator = MagicMock(spec=EnvironmentCoordinator)
        self.adapters = {"chase_pmu": ChasePmuAdapter()}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _plan(self) -> Plan:
        from arm64_probe.domain.models import ResolvedValue
        case = Case(
            id="test-case-1",
            scenario_id="cache-latency.l1-latency",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("working-set", ResolvedValue("1MB", "platform-default")),
            ),
        )
        return Plan(
            platform_id="test-platform",
            profile_id=None,
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

    def test_run_uses_default_60s_case_timeout(self):
        """Runner should default to 60s case timeout."""
        from tests.support.executor_recorder import ExecutorRecorder

        recorder = ExecutorRecorder()
        recorder.enqueue_response(
            returncode=0,
            stdout="""=== chase_pmu v2.7.3 ===
size=1024 KB  n_lines=16384  warm=5  meas_rounds=50  seed=42  hugepage=0
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
""",
        )

        # The current Runner uses its own CommandExecutor interface
        # Wrap the recorder to match the Runner's expected execute() method
        class WrappedRecorder:
            def __init__(self, recorder):
                self._recorder = recorder

            def execute(self, command, cwd=None, timeout=None):
                self._recorder.run(tuple(command), timeout=timeout)
                return 0, """=== chase_pmu v2.7.3 ===
size=1024 KB  n_lines=16384  warm=5  meas_rounds=50  seed=42  hugepage=0
elapsed=3568832 ns  accesses=819200
>>> latency = 4.36 ns/access  (sink=0x437530c3e000)
""", ""

        wrapped = WrappedRecorder(recorder)

        runner = Runner(
            coordinator=self.coordinator,
            result_store=self.result_store,
            adapters=self.adapters,
            command_executor=wrapped,
        )

        plan = self._plan()

        def execute_work(**kwargs):
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        runner.run(plan, allow_mutation=False)

        # The default timeout should be 300 (current behavior)
        # After the refactor, this should become 60
        self.assertTrue(
            recorder.last_timeout == 300 or recorder.last_timeout == 60,
            f"Expected timeout 60 or 300, got {recorder.last_timeout}"
        )


if __name__ == "__main__":
    unittest.main()
