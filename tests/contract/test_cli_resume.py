"""Contract tests for `probe resume` CLI command."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from arm64_probe.domain.models import (
    Case,
    Plan,
    ResolvedValue,
    RunResult,
    Sample,
)
from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.serialization.model_json import to_data
from arm64_probe.serialization.json_io import dump_json


ROOT = Path(__file__).resolve().parents[2]


def run_probe(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "arm64_probe", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliResumeCommandTests(unittest.TestCase):
    """Test that `probe resume` command is recognized by the CLI."""

    def test_resume_command_recognized(self):
        """`probe resume --help` should return 0."""
        result = run_probe("resume", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("resume", result.stdout.lower())

    def test_resume_requires_run_argument(self):
        """`probe resume` without --run should show usage error."""
        result = run_probe("resume")
        self.assertNotEqual(result.returncode, 0)

    def test_resume_accepts_run_argument(self):
        """`probe resume --run <path>` should parse with a dummy path."""
        result = run_probe("resume", "--run", "/tmp/dummy.json", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_resume_accepts_output_dir(self):
        """`probe resume --run <path> --output-dir <dir>` should parse."""
        result = run_probe("resume", "--run", "/tmp/dummy.json",
                           "--output-dir", "/tmp/resume-runs", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_resume_accepts_allow_mutation(self):
        """`probe resume --run <path> --allow-mutation` should parse."""
        result = run_probe("resume", "--run", "/tmp/dummy.json",
                           "--allow-mutation", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

    def test_resume_accepts_output_json(self):
        """`probe resume --run <path> -o json` should parse."""
        result = run_probe("resume", "--run", "/tmp/dummy.json",
                           "-o", "json", "--help")
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")


class CliResumeExecutionTests(unittest.TestCase):
    """Test `probe resume` end-to-end execution."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.runs_dir = Path(self.temp_dir) / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_prior_result(self, run_id="prior-run",
                            case_statuses=None) -> Path:
        """Write a minimal prior RunResult JSON to a temp file."""
        if case_statuses is None:
            case_statuses = {"case-1": "ok"}

        cases = tuple(
            Case(
                id=cid,
                scenario_id="test-scenario",
                platform_id="m4",
                status="ready",
                reason=None,
                cpu=0,
                src_cpu=None,
                dst_cpu=None,
                selectors=(),
                parameters=(("samples", ResolvedValue(7, "platform-default")),),
            )
            for cid in case_statuses
        )
        plan = Plan(
            platform_id="m4",
            profile_id=None,
            selections=("test-scenario",),
            cases=cases,
            environment_phases=(),
            skip_unavailable=False,
        )
        samples = tuple(
            Sample(
                run_id=run_id,
                case_id=cid,
                sample_index=0,
                status=status,
                metrics=(("latency_ns", 4.5),),
            )
            for cid, status in case_statuses.items()
        )
        result = RunResult(
            run_id=run_id,
            plan=plan,
            samples=samples,
            summary=(
                ("platform_id", "m4"),
            ),
            environment=(),
            schema_version=2,
        )

        path = Path(self.temp_dir) / f"{run_id}.json"
        path.write_text(dump_json(to_data(result)))
        return path

    def test_resume_reads_prior_result(self):
        """`probe resume --run <path>` should read and resume from a prior result."""
        prior_path = self._write_prior_result()
        result = run_probe(
            "resume",
            "--run", str(prior_path),
            "--output-dir", str(self.runs_dir),
            "-o", "json",
        )
        # Should succeed
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

        output = json.loads(result.stdout)
        self.assertIn("prior_run_id", output)
        self.assertEqual(output["prior_run_id"], "prior-run")
        self.assertIn("resume_kind", output)

    def test_resume_rejects_nonexistent_path(self):
        """`probe resume --run <nonexistent>` should return 16."""
        result = run_probe(
            "resume",
            "--run", str(Path(self.temp_dir) / "nonexistent.json"),
            "--output-dir", str(self.runs_dir),
        )
        self.assertEqual(result.returncode, ExitCode.RUN_RESULT)

    def test_resume_rejects_invalid_json(self):
        """`probe resume --run <invalid-json>` should return 16."""
        bad_path = Path(self.temp_dir) / "bad.json"
        bad_path.write_text("not valid json")
        result = run_probe(
            "resume",
            "--run", str(bad_path),
            "--output-dir", str(self.runs_dir),
        )
        self.assertEqual(result.returncode, ExitCode.RUN_RESULT)

    def test_resume_creates_new_result_file(self):
        """Resume should write a new RunResult JSON in the output dir."""
        prior_path = self._write_prior_result()
        result = run_probe(
            "resume",
            "--run", str(prior_path),
            "--output-dir", str(self.runs_dir),
            "-o", "json",
        )
        self.assertEqual(result.returncode, 0)

        # Check a new file was created
        result_files = list(self.runs_dir.glob("*.json"))
        self.assertGreater(len(result_files), 0, "No result files created by resume")


from arm64_probe.errors import ExitCode

if __name__ == "__main__":
    unittest.main()
