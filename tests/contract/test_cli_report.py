"""CLI contract tests for probe report."""
import subprocess
import unittest
from pathlib import Path

PROBE = Path(__file__).resolve().parents[2] / "probe"


class CliReportCommandTests(unittest.TestCase):
    def test_report_help(self):
        result = subprocess.run(
            [str(PROBE), "report", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--analysis", result.stdout)

    def test_report_missing_analysis_returns_error(self):
        result = subprocess.run(
            [str(PROBE), "report"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_report_dash_o_accepted(self):
        result = subprocess.run(
            [str(PROBE), "report", "--help"],
            capture_output=True, text=True,
        )
        self.assertIn("-o", result.stdout)
