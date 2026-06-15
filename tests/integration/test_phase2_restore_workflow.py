"""End-to-end probe-restore workflow tests for the Darwin fixture host."""

from __future__ import annotations

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
    return store.create(journal)


class Phase2RestoreWorkflowTests(unittest.TestCase):
    def test_restore_command_creates_only_authorized_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "work"
            state = Path(tmp) / "state"
            workdir.mkdir()
            journal_path = _seed_journal(state)
            before_files = set(workdir.iterdir())
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "arm64_probe",
                    "restore",
                    "--journal",
                    str(journal_path),
                    "--allow-mutation",
                ],
                cwd=workdir,
                env={**os.environ, "PYTHONPATH": str(ROOT)},
                capture_output=True,
                text=True,
            )
            after_files = set(workdir.iterdir())

        self.assertIn(result.returncode, (0, 11, 13))
        self.assertEqual(before_files, after_files)


if __name__ == "__main__":
    unittest.main()
