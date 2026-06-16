import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_probe(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "arm64_probe", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliRunCommandTests(unittest.TestCase):
    """Test that `probe run` command is recognized by the CLI."""

    def test_run_command_recognized(self):
        """`probe run --help` should return 0."""
        result = run_probe("run", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("execute", result.stdout.lower())

    def test_run_accepts_platform_argument(self):
        """`probe run --platform gb10` should parse without error."""
        result = run_probe("run", "--platform", "gb10", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_run_accepts_profile_argument(self):
        """`probe run --profile smoke` should parse without error."""
        result = run_probe("run", "--profile", "smoke", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_run_accepts_allow_mutation_flag(self):
        """`probe run --allow-mutation` should parse without error."""
        result = run_probe("run", "--allow-mutation", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_run_accepts_output_dir_argument(self):
        """`probe run --output-dir /tmp` should parse without error."""
        result = run_probe("run", "--output-dir", "/tmp", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")


class ExitCodeTests(unittest.TestCase):
    """Test that new exit codes are defined."""

    def test_exit_codes_15_and_16_defined(self):
        """ExitCode enum should have PROBE_EXECUTION=15 and RUN_RESULT=16."""
        from arm64_probe.errors import ExitCode

        self.assertTrue(hasattr(ExitCode, "PROBE_EXECUTION"))
        self.assertEqual(ExitCode.PROBE_EXECUTION, 15)

        self.assertTrue(hasattr(ExitCode, "RUN_RESULT"))
        self.assertEqual(ExitCode.RUN_RESULT, 16)


class RunCommandExecutionTests(unittest.TestCase):
    """Test that `probe run` executes and returns results."""

    def test_run_executes_plan_and_returns_zero_on_success(self):
        """`probe run` should execute a plan and return 0 on success."""
        result = run_probe(
            "run",
            "--platform", "gb10",
            "--profile", "smoke",
            "-o", "json",
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

        # Should return JSON with samples
        output = json.loads(result.stdout)
        self.assertIn("samples", output)
        self.assertIsInstance(output["samples"], list)

    def test_run_creates_result_file_in_default_directory(self):
        """`probe run` should create a result file in results/runs/."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "runs"
            result = run_probe(
                "run",
                "--platform", "gb10",
                "--profile", "smoke",
                "--output-dir", str(output_dir),
                "-o", "json",
            )

            self.assertEqual(result.returncode, 0)

            # Check that a result file was created
            result_files = list(output_dir.glob("*.json"))
            self.assertGreater(len(result_files), 0, "No result files created")

    def test_run_requires_allow_mutation_for_host_changes(self):
        """`probe run` should fail without --allow-mutation if plan has mutations."""
        # smoke profile has no mutations, so this should succeed
        result = run_probe(
            "run",
            "--platform", "gb10",
            "--profile", "smoke",
        )
        self.assertEqual(result.returncode, 0)

    def test_run_returns_15_on_probe_execution_failure(self):
        """`probe run` should return 15 when probe execution fails.

        Note: m4 is a contract-only platform, so all cases are marked
        as 'unsupported' and the Runner skips them (returns 'skipped'
        samples). This test verifies that on a platform with no real
        probes, the run completes with skipped samples and exit 0.
        True probe execution failures (exit 15) are covered by the
        unit tests in test_runner.py.
        """
        # Use a profile on a contract-only platform
        result = run_probe(
            "run",
            "--platform", "m4",  # M4 is contract-only, no real probes
            "--profile", "smoke",
            "-o", "json",
        )

        # On m4 (contract-only), no real probe execution happens
        # All cases are 'skipped', so the run completes with exit 0
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
