"""Phase 3 acceptance contract tests.

These tests enforce the AC1–AC9 criteria from the Phase 3 handoff,
covering execution boundaries, platform-name branch prohibition, and
smoke workflow invariants.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# Tokens forbidden in platform-independent execution code
EXECUTION_FORBIDDEN = (
    "gb10",
    "m4",
    "taskset",
    "sudo ",
    "/sys/",
    "/proc/",
)

# Files in arm64_probe/execution/ that must be free of platform-name branches
EXECUTION_MODULES = (
    "arm64_probe/execution/__init__.py",
    "arm64_probe/execution/runner.py",
    "arm64_probe/execution/result_store.py",
    "arm64_probe/execution/resume.py",
    "arm64_probe/execution/adapters/__init__.py",
    "arm64_probe/execution/adapters/base.py",
    "arm64_probe/execution/adapters/chase_pmu.py",
    "arm64_probe/execution/adapters/evict_slc.py",
    "arm64_probe/execution/adapters/chase_migrate.py",
)

# Frozen paths that must not appear in the diff from main
FROZEN_PATHS = (
    "runner/",
    "data/",
    "analysis/",
    "baseline/",
)


class Phase3ArchitectureBoundariesTests(unittest.TestCase):
    """Execution modules must contain no platform-name branches or live-host coupling."""

    def test_no_platform_name_branch_in_execution_modules(self):
        for relative in EXECUTION_MODULES:
            path = ROOT / relative
            if not path.exists():
                continue
            text = path.read_text()
            with self.subTest(file=relative):
                for forbidden in EXECUTION_FORBIDDEN:
                    self.assertNotIn(
                        forbidden, text,
                        f"{relative} contains forbidden token: {forbidden!r}"
                    )

    def test_probe_run_routes_through_runner_not_raw_subprocess(self):
        """CLI run dispatch must import and use Runner.run."""
        text = (ROOT / "arm64_probe/cli/main.py").read_text()
        self.assertIn("Runner", text)
        self.assertIn("runner.run", text)


class Phase3FrozenPathBoundaryTests(unittest.TestCase):
    """Frozen and transitional paths must not be touched by Phase 3."""

    def test_frozen_paths_remain_unchanged(self):
        result = subprocess.run(
            ["git", "diff", "--name-only", "main", "--"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        changed = result.stdout.strip().splitlines()
        for changed_path in changed:
            for frozen in FROZEN_PATHS:
                self.assertFalse(
                    changed_path.startswith(frozen),
                    f"Frozen path modified by Phase 3: {changed_path}"
                )


class Phase3SmokeWorkflowTests(unittest.TestCase):
    """Minimal smoke workflow runs without host mutation and produces a valid RunResult."""

    def test_smoke_run_produces_schema_valid_run_result(self):
        """probe run with smoke profile on m4 should produce a valid RunResult."""
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "runs"
            result = subprocess.run(
                [
                    sys.executable, "-m", "arm64_probe",
                    "run",
                    "--platform", "m4",
                    "--profile", "smoke",
                    "--output-dir", str(output_dir),
                    "-o", "json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")

            # Parse JSON output
            output = json.loads(result.stdout)
            self.assertIn("run_id", output)
            self.assertIn("samples", output)
            self.assertIn("plan", output)
            self.assertIn("schema_version", output)
            self.assertEqual(output["schema_version"], 2)

            # Verify result files were created
            result_files = list(output_dir.glob("*.json"))
            self.assertGreater(len(result_files), 0,
                               "Expected at least one RunResult file")

    def test_run_and_plan_emit_same_case_ids(self):
        """probe run and probe plan should produce the same case IDs (AC2)."""
        # Run plan
        plan_result = subprocess.run(
            [sys.executable, "-m", "arm64_probe", "plan",
             "--platform", "m4", "--profile", "smoke", "-o", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(plan_result.returncode, 0, plan_result.stderr)
        plan_json = json.loads(plan_result.stdout)
        plan_case_ids = {c["id"] for c in plan_json["cases"]}

        # Run execution
        with tempfile.TemporaryDirectory() as tmp:
            run_result = subprocess.run(
                [
                    sys.executable, "-m", "arm64_probe",
                    "run",
                    "--platform", "m4",
                    "--profile", "smoke",
                    "--output-dir", str(Path(tmp) / "runs"),
                    "-o", "json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr)
            run_json = json.loads(run_result.stdout)
            run_case_ids = {s["case_id"] for s in run_json["samples"]}

        # Both should have the same case IDs (plan controls what runs)
        self.assertEqual(plan_case_ids, run_case_ids)


if __name__ == "__main__":
    unittest.main()
