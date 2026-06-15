"""Contract tests for the `probe restore` CLI surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ID = "github.com/michaelyaoxxx/arm64-uarch-probe"
FIXED_TIME = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)


def _seed_journal(root: Path, transaction_id: str = "a" * 32) -> Path:
    from arm64_probe.environment.constants import REPOSITORY_ID
    from arm64_probe.environment.journal import JournalStore
    from arm64_probe.environment.models import ControllerRequest, ControllerState

    store = JournalStore(
        root,
        repository_id=REPOSITORY_ID,
        required_owner_uid=os.getuid(),
        clock=lambda: FIXED_TIME,
        transaction_id_factory=lambda: transaction_id,
    )
    request = ControllerRequest("linux.cpufreq", (("governor", "performance"),))
    before = ControllerState("linux.cpufreq", "available", (("governor", "powersave"),), ())
    journal = store.new("linux-arm64", "gb10", (request,), (before,))
    path = store.create(journal)
    return path


class ProbeRestoreCliTests(unittest.TestCase):
    def test_restore_help_is_advertised(self):
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

    def test_restore_command_appears_in_top_level_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "arm64_probe", "--help"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("restore", result.stdout)

    def test_restore_missing_mutation_returns_11(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal_path = _seed_journal(Path(tmp) / "state")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "arm64_probe",
                    "restore",
                    "--journal",
                    str(journal_path),
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 11)
        self.assertIn("allow-mutation", (result.stdout + result.stderr).lower())

    def test_restore_outside_managed_journal_returns_13(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "rogue.json"
            bad.write_text("{}")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "arm64_probe",
                    "restore",
                    "--journal",
                    str(bad),
                    "--allow-mutation",
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 13)
        self.assertIn("journal", (result.stdout + result.stderr).lower())

    def test_restore_json_output_advertised(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal_path = _seed_journal(Path(tmp) / "state")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "arm64_probe",
                    "restore",
                    "--journal",
                    str(journal_path),
                    "--allow-mutation",
                    "-o",
                    "json",
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
                capture_output=True,
                text=True,
            )
        # The production state root requires root privileges; non-root hosts
        # receive a structured authorization error in JSON form.
        self.assertIn("\"code\"", result.stdout)
        self.assertIn("\"message\"", result.stdout)


if __name__ == "__main__":
    unittest.main()
