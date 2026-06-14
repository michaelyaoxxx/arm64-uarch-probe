import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_probe(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "arm64_probe", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliDiscoveryTests(unittest.TestCase):
    def test_list_commands_are_deterministic(self):
        expectations = {
            "targets": "cache-latency.l1-latency",
            "profiles": "baseline",
            "platforms": "gb10",
            "capabilities": "cpu-binding",
        }
        for category, expected in expectations.items():
            with self.subTest(category=category):
                first = run_probe("list", category)
                second = run_probe("list", category)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(first.stdout, second.stdout)
                self.assertIn(expected, first.stdout)

    def test_show_supports_table_and_json(self):
        table = run_probe("show", "cache-latency.l2-latency")
        json_result = run_probe("show", "gb10", "-o", "json")

        self.assertEqual(table.returncode, 0, table.stderr)
        self.assertIn("cache-latency.l2-latency", table.stdout)
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        self.assertEqual(json.loads(json_result.stdout)["id"], "gb10")

    def test_subcommand_help_has_no_configuration_dependency(self):
        for arguments in (("help", "plan"), ("plan", "--help")):
            with self.subTest(arguments=arguments):
                result = run_probe(*arguments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--select", result.stdout)

    def test_unknown_show_is_structured_configuration_error(self):
        result = run_probe("show", "unknown")

        self.assertEqual(result.returncode, 3)
        self.assertIn("error:", result.stderr)
        self.assertIn("probe list", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
