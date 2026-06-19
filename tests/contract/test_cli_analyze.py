"""CLI contract tests for probe analyze."""
import subprocess
import tempfile
import unittest
from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / "probe"


class CliAnalyzeCommandTests(unittest.TestCase):
    def test_analyze_help(self):
        result = subprocess.run(
            [str(PROBE), "analyze", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--run", result.stdout)

    def test_analyze_missing_run_returns_usage_error(self):
        result = subprocess.run(
            [str(PROBE), "analyze"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_analyze_dash_o_json_accepted(self):
        result = subprocess.run(
            [str(PROBE), "analyze", "--help"],
            capture_output=True, text=True,
        )
        self.assertIn("-o", result.stdout)


class CliAnalyzeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _write_fixture_result(self):
        from arm64_probe.execution.result_store import ResultStore
        from arm64_probe.domain.models import (
            Sample, Plan, Case, make_run_result,
            ResolvedValue,
        )
        store = ResultStore(results_dir=self.tmpdir)
        samples = (
            Sample(
                run_id="testrun", case_id="test@gb10", sample_index=0,
                status="ok", metrics=(("latency_ns", 4.36),),
            ),
        )
        plan = Plan(
            platform_id="gb10", profile_id="smoke",
            selections=("test",),
            cases=(
                Case(id="test@gb10", scenario_id="test", platform_id="gb10",
                     status="ready", reason=None, cpu=0, src_cpu=None,
                     dst_cpu=None, selectors=(),
                     parameters=(("samples", ResolvedValue(value=1, source="default")),),
                     execution_requirements=()),
            ),
            environment_phases=(), skip_unavailable=False,
        )
        result = make_run_result(
            run_id="testrun", plan=plan, samples=samples,
            summary=(
                ("platform_id", "gb10"),
                ("total_samples", 1), ("ok_samples", 1),
                ("error_samples", 0), ("skipped_samples", 0),
                ("phase_count", 1),
                ("repository_id", "github.com/x/arm64-uarch-probe"),
                ("repository_commit", "abc123"), ("dirty_tree", False),
                ("case_definitions_signature", "aa" * 32),
            ),
            environment=(("platform", "unknown"),),
        )
        store.write_result(result)
        return self.tmpdir / "testrun.json"

    def test_analyze_accepts_run_and_writes_analysis_json(self):
        run_path = self._write_fixture_result()
        output_dir = self.tmpdir / "analysis_out"
        result = subprocess.run(
            [str(PROBE), "analyze", "--run", str(run_path),
             "--output-dir", str(output_dir), "-o", "json"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        files = list(output_dir.glob("*.json"))
        self.assertGreater(len(files), 0)

    def test_analyze_nonexistent_file_returns_16(self):
        result = subprocess.run(
            [str(PROBE), "analyze", "--run", "/nonexistent/path.json",
             "--output-dir", str(self.tmpdir / "out"), "-o", "json"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 16)
