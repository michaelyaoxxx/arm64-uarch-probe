"""Integration test for Phase 4 analysis workflow via the CLI."""
import subprocess
import tempfile
import unittest
from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / "probe"


class Phase4AnalysisWorkflowTests(unittest.TestCase):
    """End-to-end workflow test for probe analyze."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _write_fixture_result(self, run_id: str, case_id: str,
                              latency_ns: float) -> Path:
        from arm64_probe.execution.result_store import ResultStore
        from arm64_probe.domain.models import (
            Sample, Plan, Case, make_run_result, ResolvedValue,
        )
        store = ResultStore(results_dir=self.tmpdir)
        samples = (
            Sample(
                run_id=run_id, case_id=case_id, sample_index=0,
                status="ok", metrics=(("latency_ns", latency_ns),),
            ),
        )
        plan = Plan(
            platform_id="gb10", profile_id="smoke",
            selections=("test",),
            cases=(
                Case(id=case_id, scenario_id="test", platform_id="gb10",
                     status="ready", reason=None, cpu=0, src_cpu=None,
                     dst_cpu=None, selectors=(),
                     parameters=(("samples", ResolvedValue(value=1,
                                                           source="default")),),
                     execution_requirements=()),
            ),
            environment_phases=(), skip_unavailable=False,
        )
        result = make_run_result(
            run_id=run_id, plan=plan, samples=samples,
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
        return store.write_result(result)

    def test_analyze_two_run_files(self):
        run1 = self._write_fixture_result("run-alpha", "membench@gb10", 4.2)
        run2 = self._write_fixture_result("run-beta", "membench@gb10", 4.5)
        output_dir = self.tmpdir / "analysis"
        result = subprocess.run(
            [str(PROBE), "analyze",
             "--run", str(run1), "--run", str(run2),
             "--output-dir", str(output_dir), "-o", "table"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("membench@gb10", result.stdout)
        self.assertIn("run-alpha", result.stdout)
        self.assertIn("run-beta", result.stdout)

    def test_analyze_duplicate_run_id_rejected(self):
        run1 = self._write_fixture_result("dup-run", "case@gb10", 4.2)
        run2 = self._write_fixture_result("dup-run", "case@gb10", 4.3)
        output_dir = self.tmpdir / "analysis"
        result = subprocess.run(
            [str(PROBE), "analyze",
             "--run", str(run1), "--run", str(run2),
             "--output-dir", str(output_dir), "-o", "table"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 16)
        self.assertIn("duplicate", result.stderr)
