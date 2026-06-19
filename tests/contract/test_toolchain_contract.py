"""Contract tests for the Python toolchain pin.

The repository is pinned to CPython 3.13.13 managed by `uv`. These tests
enforce the four structural invariants every checkout must satisfy:

1. `.python-version` exists and pins the exact interpreter.
2. `pyproject.toml` declares the same interpreter as a hard requirement.
3. `uv.lock` exists, is committed, and locks to the same interpreter.
4. The Makefile routes every Python invocation through `uv run`.

The tests do not invoke `uv`; they only read the workspace files. The
runtime side of the contract (`.venv/`, `uv sync`) is exercised through
`make sync` and `make check` by the developer or CI.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PYTHON = "3.13.13"
PYTHON_RE = re.compile(r"^3\.13\.13$")


class PythonVersionPinTests(unittest.TestCase):
    def test_python_version_file_pins_to_3_13_13(self):
        path = ROOT / ".python-version"
        self.assertTrue(path.exists(), "missing .python-version")
        value = path.read_text().strip()
        self.assertRegex(value, PYTHON_RE, f"unexpected .python-version: {value!r}")
        self.assertEqual(value, EXPECTED_PYTHON)

    def test_pyproject_declares_3_13_13_as_requires_python(self):
        path = ROOT / "pyproject.toml"
        self.assertTrue(path.exists(), "missing pyproject.toml")
        payload = tomllib.loads(path.read_text())
        self.assertEqual(
            payload["project"]["requires-python"],
            "==3.13.13",
        )
        self.assertEqual(
            payload["project"]["classifiers"],
            [
                "Development Status :: 3 - Alpha",
                "Environment :: Console",
                "Intended Audience :: Science/Research",
                "Operating System :: MacOS",
                "Operating System :: POSIX :: Linux",
                "Programming Language :: Python :: 3",
                "Programming Language :: Python :: 3.13",
                "Topic :: Scientific/Engineering",
            ],
        )

    def test_pyproject_allows_matplotlib_only(self):
        """Phase 4 adds matplotlib for figure generation (Agg backend).

        The control layer (planning, environment, execution) still uses
        only the standard library. matplotlib is the sole allowed runtime
        dependency, required by the analysis/report subsystem.
        """
        payload = tomllib.loads((ROOT / "pyproject.toml").read_text())
        deps = payload["project"]["dependencies"]
        self.assertEqual(len(deps), 1, f"expected exactly 1 dependency, got {len(deps)}")
        self.assertIn("matplotlib", deps[0], f"unexpected dependency: {deps[0]}")

    def test_pyproject_pins_uv_managed_workspace(self):
        payload = tomllib.loads((ROOT / "pyproject.toml").read_text())
        tool_uv = payload.get("tool", {}).get("uv", {})
        self.assertTrue(tool_uv.get("managed"), "uv must manage the workspace")
        self.assertFalse(
            tool_uv.get("package", True),
            "uv package=false is required so the venv provisions only the interpreter",
        )


class UvLockfileTests(unittest.TestCase):
    def test_uv_lock_exists_and_pins_3_13_13(self):
        path = ROOT / "uv.lock"
        self.assertTrue(path.exists(), "uv.lock must be committed")
        text = path.read_text()
        self.assertIn('requires-python = "==3.13.13"', text)
        self.assertIn("arm64-uarch-probe", text)

    def test_uv_lock_contains_matplotlib_and_its_dependencies(self):
        """Phase 4 adds matplotlib; uv.lock now carries its dependency tree.

        Only the workspace package name ('arm64-uarch-probe') and
        matplotlib-related packages are expected. Any other addition must
        be deliberate and reviewed.
        """
        text = (ROOT / "uv.lock").read_text()
        known = {"arm64-uarch-probe", "matplotlib", "contourpy", "cycler",
                  "fonttools", "kiwisolver", "numpy", "packaging", "pillow",
                  "pyparsing", "python-dateutil", "six"}
        self.assertIn("matplotlib", text, "matplotlib must be in lockfile")
        for pkg in known:
            self.assertIn(f'name = "{pkg}"', text,
                          f"expected package {pkg} in uv.lock")


class MakefileUvIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (ROOT / "Makefile").read_text()
        self.lines = self.text.splitlines()

    def test_makefile_defines_uv_and_uv_run(self):
        self.assertIn("UV ?= uv", self.lines)
        self.assertIn("UV_RUN := $(UV) run --no-sync", self.lines)

    def test_makefile_routes_python_through_uv_run(self):
        for forbidden in (
            "python3 -m unittest",
            "python3 scripts/legacy_manifest.py",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text, f"legacy {forbidden!r} must be replaced by $(UV_RUN) python")

    def test_makefile_exposes_sync_and_clean_venv_targets(self):
        self.assertIn("sync:", self.lines)
        self.assertIn("clean-venv:", self.lines)
        self.assertIn("\t$(UV) sync", self.text)
        self.assertIn("rm -rf .venv", self.text)

    def test_makefile_help_advertises_uv_managed_targets(self):
        for marker in ("sync", "clean-venv", "(uv-managed)"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_makefile_avoids_explicit_conda_or_anaconda_paths(self):
        for forbidden in ("/opt/homebrew/bin/python", "anaconda3/bin/python"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.text)


class RuntimeInterpreterTests(unittest.TestCase):
    """Only runs when `uv` and `.venv/` are present.

    Skipped automatically otherwise so the test is harmless on a freshly
    cloned repo that has not yet executed `make sync`.
    """

    def setUp(self) -> None:
        self.venv_python = ROOT / ".venv" / "bin" / "python"
        if not self.venv_python.exists():
            self.skipTest(".venv/ not yet provisioned (run `make sync`)")

    def test_venv_interpreter_matches_pinned_version(self):
        import subprocess
        import sys

        result = subprocess.run(
            [str(self.venv_python), "--version"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": str(self.venv_python.parent) + os.pathsep + os.environ.get("PATH", "")},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        # Output looks like "Python 3.13.13".
        self.assertIn("3.13.13", result.stdout)

    def test_venv_executable_does_not_resolve_to_conda(self):
        result = subprocess.run(
            [str(self.venv_python), "-c", "import sys; print(sys.executable)"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.venv_python.parent), result.stdout)
        for forbidden in ("anaconda", "conda", "Homebrew"):
            self.assertNotIn(forbidden, result.stdout)


class GitignoreExcludesVenvTests(unittest.TestCase):
    def test_gitignore_excludes_local_venv(self):
        text = (ROOT / ".gitignore").read_text()
        self.assertIn("/.venv/", text)


if __name__ == "__main__":
    unittest.main()
