import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_module(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "arm64_probe", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def run_script(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ROOT / "probe"), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliFoundationTests(unittest.TestCase):
    def test_top_level_help_is_side_effect_free(self):
        result = run_module("--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: probe", result.stdout)
        for command in ("list", "show", "plan"):
            with self.subTest(command=command):
                self.assertIn(command, result.stdout)

    def test_checkout_script_exposes_same_help(self):
        module_result = run_module("--help")
        script_result = run_script("--help")

        self.assertEqual(script_result.returncode, 0, script_result.stderr)
        self.assertEqual(script_result.stdout, module_result.stdout)

    def test_unknown_command_uses_cli_usage_exit_code(self):
        result = run_module("unknown-command")

        self.assertEqual(result.returncode, 2)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_stable_exit_code_values(self):
        from arm64_probe.errors import ExitCode

        self.assertEqual(ExitCode.SUCCESS, 0)
        self.assertEqual(ExitCode.USAGE, 2)
        self.assertEqual(ExitCode.CONFIG, 3)
        self.assertEqual(ExitCode.CAPABILITY, 4)
        self.assertEqual(ExitCode.PLANNING, 5)


if __name__ == "__main__":
    unittest.main()
