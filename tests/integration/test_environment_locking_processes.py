import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from arm64_probe.environment.locking import MutationLock
from arm64_probe.errors import ExitCode, ProbeError


ROOT = Path(__file__).resolve().parents[2]
CHILD = """
import os
import sys
import time
from pathlib import Path
from arm64_probe.environment.locking import MutationLock
with MutationLock(Path(sys.argv[1]), required_owner_uid=os.getuid()):
    print("ready", flush=True)
    time.sleep(60)
"""


class EnvironmentLockingProcessTests(unittest.TestCase):
    def test_contention_fails_and_crashed_owner_releases_os_lock(self):
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
            def cleanup():
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
                child.stdout.close()
                child.stderr.close()

            self.addCleanup(cleanup)
            self.assertEqual(child.stdout.readline().strip(), "ready")

            with self.assertRaises(ProbeError) as error:
                MutationLock(root, required_owner_uid=os.getuid()).acquire()
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_BUSY)

            child.kill()
            child.wait(timeout=10)
            with MutationLock(root, required_owner_uid=os.getuid()) as lock:
                self.assertTrue(lock.held)


if __name__ == "__main__":
    unittest.main()
