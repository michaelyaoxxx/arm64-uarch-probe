import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "legacy_manifest.py"
MANIFEST = REPO_ROOT / "legacy" / "manifest.json"


class LegacyManifestTest(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def test_committed_manifest_verifies(self):
        result = self.run_script("verify")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("legacy manifest verified", result.stdout)

    def test_manifest_inventory_matches_tracked_legacy_files(self):
        tracked = subprocess.run(
            ["git", "ls-files", "runner/run_pmu*.sh", "data/**/*.txt"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(sorted(manifest["files"]), sorted(tracked))

    def test_changed_digest_fails_verification(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        changed_path = next(iter(manifest["files"]))
        manifest["files"][changed_path] = "0" * 64

        with tempfile.TemporaryDirectory() as temporary_directory:
            changed_manifest = Path(temporary_directory) / "manifest.json"
            changed_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_script(
                "verify", "--manifest", str(changed_manifest.resolve())
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
