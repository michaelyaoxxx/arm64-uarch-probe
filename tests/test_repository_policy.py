import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=ROOT,
    )
    return result.returncode == 0


class RepositoryPolicyTests(unittest.TestCase):
    def test_temporary_paths_are_ignored(self):
        for path in (
            "build/bin/chase_pmu",
            "results/runs/example/manifest.json",
            "results/.locks/active.lock",
            "results/.recovery/session.json",
            ".venv/bin/python",
            "arm64_probe/__pycache__/module.pyc",
        ):
            with self.subTest(path=path):
                self.assertTrue(ignored(path))

    def test_release_evidence_is_not_ignored(self):
        for path in (
            "results/baselines/v1.0/manifest.json",
            "docs/assets/v1.0/cache-latency.svg",
        ):
            with self.subTest(path=path):
                self.assertFalse(ignored(path))

    def test_policy_documents_exist(self):
        for path in (
            "results/README.md",
            "results/baselines/v1.0/README.md",
            "docs/assets/v1.0/README.md",
        ):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
