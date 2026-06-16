"""Tests for the ResultStore."""
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from arm64_probe.domain.models import Case, Plan, RunResult, Sample
from arm64_probe.execution.result_store import ResultStore, MAX_RESULT_BYTES


class TestResultStore(unittest.TestCase):
    """Test ResultStore read/write operations."""

    def setUp(self):
        """Set up a temporary directory for results."""
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.store = ResultStore(self.results_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_sample_plan(self) -> Plan:
        """Create a minimal Plan for testing."""
        from arm64_probe.domain.models import ResolvedValue

        case = Case(
            id="test-case-1",
            scenario_id="test-scenario",
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
            selections=("test-scenario",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

    def _create_sample_result(self, run_id: str = "test-run-1") -> RunResult:
        """Create a minimal RunResult for testing."""
        plan = self._create_sample_plan()
        sample = Sample(
            run_id=run_id,
            case_id="test-case-1",
            sample_index=0,
            status="ok",
            metrics=(
                ("latency_ns", 100.5),
                ("throughput_mbps", 500.0),
            ),
        )
        return RunResult(
            run_id=run_id,
            plan=plan,
            samples=(sample,),
            summary=(
                ("total_cases", 1),
                ("successful_cases", 1),
            ),
            environment=(),
        )

    def test_write_and_read_result(self):
        """Test writing and reading back a result."""
        result = self._create_sample_result()
        result_path = self.store.write_result(result)

        # Verify file exists
        self.assertTrue(result_path.exists())

        # Read it back
        loaded_result = self.store.read_result("test-run-1")

        # Verify fields match
        self.assertEqual(loaded_result.run_id, result.run_id)
        self.assertEqual(loaded_result.plan.platform_id, result.plan.platform_id)
        self.assertEqual(len(loaded_result.samples), len(result.samples))

        sample = loaded_result.samples[0]
        self.assertEqual(sample.case_id, "test-case-1")
        self.assertEqual(sample.status, "ok")
        self.assertEqual(dict(sample.metrics)["latency_ns"], 100.5)

    def test_write_result_atomic(self):
        """Test that write_result uses atomic write (temp file + rename)."""
        result = self._create_sample_result()
        result_path = self.store.write_result(result)

        # Verify final file exists
        self.assertTrue(result_path.exists())

        # Verify no temp files remain
        temp_files = list(self.results_dir.glob("*.tmp"))
        self.assertEqual(len(temp_files), 0)

    def test_read_nonexistent_result(self):
        """Test reading a result that doesn't exist."""
        from arm64_probe.errors import ExitCode, ProbeError
        with self.assertRaises(ProbeError) as ctx:
            self.store.read_result("nonexistent-run")
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)

    def test_list_results_empty(self):
        """Test listing results when directory is empty."""
        results = self.store.list_results()
        self.assertEqual(results, [])

    def test_list_results_multiple(self):
        """Test listing multiple results."""
        # Write several results
        for i in range(3):
            result = self._create_sample_result(f"run-{i}")
            self.store.write_result(result)

        # List them
        results = self.store.list_results()
        self.assertEqual(len(results), 3)
        self.assertIn("run-0", results)
        self.assertIn("run-1", results)
        self.assertIn("run-2", results)

    def test_write_result_with_error_sample(self):
        """Test writing a result with error samples."""
        plan = self._create_sample_plan()
        error_sample = Sample(
            run_id="error-run",
            case_id="test-case-1",
            sample_index=0,
            status="error",
            metrics=(
                ("error", "Probe failed"),
                ("stderr", "Some error output"),
            ),
        )
        result = RunResult(
            run_id="error-run",
            plan=plan,
            samples=(error_sample,),
            summary=(
                ("total_cases", 1),
                ("failed_cases", 1),
            ),
            environment=(),
        )

        self.store.write_result(result)
        loaded = self.store.read_result("error-run")

        self.assertEqual(loaded.samples[0].status, "error")
        self.assertEqual(dict(loaded.samples[0].metrics)["error"], "Probe failed")

    def test_write_result_preserves_journal_transactions(self):
        """Test that journal_transactions field is preserved."""
        from arm64_probe.domain.models import RunResult

        # Build a result with journal_transactions
        result = RunResult(
            run_id="test-run-1",
            plan=self._create_sample_plan(),
            samples=(Sample(
                run_id="test-run-1",
                case_id="test-case-1",
                sample_index=0,
                status="ok",
                metrics=(("latency_ns", 100.5),),
            ),),
            summary=(("total_cases", 1),),
            environment=(),
            journal_transactions=("tx-123", "tx-456"),
        )

        self.store.write_result(result)
        loaded = self.store.read_result("test-run-1")

        self.assertEqual(tuple(loaded.journal_transactions), ("tx-123", "tx-456"))

    def test_write_result_uses_temp_file_pattern(self):
        """write_result should write to a temp file then rename."""
        result = self._create_sample_result("atomic-test")

        # Intercept os.replace to verify the pattern
        with patch("os.replace", wraps=os.replace) as mock_replace:
            self.store.write_result(result)

        # os.replace should have been called (temp -> final)
        self.assertTrue(mock_replace.called, "write_result should use os.replace for atomic write")

    def test_read_rejects_oversized_file(self):
        """read should reject files larger than MAX_RESULT_BYTES."""
        from arm64_probe.errors import ExitCode, ProbeError

        large_path = self.results_dir / "oversized.json"
        # Write a file just over the limit
        large_path.write_text("x" * (MAX_RESULT_BYTES + 1))

        with self.assertRaises(ProbeError) as ctx:
            self.store.read(large_path)
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)

    def test_read_result_preserves_new_fields(self):
        """_dict_to_run_result should deserialize schema_version, prior_run_id, resume_kind."""
        result = RunResult(
            run_id="test-run-1",
            plan=self._create_sample_plan(),
            samples=(Sample(
                run_id="test-run-1",
                case_id="test-case-1",
                sample_index=0,
                status="ok",
                metrics=(("latency_ns", 100.5),),
            ),),
            summary=(("total_cases", 1),),
            environment=(),
            schema_version=2,
            prior_run_id="prior-abc",
            resume_kind="no-op",
        )

        self.store.write_result(result)
        loaded = self.store.read_result("test-run-1")

        self.assertEqual(loaded.schema_version, 2)
        self.assertEqual(loaded.prior_run_id, "prior-abc")
        self.assertEqual(loaded.resume_kind, "no-op")

    def test_read_validates_schema_version(self):
        """read should reject RunResults with unexpected schema_version."""
        from arm64_probe.errors import ExitCode, ProbeError

        result = RunResult(
            run_id="old-schema",
            plan=self._create_sample_plan(),
            samples=(Sample(
                run_id="old-schema",
                case_id="test-case-1",
                sample_index=0,
                status="ok",
                metrics=(("latency_ns", 100.5),),
            ),),
            summary=(("total_cases", 1),),
            environment=(),
            schema_version=1,
        )

        self.store.write_result(result)

        with self.assertRaises(ProbeError) as ctx:
            self.store.read_result("old-schema")
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)


if __name__ == "__main__":
    unittest.main()
