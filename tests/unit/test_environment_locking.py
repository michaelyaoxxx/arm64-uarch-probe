import os
import tempfile
import unittest
from pathlib import Path

from arm64_probe.environment.locking import MutationLock
from arm64_probe.errors import ExitCode, ProbeError


class EnvironmentLockingTests(unittest.TestCase):
    def test_context_creates_holds_and_releases_fixed_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            lock = MutationLock(root, required_owner_uid=os.getuid())
            self.assertFalse(root.exists())

            with lock:
                self.assertTrue(lock.held)
                self.assertEqual(lock.metadata["pid"], os.getpid())
                self.assertTrue((root / "mutation.lock").exists())
                self.assertEqual((root / "mutation.lock").stat().st_mode & 0o777, 0o644)

            self.assertFalse(lock.held)
            self.assertTrue((root / "mutation.lock").exists())

    def test_rejects_unsafe_root_symlink_lock_and_owner_before_acquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            unsafe = parent / "unsafe"
            unsafe.mkdir()
            os.chmod(unsafe, 0o777)
            with self.assertRaises(ProbeError):
                MutationLock(unsafe, required_owner_uid=os.getuid()).acquire()
            self.assertEqual(unsafe.stat().st_mode & 0o777, 0o777)

            root = parent / "state"
            root.mkdir(mode=0o755)
            target = parent / "target"
            target.write_text("")
            (root / "mutation.lock").symlink_to(target)
            with self.assertRaises(ProbeError):
                MutationLock(root, required_owner_uid=os.getuid()).acquire()

            missing = parent / "missing"
            with self.assertRaises(ProbeError) as error:
                MutationLock(missing, required_owner_uid=os.getuid() + 1).acquire()
            self.assertEqual(error.exception.code, ExitCode.MUTATION_AUTHORIZATION)
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
