import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class Phase1CliWorkflowTests(unittest.TestCase):
    def test_all_phase1_commands_are_side_effect_free_from_other_directory(self):
        commands = (
            ("--help",),
            ("help", "plan"),
            ("list", "targets"),
            ("show", "gb10", "-o", "json"),
            ("plan", "--platform", "m4", "--profile", "smoke", "-o", "json"),
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
                    output = result.stdout + result.stderr
                    for forbidden in ("/sys/", "/proc/", "taskset", "sudo "):
                        self.assertNotIn(forbidden, output)


if __name__ == "__main__":
    unittest.main()
