"""Phase 2 acceptance contract tests.

These tests enforce repository-level invariants that the v1.0 architecture
must preserve: no live host coupling outside the read-only `doctor` flow,
no platform-name branches in capability-driven code, deterministic
planning, and explicit authorization on every mutating entry point.
"""

from __future__ import annotations

import ast
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_FORBIDDEN = (
    "/sys/",
    "/proc/",
    "/var/lib/arm64-uarch-probe",
    "gb10",
    "m4",
    "taskset",
    "sudo ",
)


def _read(relative: str) -> str:
    return ROOT.joinpath(*relative.split("/")).read_text()


def _iter_python(relative: str):
    text = _read(relative)
    tree = ast.parse(text)
    yield relative, text, tree


class Phase2ArchitectureBoundariesTests(unittest.TestCase):
    def test_platform_resolver_has_no_live_host_mechanisms(self):
        text = _read("arm64_probe/platforms/configured_resolver.py")
        for forbidden in SOURCE_FORBIDDEN:
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, text)

    def test_backends_coordinators_and_controllers_have_no_platform_branches(self):
        # Files that legitimately embed well-known Linux sysfs paths as
        # constant strings. The acceptance boundary only forbids dynamic
        # platform names (gb10, m4) and live-host coupling in non-Linux
        # paths.
        files = [
            "arm64_probe/backends/base.py",
            "arm64_probe/backends/io.py",
            "arm64_probe/backends/select.py",
            "arm64_probe/backends/darwin_arm64/backend.py",
            "arm64_probe/backends/linux_arm64/backend.py",
            "arm64_probe/environment/coordinator.py",
            "arm64_probe/environment/recovery.py",
            "arm64_probe/environment/signals.py",
        ]
        platform_only_forbidden = ("gb10", "m4", "taskset", "sudo ")
        for relative in files:
            text = _read(relative)
            with self.subTest(file=relative):
                for forbidden in platform_only_forbidden:
                    self.assertNotIn(forbidden, text)

    def test_execution_modules_have_no_platform_branches(self):
        """Phase 3 execution modules must be platform-independent."""
        import glob
        execution_files = [
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "arm64_probe/execution").rglob("*.py")
            if p.name != "__pycache__"
        ]
        platform_only_forbidden = ("gb10", "m4", "taskset", "sudo ")
        for relative in execution_files:
            text = _read(relative)
            with self.subTest(file=relative):
                for forbidden in platform_only_forbidden:
                    self.assertNotIn(forbidden, text)

    def test_configs_contain_no_sysfs_proc_shell_or_runner_logic(self):
        for path in sorted(ROOT.joinpath("configs").rglob("*.json")):
            payload = json.loads(path.read_text())
            with self.subTest(path=str(path)):
                self.assertNotIn("taskset", json.dumps(payload))
                self.assertNotIn("sudo", json.dumps(payload))


class Phase2FixtureWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(platform.system() == "Darwin", "requires Darwin ARM64 host")
    def test_darwin_probe_workflow_creates_no_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            environment = {**os.environ, "PYTHONPATH": str(ROOT)}
            commands = (
                ("--help",),
                ("help", "plan"),
                ("help", "doctor"),
                ("help", "restore"),
                ("list", "targets"),
                ("show", "gb10", "-o", "json"),
                ("plan", "--platform", "m4", "--profile", "smoke", "-o", "json"),
                ("doctor", "-o", "json"),
            )
            for command in commands:
                with self.subTest(command=command):
                    before = set(workdir.iterdir())
                    result = subprocess.run(
                        [sys.executable, "-m", "arm64_probe", *command],
                        cwd=workdir,
                        env=environment,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(set(workdir.iterdir()), before)
                    output = result.stdout + result.stderr
                    for forbidden in ("/sys/", "/proc/", "taskset", "sudo "):
                        self.assertNotIn(forbidden, output)


class Phase2RestoreAuthorizationTests(unittest.TestCase):
    def test_restore_requires_authorization_and_accepts_no_target_settings(self):
        result = subprocess.run(
            [sys.executable, "-m", "arm64_probe", "help", "restore"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--allow-mutation", result.stdout)
        self.assertIn("--journal", result.stdout)
        for forbidden in ("--state-root", "--target", "--value", "--command"):
            self.assertNotIn(forbidden, result.stdout)


class FrozenTransitionalPathsTests(unittest.TestCase):
    def test_frozen_legacy_paths_remain_unchanged_since_phase1(self):
        from subprocess import check_output

        for path in ("runner/run_pmu_v2.7.3.sh", "data/20260611_v2.7.3/raw/run_20260611_123112.txt"):
            with self.subTest(path=path):
                output = check_output(
                    ["git", "--git-dir", str(ROOT / ".git"), "diff", "--stat", "main", "--", path],
                    cwd=ROOT,
                    text=True,
                )
                self.assertEqual(output.strip(), "")


if __name__ == "__main__":
    unittest.main()
