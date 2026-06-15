import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Phase2DoctorWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(
        platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"},
        "requires Darwin ARM64 host",
    )
    def test_darwin_doctor_commands_create_no_files(self):
        commands = (
            ("doctor",),
            ("doctor", "--platform", "m4"),
            ("doctor", "-o", "json"),
            ("help", "doctor"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            environment = {
                "PATH": os.environ["PATH"],
                "PYTHONPATH": str(ROOT),
            }
            for command in commands:
                with self.subTest(command=command):
                    before = tuple(workdir.iterdir())
                    result = subprocess.run(
                        [sys.executable, "-m", "arm64_probe", *command],
                        cwd=workdir,
                        env=environment,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(tuple(workdir.iterdir()), before)


if __name__ == "__main__":
    unittest.main()
