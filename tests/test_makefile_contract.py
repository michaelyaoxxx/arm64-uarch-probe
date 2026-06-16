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
        for target in ("probe", "probe-help", "phase1-check", "doctor", "phase2-check", "sync", "clean-venv"):
            with self.subTest(target=target):
                self.assertIn(target, help_result.stdout)
        # Probe/doctor wrappers now route through `uv run` against the
        # pinned CPython 3.13.13 interpreter.
        self.assertIn("uv run --no-sync python ./probe list targets", probe.stdout)
        self.assertIn("uv run --no-sync python ./probe --help", probe_help.stdout)
        self.assertIn("uv run --no-sync python -m unittest discover", phase1_check.stdout)
        self.assertIn("uv run --no-sync python scripts/legacy_manifest.py verify", phase1_check.stdout)
        self.assertNotIn("build/bin", phase1_check.stdout)
        self.assertIn("uv run --no-sync python ./probe doctor", doctor.stdout)
        self.assertIn("uv run --no-sync python -m unittest discover", phase2_check.stdout)
        self.assertIn("uv run --no-sync python scripts/legacy_manifest.py verify", phase2_check.stdout)
        self.assertNotIn("build/bin", phase2_check.stdout)
        self.assertNotIn("sudo", phase2_check.stdout)
        self.assertNotIn("/sys/", phase2_check.stdout)
        # The legacy raw-python3 entry points must be gone.
        for forbidden in (
            "python3 -m unittest",
            "python3 scripts/legacy_manifest.py",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, phase1_check.stdout + phase2_check.stdout)

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


class Phase3MakefileContractTests(unittest.TestCase):
    """Phase 3 Makefile targets must be thin uv-managed wrappers."""

    def test_phase3_targets_exist_and_are_uv_managed(self):
        """make smoke and make phase3-check must exist and use uv run."""
        help_result = make("help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("smoke", help_result.stdout)
        self.assertIn("phase3-check", help_result.stdout)

        for target in ("smoke", "phase3-check"):
            result = make("-n", target)
            with self.subTest(target=target):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("uv run --no-sync python", result.stdout)

    def test_phase3_targets_have_no_parsing_or_mutation_logic(self):
        """smoke and phase3-check recipes must contain no platform branch or parsing."""
        for target in ("smoke", "phase3-check"):
            result = make("-n", target)
            with self.subTest(target=target):
                output = result.stdout + result.stderr
                for forbidden in (
                    "ifdef",
                    "ifeq",
                    "ifndef",
                    "python3 ",
                    "sudo",
                    "/sys/",
                    "awk",
                    "jq",
                ):
                    self.assertNotIn(
                        forbidden, output,
                        f"{target} recipe contains forbidden token: {forbidden!r}"
                    )

    def test_phase3_help_advertises_targets(self):
        """make help should mention phase3-check and smoke."""
        result = make("help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("phase3-check", result.stdout)
        self.assertIn("smoke", result.stdout)


if __name__ == "__main__":
    unittest.main()
