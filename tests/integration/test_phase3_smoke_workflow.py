"""Integration smoke test: Runner + FakeBackend produces a schema-valid RunResult."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from arm64_probe.domain.models import (
    Case,
    Plan,
    ResolvedValue,
    RunResult,
    Sample,
)
from arm64_probe.environment.coordinator import EnvironmentCoordinator
from arm64_probe.execution.adapters.chase_pmu import ChasePmuAdapter
from arm64_probe.execution.result_store import ResultStore
from arm64_probe.execution.runner import Runner
from arm64_probe.serialization.model_json import to_data


class Phase3SmokeWorkflowTests(unittest.TestCase):
    """End-to-end smoke: Runner against a fake coordinator + executor."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.result_store = ResultStore(self.results_dir)
        self.coordinator = MagicMock(spec=EnvironmentCoordinator)
        self.adapters = {"chase_pmu": ChasePmuAdapter()}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_smoke_workflow_produces_valid_run_result(self):
        """Full runner workflow should produce a schema-valid RunResult."""
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
        )
        plan = Plan(
            platform_id="gb10",
            profile_id="smoke",
            selections=("cache-latency.l1-latency",),
            cases=(case,),
            environment_phases=(),
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
            adapters=self.adapters,
            command_executor=executor,
        )

        def execute_work(**kwargs):
            work = kwargs.get("work")
            if work:
                work()
            return MagicMock()

        self.coordinator.execute.side_effect = execute_work

        result = runner.run(plan, allow_mutation=False)

        # Verify RunResult structure
        self.assertIsInstance(result, RunResult)
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(result.samples[0].status, "ok")
        self.assertEqual(result.schema_version, 2)

        # Verify it serializes to valid JSON
        result_json = json.dumps(to_data(result), sort_keys=True, default=str)
        self.assertIsInstance(json.loads(result_json), dict)

        # Verify it was persisted
        result_files = list(self.results_dir.glob("*.json"))
        self.assertGreater(len(result_files), 0)


class _RecordingExecutor:
    """Records executed commands and returns scripted responses."""

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
