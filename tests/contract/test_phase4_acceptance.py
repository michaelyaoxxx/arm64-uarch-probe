"""Phase 4 acceptance contract tests."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = ROOT / "arm64_probe" / "analysis"


class Phase4ArchitectureBoundaryTests(unittest.TestCase):
    def test_no_platform_name_branch_in_analysis_modules(self):
        """No 'if platform == gb10' branches in analysis package."""
        for py_file in ANALYSIS_DIR.rglob("*.py"):
            if py_file.name == "__init__.py" and py_file.parent == ANALYSIS_DIR:
                continue
            text = py_file.read_text()
            lines = [
                l for l in text.split("\n")
                if "if" in l and ("gb10" in l.lower() or "m4" in l.lower())
            ]
            self.assertEqual(
                len(lines), 0,
                f"{py_file.relative_to(ROOT)} contains platform-name branch"
            )

    def test_analysis_package_has_no_sudo_or_mutation(self):
        """Analysis package must not reference sudo or MutationLock."""
        for py_file in ANALYSIS_DIR.rglob("*.py"):
            text = py_file.read_text()
            self.assertNotIn("sudo", text, f"{py_file.name} mentions sudo")
            self.assertNotIn("MutationLock", text, f"{py_file.name} mentions MutationLock")

    def test_matplotlib_is_in_dependencies(self):
        pyproject = ROOT / "pyproject.toml"
        text = pyproject.read_text()
        self.assertIn("matplotlib", text)


class Phase4MakefileTests(unittest.TestCase):
    def test_phase4_check_target_exists(self):
        makefile = ROOT / "Makefile"
        text = makefile.read_text()
        self.assertIn("phase4-check", text)


class Phase4CliCommandTests(unittest.TestCase):
    def test_analyze_and_report_in_help(self):
        import subprocess
        result = subprocess.run(
            [str(ROOT / "probe"), "--help"],
            capture_output=True, text=True,
        )
        self.assertIn("analyze", result.stdout)
        self.assertIn("report", result.stdout)
