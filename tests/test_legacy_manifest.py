import copy
import hashlib
import json
import os
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
    def git_in(cls, root, *args, input_text=None):
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            input=input_text,
        )

    @classmethod
    def git(cls, *args, input_text=None):
        return cls.git_in(cls.fixture_root, *args, input_text=input_text)

    def setUp(self):
        for replacement in self.git("replace", "-l").stdout.splitlines():
            self.git("replace", "-d", replacement)
        self.git("reset", "--hard", "-q", self.fixture_commit)
        self.write_fixture_manifest(self.fixture_payload)
        for name in ("generated.json", "target.sh"):
            (self.fixture_root / name).unlink(missing_ok=True)
        shutil.rmtree(self.fixture_root / "data" / "sample-real", ignore_errors=True)

    def run_script(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            env=env,
        )

    def run_fixture_script(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(self.fixture_script), *args],
            cwd=self.fixture_root,
            capture_output=True,
            text=True,
            env=env,
        )

    def create_foreign_repository(self, root):
        (root / "runner").mkdir()
        (root / "data" / "sample" / "raw").mkdir(parents=True)
        (root / "runner" / "run_pmu_v1.sh").write_bytes(
            (self.fixture_root / "runner" / "run_pmu_v1.sh").read_bytes()
        )
        (root / "data" / "sample" / "raw" / "run.txt").write_bytes(
            (self.fixture_root / "data" / "sample" / "raw" / "run.txt").read_bytes()
        )
        self.git_in(root, "init", "-q")
        self.git_in(root, "config", "user.name", "Foreign Repository")
        self.git_in(root, "config", "user.email", "foreign@example.invalid")
        self.git_in(root, "add", "runner", "data")
        self.git_in(root, "commit", "-qm", "foreign baseline")
        return self.git_in(root, "rev-parse", "HEAD").stdout.strip()

    def redirected_git_environment(self, foreign_root):
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_DIR": str(foreign_root / ".git"),
                "GIT_WORK_TREE": str(self.fixture_root),
                "GIT_COMMON_DIR": str(foreign_root / ".git"),
                "GIT_OBJECT_DIRECTORY": str(foreign_root / ".git" / "objects"),
                "GIT_INDEX_FILE": str(foreign_root / ".git" / "index"),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.worktree",
                "GIT_CONFIG_VALUE_0": str(self.fixture_root),
            }
        )
        return environment

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
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            changed_path = temporary_root / "changed.sh"
            changed_path.write_text("#!/bin/sh\n# mutation\n", encoding="utf-8")
            manifest = {
                "source_commit": "test",
                "files": {str(changed_path.resolve()): "0" * 64},
            }
            changed_manifest = Path(temporary_directory) / "manifest.json"
            changed_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            result = self.run_script(
                "verify",
                "--manifest",
                str(changed_manifest.resolve()),
            )

        self.assert_concise_failure(result, "digest mismatch")

    def test_external_manifest_verifies_absolute_path_digest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            checked_path = temporary_root / "checked.txt"
            checked_path.write_text("checked\n", encoding="utf-8")
            payload = {
                "source_commit": "ad-hoc",
                "files": {
                    str(checked_path.resolve()): hashlib.sha256(
                        checked_path.read_bytes()
                    ).hexdigest()
                },
            }
            external_manifest = temporary_root / "manifest.json"
            external_manifest.write_text(json.dumps(payload), encoding="utf-8")
            environment = os.environ.copy()
            environment.update(
                {
                    "GIT_DIR": str(temporary_root / "not-a-repository"),
                    "GIT_WORK_TREE": str(temporary_root / "not-a-worktree"),
                }
            )
            result = self.run_script(
                "verify",
                "--manifest",
                str(external_manifest.resolve()),
                env=environment,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("external manifest digests verified", result.stdout)

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

        self.assert_concise_failure(result, "invalid manifest:")

    def test_canonical_manifest_requires_full_source_oid(self):
        for source_commit in (
            "HEAD",
            self.fixture_commit[:12],
            "g" * 40,
            "\ud800",
        ):
            with self.subTest(source_commit=source_commit):
                payload = copy.deepcopy(self.fixture_payload)
                payload["source_commit"] = source_commit
                self.write_fixture_manifest(payload)

                result = self.run_fixture_script("verify")

                self.assert_concise_failure(
                    result, "invalid manifest: source_commit must be a 40-hex OID"
                )

    def test_canonical_manifest_accepts_uppercase_source_oid(self):
        payload = copy.deepcopy(self.fixture_payload)
        payload["source_commit"] = self.fixture_commit.upper()
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("legacy manifest verified", result.stdout)

    def test_canonical_manifest_rejects_source_commit_not_ancestor(self):
        unrelated_commit = self.git(
            "commit-tree", "HEAD^{tree}", input_text="unrelated\n"
        ).stdout.strip()
        payload = copy.deepcopy(self.fixture_payload)
        payload["source_commit"] = unrelated_commit
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "source_commit is not an ancestor of HEAD")

    def test_canonical_manifest_rejects_different_source_tree(self):
        runner_path = self.fixture_root / "runner" / "run_pmu_v1.sh"
        runner_path.write_text("#!/bin/sh\n# different commit\n", encoding="utf-8")
        self.git("add", "runner/run_pmu_v1.sh")
        self.git("commit", "-qm", "different legacy tree")
        different_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", self.fixture_commit, "--", "runner/run_pmu_v1.sh")
        payload = copy.deepcopy(self.fixture_payload)
        payload["source_commit"] = different_commit
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "source tree digest mismatch:")

    def test_canonical_manifest_rejects_source_tree_symlink(self):
        runner_path = self.fixture_root / "runner" / "run_pmu_v1.sh"
        runner_path.unlink()
        runner_path.symlink_to("../data/sample/raw/run.txt")
        self.git("add", "runner/run_pmu_v1.sh")
        self.git("commit", "-qm", "symlink legacy entry")
        symlink_commit = self.git("rev-parse", "HEAD").stdout.strip()
        payload = copy.deepcopy(self.fixture_payload)
        payload["source_commit"] = symlink_commit
        payload["files"]["runner/run_pmu_v1.sh"] = self.fixture_files[
            "data/sample/raw/run.txt"
        ]
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(
            result, "source tree entry is not a regular file:"
        )

    def test_canonical_manifest_rejects_working_tree_symlink(self):
        runner_path = self.fixture_root / "runner" / "run_pmu_v1.sh"
        target = self.fixture_root / "target.sh"
        target.write_bytes(runner_path.read_bytes())
        runner_path.unlink()
        runner_path.symlink_to(target)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(
            result, "working tree entry is not a regular file:"
        )

    def test_canonical_manifest_rejects_parent_directory_symlink(self):
        sample = self.fixture_root / "data" / "sample"
        sample_real = self.fixture_root / "data" / "sample-real"
        sample.rename(sample_real)
        sample.symlink_to(sample_real.name, target_is_directory=True)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(
            result, "working tree path contains symlink:"
        )

    def test_canonical_manifest_ignores_git_replace(self):
        runner_path = self.fixture_root / "runner" / "run_pmu_v1.sh"
        runner_path.write_text("#!/bin/sh\n# replaced commit\n", encoding="utf-8")
        self.git("add", "runner/run_pmu_v1.sh")
        self.git("commit", "-qm", "replace target")
        replaced_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", self.fixture_commit, "--", "runner/run_pmu_v1.sh")
        self.git("replace", replaced_commit, self.fixture_commit)
        payload = copy.deepcopy(self.fixture_payload)
        payload["source_commit"] = replaced_commit
        self.write_fixture_manifest(payload)

        result = self.run_fixture_script("verify")

        self.assert_concise_failure(result, "source tree digest mismatch:")

    def test_canonical_manifest_ignores_redirected_git_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            foreign_root = Path(temporary_directory)
            foreign_commit = self.create_foreign_repository(foreign_root)
            payload = copy.deepcopy(self.fixture_payload)
            payload["source_commit"] = foreign_commit
            self.write_fixture_manifest(payload)

            result = self.run_fixture_script(
                "verify",
                env=self.redirected_git_environment(foreign_root),
            )

        self.assert_concise_failure(result, "invalid source_commit:")

    def test_write_ignores_redirected_git_environment(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            foreign_root = Path(temporary_directory)
            foreign_commit = self.create_foreign_repository(foreign_root)

            result = self.run_fixture_script(
                "write",
                "--manifest",
                "generated.json",
                "--source-commit",
                foreign_commit,
                env=self.redirected_git_environment(foreign_root),
            )

        self.assert_concise_failure(result, "invalid source_commit:")

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

    def test_write_rejects_current_bytes_that_differ_from_source_tree(self):
        (self.fixture_root / "runner" / "run_pmu_v1.sh").write_text(
            "#!/bin/sh\n# current mutation\n", encoding="utf-8"
        )

        result = self.run_fixture_script(
            "write",
            "--manifest",
            "generated.json",
            "--source-commit",
            self.fixture_commit,
        )

        self.assert_concise_failure(
            result, "current file digest differs from source_commit:"
        )

    def test_duplicate_json_object_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            checked_path = temporary_root / "checked.txt"
            checked_path.write_text("checked\n", encoding="utf-8")
            encoded_path = json.dumps(str(checked_path.resolve()))
            digest = hashlib.sha256(checked_path.read_bytes()).hexdigest()
            manifests = (
                (
                    '{"source_commit":"first","source_commit":"second",'
                    f'"files":{{{encoded_path}:"{digest}"}}}}'
                ),
                (
                    '{"source_commit":"ad-hoc","files":{'
                    f'{encoded_path}:"{digest}",{encoded_path}:"{digest}"}}}}'
                ),
            )
            for index, raw_manifest in enumerate(manifests):
                with self.subTest(index=index):
                    external_manifest = temporary_root / f"manifest-{index}.json"
                    external_manifest.write_text(raw_manifest, encoding="utf-8")
                    result = self.run_script(
                        "verify", "--manifest", str(external_manifest.resolve())
                    )
                    self.assert_concise_failure(
                        result, "invalid manifest: duplicate key:"
                    )

    def test_invalid_utf8_and_json_are_reported_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            for name, raw_manifest in (
                ("invalid-utf8.json", b"\xff"),
                ("invalid-json.json", b"{"),
            ):
                with self.subTest(name=name):
                    external_manifest = temporary_root / name
                    external_manifest.write_bytes(raw_manifest)
                    result = self.run_script(
                        "verify", "--manifest", str(external_manifest.resolve())
                    )
                    self.assert_concise_failure(result, "invalid manifest:")

    def test_external_manifest_schema_error_is_concise(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            external_manifest = Path(temporary_directory) / "manifest.json"
            external_manifest.write_text(
                json.dumps({"source_commit": "ad-hoc", "files": []}),
                encoding="utf-8",
            )
            result = self.run_script(
                "verify", "--manifest", str(external_manifest.resolve())
            )

        self.assert_concise_failure(result, "invalid manifest:")


if __name__ == "__main__":
    unittest.main()
