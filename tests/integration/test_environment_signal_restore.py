"""End-to-end signal-driven restoration test for the environment coordinator."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ID = "github.com/michaelyaoxxx/arm64-uarch-probe"


CHILD = textwrap.dedent(
    """
    import os
    import sys
    import time
    from datetime import UTC, datetime
    from pathlib import Path

    from arm64_probe.environment.constants import REPOSITORY_ID
    from arm64_probe.environment.coordinator import EnvironmentCoordinator
    from arm64_probe.environment.journal import JournalStore
    from arm64_probe.environment.models import ControllerRequest
    from tests.support.fake_controllers import FakeBackend, FakeController

    fixed = datetime(2026, 6, 15, 0, 0, 0, tzinfo=UTC)
    root = Path(sys.argv[1])
    print("ready", flush=True)
    store = JournalStore(
        root,
        repository_id=REPOSITORY_ID,
        required_owner_uid=os.getuid(),
        clock=lambda: fixed,
        transaction_id_factory=lambda: "b" * 32,
    )
    controller = FakeController(
        "linux.cpufreq",
        "linux.cpufreq",
        before_values=(("governor", "powersave"),),
        applied_values=(("governor", "performance"),),
    )
    backend = FakeBackend(controllers=(controller,))
    coordinator = EnvironmentCoordinator(
        journal_factory=lambda: (root, store, os.getuid(), REPOSITORY_ID),
    )
    try:
        coordinator.execute(
            backend=backend,
            platform_id="gb10",
            requests=(ControllerRequest("linux.cpufreq", (("governor", "performance"),)),),
            work=lambda: time.sleep(60),
            allow_mutation=True,
        )
    except Exception as error:  # noqa: BLE001
        print(f"failure:{type(error).__name__}:{error}", flush=True)
        sys.exit(0)
    sys.exit(0)
    """
)


class EnvironmentSignalRestoreTests(unittest.TestCase):
    def test_sigterm_triggers_restoration_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            environment = {**os.environ, "PYTHONPATH": str(ROOT)}
            child = subprocess.Popen(
                [sys.executable, "-c", CHILD, str(root)],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                time.sleep(0.2)
                child.send_signal(signal.SIGTERM)
                stdout, _ = child.communicate(timeout=30)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)

            self.assertTrue(stdout.startswith("failure:ProbeError:"))
            self.assertIn("signal 15", stdout)

            from arm64_probe.environment.journal import JournalStore

            store = JournalStore(
                root,
                repository_id=REPOSITORY_ID,
                required_owner_uid=os.getuid(),
                clock=lambda: datetime(2026, 6, 15, 1, 0, 0, tzinfo=UTC),
                transaction_id_factory=lambda: "ignored",
            )
            journal = store.read(root / "journals" / (("b" * 32) + ".json"))
            self.assertEqual(journal.state, "restored")
            self.assertEqual(journal.applied, ("linux.cpufreq",))
            self.assertEqual(journal.restoration_status, "succeeded")
            self.assertEqual(
                [failure.category for failure in journal.failures],
                ["signal"],
            )

            from arm64_probe.environment.locking import MutationLock

            with MutationLock(root, required_owner_uid=os.getuid()) as lock:
                self.assertTrue(lock.held)


if __name__ == "__main__":
    unittest.main()
