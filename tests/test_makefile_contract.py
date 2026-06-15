import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TARGETS = [
    "src/chase_pmu/chase_pmu_v2.7.3.c -> build/bin/chase_pmu [Linux]",
    "src/evict_slc/evict_slc_v1.2.c -> build/bin/evict_slc [Linux,Darwin]",
    "src/chase_migrate/chase_migrate_v1.0.c -> build/bin/chase_migrate [Linux]",
]


def make(
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *arguments],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def make_with_uname(
    system: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        fake_uname = Path(tmp) / "uname"
        fake_uname.write_text(f"#!/bin/sh\nprintf '%s\\n' '{system}'\n")
        fake_uname.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{tmp}{os.pathsep}{env['PATH']}"
        return make(*arguments, env=env)


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

    def test_phase1_cli_and_check_targets_are_thin_wrappers(self):
        help_result = make("help")
        probe = make("-n", "probe", "PROBE_ARGS=list targets")
        probe_help = make("-n", "probe-help")
        phase1_check = make("-n", "phase1-check")
        doctor = make("-n", "doctor")
        phase2_check = make("-n", "phase2-check")

        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for target in ("probe", "probe-help", "phase1-check", "doctor", "phase2-check"):
            with self.subTest(target=target):
                self.assertIn(target, help_result.stdout)
        self.assertEqual(probe.stdout.strip(), "./probe list targets")
        self.assertEqual(probe_help.stdout.strip(), "./probe --help")
        self.assertIn("python3 -m unittest discover", phase1_check.stdout)
        self.assertIn("python3 scripts/legacy_manifest.py verify", phase1_check.stdout)
        self.assertNotIn("build/bin", phase1_check.stdout)
        self.assertEqual(doctor.stdout.strip(), "./probe doctor")
        self.assertIn("python3 -m unittest discover", phase2_check.stdout)
        self.assertIn("python3 scripts/legacy_manifest.py verify", phase2_check.stdout)
        self.assertNotIn("build/bin", phase2_check.stdout)
        self.assertNotIn("sudo", phase2_check.stdout)
        self.assertNotIn("/sys/", phase2_check.stdout)

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
        result = make_with_uname("Linux", "-B", "-n", "build")
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        for source in (
            "src/chase_pmu/chase_pmu_v2.7.3.c",
            "src/evict_slc/evict_slc_v1.2.c",
            "src/chase_migrate/chase_migrate_v1.0.c",
        ):
            with self.subTest(source=source):
                self.assertIn(source, output)

    def test_command_line_cannot_spoof_detected_platform(self):
        spoofed = "Linux" if platform.system() != "Linux" else "Darwin"
        result = make("-B", "-n", "build", f"HOST_OS={spoofed}", f"UNAME_S={spoofed}")
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        if platform.system() == "Linux":
            self.assertIn("src/chase_pmu/chase_pmu_v2.7.3.c", output)
        else:
            self.assertNotIn("src/chase_pmu/chase_pmu_v2.7.3.c", output)

    def test_unknown_host_is_rejected(self):
        result = make_with_uname("FreeBSD", "-n", "build")
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 2, output)
        self.assertIn("unsupported host: FreeBSD", output)

    def test_clean_cannot_be_redirected_by_command_line(self):
        result = make("-n", "clean", f"BUILD_DIR={ROOT}")
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        self.assertNotIn(str(ROOT), output)
        self.assertIn("rm -rf build", output)

    def test_overlapping_linux_build_goals_compile_each_probe_once(self):
        result = make_with_uname(
            "Linux",
            "-B",
            "-j8",
            "-n",
            "build",
            "build-linux",
        )
        output = result.stdout + result.stderr

        self.assertEqual(result.returncode, 0, output)
        for source in (
            "src/chase_pmu/chase_pmu_v2.7.3.c",
            "src/evict_slc/evict_slc_v1.2.c",
            "src/chase_migrate/chase_migrate_v1.0.c",
        ):
            with self.subTest(source=source):
                self.assertEqual(output.count(source), 1, output)


if __name__ == "__main__":
    unittest.main()
