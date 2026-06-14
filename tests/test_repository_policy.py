import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CONTRACT = ROOT / "docs" / "design" / "repository-layout.md"
SKELETON_READMES = (
    "arm64_probe/README.md",
    "configs/README.md",
    "configs/platforms/README.md",
    "configs/experiments/README.md",
    "configs/profiles/README.md",
    "tests/unit/README.md",
    "tests/contract/README.md",
    "tests/fixtures/README.md",
    "tests/integration/README.md",
    "docs/methodology/README.md",
    "docs/references/README.md",
    "docs/results/README.md",
    "docs/roadmap/README.md",
)


def ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        result.check_returncode()
    return result.returncode == 0


class RepositoryPolicyTests(unittest.TestCase):
    def test_temporary_paths_are_ignored(self):
        for path in (
            "build/bin/chase_pmu",
            "tools/bin/chase_pmu",
            "bin/chase_pmu",
            "backup/archive.tar",
            "results/runs/example/manifest.json",
            "results/.locks/active.lock",
            "results/.recovery/session.json",
            ".venv/bin/python",
            ".pytest_cache/v/cache/nodeids",
            ".ruff_cache/content",
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

    def test_root_local_directory_names_are_trackable_below_release_paths(self):
        for path in (
            "results/baselines/v1.0/build/environment.json",
            "results/baselines/v1.0/tools/bin/helper",
            "docs/assets/v1.0/bin/cache-latency.svg",
            "docs/assets/v2.0/backup/chart.svg",
            "docs/assets/v1.0/.venv/environment.json",
            "results/baselines/v1.0/.pytest_cache/summary.json",
            "results/baselines/v1.0/.ruff_cache/summary.json",
            "docs/assets/v1.0/results/runs/manifest.json",
            "docs/assets/v1.0/results/.locks/active.lock",
            "docs/assets/v1.0/results/.recovery/session.json",
        ):
            with self.subTest(path=path):
                self.assertFalse(ignored(path))

    def test_git_errors_are_not_treated_as_trackable(self):
        with self.assertRaises(subprocess.CalledProcessError) as error:
            ignored("../outside")

        self.assertGreater(error.exception.returncode, 1)

    def test_policy_documents_exist(self):
        for path in (
            "results/README.md",
            "results/baselines/v1.0/README.md",
            "docs/assets/v1.0/README.md",
        ):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())

    def test_entry_documents_describe_current_contract(self):
        agents = (ROOT / "AGENTS.md").read_text()
        readme = (ROOT / "README.md").read_text()
        for phrase in ("make build", "make check", "build/bin", "legacy"):
            with self.subTest(document="AGENTS.md", phrase=phrase):
                self.assertIn(phrase, agents)
        for phrase in ("arm64-uarch-probe", "GB10", "make help", "legacy"):
            with self.subTest(document="README.md", phrase=phrase):
                self.assertIn(phrase, readme)

    def test_v1_skeleton_readmes_exist_and_are_trackable(self):
        for path in SKELETON_READMES:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())
                self.assertFalse(ignored(path))

    def test_layout_contract_classifies_repository_boundaries(self):
        layout = LAYOUT_CONTRACT.read_text()
        for phrase in (
            "Frozen Historical Evidence",
            "`runner/run_pmu*.sh`",
            "`data/`",
            "Transitional Paths",
            "`analysis/`",
            "`baseline/`",
            "`runner/cache_info_*.sh`",
            "v1.0-Owned Paths",
            "`arm64_probe/`",
            "`configs/`",
            "`tests/unit/`",
            "`docs/methodology/`",
            "`git mv`",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, layout)

    def test_entry_documents_link_to_layout_contract(self):
        for path in ("AGENTS.md", "README.md", "docs/design/repository-contract.md"):
            with self.subTest(path=path):
                self.assertIn(
                    "docs/design/repository-layout.md",
                    (ROOT / path).read_text(),
                )


if __name__ == "__main__":
    unittest.main()
