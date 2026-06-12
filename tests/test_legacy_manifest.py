import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "legacy_manifest.py"
MANIFEST = REPO_ROOT / "legacy" / "manifest.json"


class LegacyManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_directory = tempfile.TemporaryDirectory()
        cls.fixture_root = Path(cls.fixture_directory.name)
        cls.fixture_script = cls.fixture_root / "scripts" / "legacy_manifest.py"
        cls.fixture_manifest = cls.fixture_root / "legacy" / "manifest.json"

        cls.fixture_script.parent.mkdir()
        cls.fixture_manifest.parent.mkdir()
        (cls.fixture_root / "runner").mkdir()
        (cls.fixture_root / "data" / "sample" / "raw").mkdir(parents=True)
        shutil.copy2(SCRIPT, cls.fixture_script)
        (cls.fixture_root / "runner" / "run_pmu_v1.sh").write_text(
            "#!/bin/sh\n", encoding="utf-8"
        )
        (cls.fixture_root / "data" / "sample" / "raw" / "run.txt").write_text(
            "sample\n", encoding="utf-8"
        )
        (cls.fixture_root / "README.md").write_text("untracked\n", encoding="utf-8")

        cls.git("init", "-q")
        cls.git("config", "user.name", "Legacy Manifest Test")
        cls.git("config", "user.email", "legacy-manifest@example.invalid")
        cls.git("add", "runner", "data")
        cls.git("commit", "-qm", "fixture baseline")
        cls.fixture_commit = cls.git("rev-parse", "HEAD").stdout.strip()
        cls.fixture_files = {
            path: hashlib.sha256((cls.fixture_root / path).read_bytes()).hexdigest()
            for path in (
                "data/sample/raw/run.txt",
                "runner/run_pmu_v1.sh",
            )
        }
        cls.fixture_payload = {
            "source_commit": cls.fixture_commit,
            "files": cls.fixture_files,
        }

    @classmethod
    def tearDownClass(cls):
        cls.fixture_directory.cleanup()

    @classmethod
    def git(cls, *args, input_text=None):
        return subprocess.run(
            ["git", *args],
            cwd=cls.fixture_root,
            check=True,
            capture_output=True,
            text=True,
            input=input_text,
        )

    def setUp(self):
        self.write_fixture_manifest(self.fixture_payload)
        (self.fixture_root / "generated.json").unlink(missing_ok=True)

    def run_script(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )

    def run_fixture_script(self, *args):
        return subprocess.run(
            [sys.executable, str(self.fixture_script), *args],
            cwd=self.fixture_root,
            capture_output=True,
            text=True,
        )

    def write_fixture_manifest(self, payload):
        self.fixture_manifest.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def assert_concise_failure(self, result, message):
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

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
                "verify",
                "--manifest",
                str(changed_manifest.resolve()),
                "--allow-custom-manifest",
            )

        self.assert_concise_failure(result, "digest mismatch")

    def test_custom_manifest_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            custom_manifest = Path(temporary_directory) / "manifest.json"
            shutil.copy2(MANIFEST, custom_manifest)
            result = self.run_script("verify", "--manifest", str(custom_manifest))

        self.assert_concise_failure(
            result, "custom manifest requires --allow-custom-manifest"
        )

    def test_canonical_manifest_rejects_missing_inventory_entry(self):
        payload = copy.deepcopy(self.fixture_payload)
        payload["files"].pop(next(iter(payload["files"])))
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "inventory mismatch: missing entries:")

    def test_canonical_manifest_rejects_empty_inventory(self):
        payload = copy.deepcopy(self.fixture_payload)
        payload["files"] = {}
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "inventory mismatch: missing entries:")

    def test_canonical_manifest_rejects_extra_inventory_entry(self):
        payload = copy.deepcopy(self.fixture_payload)
        payload["files"]["README.md"] = hashlib.sha256(b"untracked\n").hexdigest()
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "inventory mismatch: extra entries:")

    def test_malformed_schema_is_reported_without_traceback(self):
        malformed_payloads = (
            [],
            {"files": self.fixture_files},
            {"source_commit": self.fixture_commit, "files": []},
            {
                "source_commit": self.fixture_commit,
                "files": {"runner/run_pmu_v1.sh": "not-a-sha256"},
            },
            {
                "source_commit": self.fixture_commit,
                "files": self.fixture_files,
                "unexpected": True,
            },
        )
        for payload in malformed_payloads:
            with self.subTest(payload=payload):
                self.write_fixture_manifest(payload)
                result = self.run_fixture_script("verify")
                self.assert_concise_failure(result, "invalid manifest:")

    def test_write_rejects_source_that_is_not_commit(self):
        result = self.run_fixture_script(
            "write", "--manifest", "generated.json", "--source-commit", "not-a-commit"
        )

        self.assert_concise_failure(result, "invalid source_commit:")

    def test_write_records_resolved_source_commit(self):
        result = self.run_fixture_script(
            "write", "--manifest", "generated.json", "--source-commit", "HEAD"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = json.loads(
            (self.fixture_root / "generated.json").read_text(encoding="utf-8")
        )

        self.assertEqual(generated["source_commit"], self.fixture_commit)

    def test_canonical_manifest_rejects_source_that_is_not_commit(self):
        payload = copy.deepcopy(self.fixture_payload)
        payload["source_commit"] = "not-a-commit"
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "invalid source_commit:")

    def test_canonical_manifest_rejects_source_commit_not_ancestor(self):
        unrelated_commit = self.git(
            "commit-tree", "HEAD^{tree}", input_text="unrelated\n"
        ).stdout.strip()
        payload = copy.deepcopy(self.fixture_payload)
        payload["source_commit"] = unrelated_commit
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "source_commit is not an ancestor of HEAD")

    def test_canonical_manifest_rejects_unsafe_paths(self):
        tracked_path = "runner/run_pmu_v1.sh"
        digest = self.fixture_files[tracked_path]
        unsafe_paths = (
            str((self.fixture_root / tracked_path).resolve()),
            "data/../runner/run_pmu_v1.sh",
            "runner//run_pmu_v1.sh",
        )
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                payload = copy.deepcopy(self.fixture_payload)
                payload["files"][unsafe_path] = digest
                self.write_fixture_manifest(payload)
                result = self.run_fixture_script("verify")
                self.assert_concise_failure(
                    result, "invalid manifest: path must be normalized repo-relative:"
                )

    def test_custom_manifest_rejects_unsafe_and_untracked_paths(self):
        tracked_path = "runner/run_pmu_v1.sh"
        digest = self.fixture_files[tracked_path]
        unsafe_paths = (
            str((self.fixture_root / tracked_path).resolve()),
            "data/../runner/run_pmu_v1.sh",
            "README.md",
        )
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path):
                payload = {
                    "source_commit": self.fixture_commit,
                    "files": {unsafe_path: digest},
                }
                with tempfile.TemporaryDirectory() as temporary_directory:
                    custom_manifest = Path(temporary_directory) / "manifest.json"
                    custom_manifest.write_text(json.dumps(payload), encoding="utf-8")
                    result = self.run_fixture_script(
                        "verify",
                        "--manifest",
                        str(custom_manifest),
                        "--allow-custom-manifest",
                    )
                self.assert_concise_failure(result, "invalid manifest:")


if __name__ == "__main__":
    unittest.main()
