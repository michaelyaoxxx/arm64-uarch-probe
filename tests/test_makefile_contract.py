import platform
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TARGETS = [
    "src/chase_pmu/chase_pmu_v2.7.3.c -> build/bin/chase_pmu [Linux]",
    "src/evict_slc/evict_slc_v1.2.c -> build/bin/evict_slc [Linux,Darwin]",
    "src/chase_migrate/chase_migrate_v1.0.c -> build/bin/chase_migrate [Linux]",
]


def make(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


class MakefileContractTests(unittest.TestCase):
    def test_help_lists_stable_phase0_targets(self):
        result = make("help")

        self.assertEqual(result.returncode, 0, result.stderr)
        for target in (
            "build",
            "build-linux",
            "check",
            "legacy-check",
            "show-targets",
        ):
            with self.subTest(target=target):
                self.assertIn(target, result.stdout)

    def test_show_targets_lists_exact_supported_probe_mappings(self):
        result = make("show-targets")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), EXPECTED_TARGETS)

    def test_build_linux_rejects_non_linux(self):
        if platform.system() == "Linux":
            self.skipTest("non-Linux contract")

        result = make("build-linux")

        self.assertEqual(result.returncode, 2)
        self.assertIn("build-linux requires Linux", result.stderr + result.stdout)

    def test_non_linux_build_dry_run_selects_evict_slc_and_honors_overrides(self):
        if platform.system() == "Linux":
            self.skipTest("non-Linux contract")

        result = make(
            "-B",
            "-n",
            "build",
            "CC=contract-cc",
            "CFLAGS=contract-cflags",
        )
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        self.assertIn(
            "contract-cc contract-cflags -o build/bin/evict_slc "
            "src/evict_slc/evict_slc_v1.2.c",
            output,
        )
        self.assertNotIn("src/chase_pmu/chase_pmu_v2.7.3.c", output)
        self.assertNotIn("src/chase_migrate/chase_migrate_v1.0.c", output)

    def test_linux_build_dry_run_selects_all_probes(self):
        result = make("-B", "-n", "build", "UNAME_S=Linux")
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        for source in (
            "src/chase_pmu/chase_pmu_v2.7.3.c",
            "src/evict_slc/evict_slc_v1.2.c",
            "src/chase_migrate/chase_migrate_v1.0.c",
        ):
            with self.subTest(source=source):
                self.assertIn(source, output)


if __name__ == "__main__":
    unittest.main()
