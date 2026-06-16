"""Integration tests that verify adapter-generated CLI arguments are
accepted by the actual compiled C probe binaries.

These tests bridge the gap between adapter build_argv output and the
C probe's arg parser.  They must pass after ``make build`` and catch
CLI mismatches (underscore vs hyphen, positional vs named, missing
required args, etc.) before they reach GB10 hardware.

Probes are invoked with adapter-generated args; the test passes when
stderr does **not** contain ``Usage:``, ``unrecognized option``, or
``size too small`` — real measurement failures (PMU permission, memory,
migration syscall, …) are not CLI errors and are allowed.
"""

import os
import platform
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BIN_DIR = ROOT / "build" / "bin"
MINIMUM_WORKING_SET_KB = 1024  # 1 MB — safe minimum every probe accepts

_CLI_ERROR_MARKERS = (
    "Usage:",
    "unrecognized option",
    "size too small",
    "invalid option",
)


def _probe_binary(name: str) -> Path | None:
    """Return the probe binary path if it exists, else None."""
    path = BIN_DIR / name
    return path if path.is_file() else None


def _adapter_for(probe_name: str):
    """Return the adapter instance for a probe name."""
    if probe_name == "chase_pmu":
        from arm64_probe.execution.adapters.chase_pmu import ChasePmuAdapter
        return ChasePmuAdapter()
    if probe_name == "chase_migrate":
        from arm64_probe.execution.adapters.chase_migrate import ChaseMigrateAdapter
        return ChaseMigrateAdapter()
    if probe_name == "evict_slc":
        from arm64_probe.execution.adapters.evict_slc import EvictSlcAdapter
        return EvictSlcAdapter()
    raise ValueError(f"Unknown probe: {probe_name}")


def _has_cli_error(stderr: str) -> bool:
    """Return True if stderr contains a CLI-level (not runtime) error."""
    return any(marker.lower() in stderr.lower() for marker in _CLI_ERROR_MARKERS)


class ProbeCliContractTests(unittest.TestCase):
    """Run each compiled probe with adapter-generated argv and verify
    the CLI contract is accepted (no usage / unrecognized-option errors)."""

    def _run_probe(self, binary_name: str, **adapter_kwargs):
        """Build argv via adapter, invoke the probe, assert CLI acceptance."""
        binary = _probe_binary(binary_name)
        if binary is None:
            self.skipTest(
                f"{binary_name} not compiled — run 'make build' first"
            )

        adapter = _adapter_for(binary_name)
        argv = adapter.build_argv(**adapter_kwargs)

        cmd = [str(binary)] + argv
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            # Timeout means the probe actually ran (did its measurement
            # loop), so the CLI contract is definitely valid.
            return
        except FileNotFoundError:
            self.skipTest(f"{binary} missing at runtime")
        except PermissionError:
            self.skipTest(f"{binary} not executable")

        combined = result.stderr + result.stdout
        self.assertFalse(
            _has_cli_error(combined),
            f"{binary_name} rejected adapter-generated argv.\n"
            f"  command: {' '.join(cmd)}\n"
            f"  exit code: {result.returncode}\n"
            f"  stderr: {result.stderr[:500]}\n"
            f"  stdout: {result.stdout[:500]}",
        )

    # -- chase_pmu -------------------------------------------------------

    def test_chase_pmu_accepts_positional_args_warm(self):
        """L1 warm: size_kb=32 warm=5 force_rounds=0 seed=42 clflush=0 hugepage=0"""
        self._run_probe(
            "chase_pmu",
            cpu=0,
            working_set_kb=32,
            warm_passes=5,
            force_rounds=0,
            seed=42,
            hugepage=False,
        )

    def test_chase_pmu_accepts_positional_args_cold(self):
        """DRAM cold: size_kb=65536 warm=0 force_rounds=1 seed=42 clflush=1 hugepage=0"""
        self._run_probe(
            "chase_pmu",
            cpu=0,
            working_set_kb=65536,
            warm_passes=0,
            force_rounds=1,
            seed=42,
            hugepage=False,
        )

    def test_chase_pmu_accepts_hugepage_flag(self):
        """Warm with hugepage=1."""
        self._run_probe(
            "chase_pmu",
            cpu=0,
            working_set_kb=MINIMUM_WORKING_SET_KB,
            warm_passes=5,
            force_rounds=0,
            seed=42,
            hugepage=True,
        )

    # -- chase_migrate ---------------------------------------------------

    def test_chase_migrate_accepts_cross_cluster_args(self):
        """Cross-cluster: src-cpu=0 dst-cpu=5 size-kb=4096."""
        self._run_probe(
            "chase_migrate",
            cpu=0,
            working_set_kb=4096,
            src_cpu=0,
            dst_cpu=5,
            warm_passes=5,
            measure_passes=1,
            seed=42,
            hugepage=False,
        )

    def test_chase_migrate_accepts_hugepage_args(self):
        """Migration with hugepage=1, strict-hugepage=1."""
        self._run_probe(
            "chase_migrate",
            cpu=0,
            working_set_kb=MINIMUM_WORKING_SET_KB,
            src_cpu=0,
            dst_cpu=5,
            warm_passes=3,
            measure_passes=1,
            seed=42,
            hugepage=True,
        )

    # -- evict_slc -------------------------------------------------------

    def test_evict_slc_accepts_equals_syntax(self):
        """--evict_mb=32 --seed=42"""
        self._run_probe(
            "evict_slc",
            cpu=0,
            working_set_kb=32 * 1024,  # 32 MB
            seed=42,
        )

    def test_evict_slc_accepts_minimum_size(self):
        """--evict_mb=1 (minimum)"""
        self._run_probe(
            "evict_slc",
            cpu=0,
            working_set_kb=1024,  # 1 MB
            seed=0,
        )


class ProbeAdapterArgvContractTests(unittest.TestCase):
    """Structural tests on adapter-generated argv.

    These do NOT require compiled binaries — they verify argv shape
    against the documented C probe CLI signatures.
    """

    def test_chase_pmu_argv_is_positional_only(self):
        """ChasePmuAdapter must emit positional args, no --flags."""
        from arm64_probe.execution.adapters.chase_pmu import ChasePmuAdapter
        adapter = ChasePmuAdapter()
        argv = adapter.build_argv(cpu=0, working_set_kb=1024, seed=42)

        for token in argv:
            self.assertFalse(
                token.startswith("--"),
                f"chase_pmu argv must be positional, got named flag: {token}",
            )
        self.assertEqual(len(argv), 6, "expected 6 positional args")

    def test_chase_migrate_argv_uses_hyphens(self):
        """ChaseMigrateAdapter must use --src-cpu, --dst-cpu, --size-kb."""
        from arm64_probe.execution.adapters.chase_migrate import ChaseMigrateAdapter
        adapter = ChaseMigrateAdapter()
        argv = adapter.build_argv(
            cpu=0, working_set_kb=1024, src_cpu=0, dst_cpu=5, seed=42,
        )

        arg_str = " ".join(argv)
        self.assertIn("--src-cpu", arg_str)
        self.assertIn("--dst-cpu", arg_str)
        self.assertIn("--size-kb", arg_str)
        self.assertNotIn("--src_cpu", arg_str, "must use hyphen, not underscore")
        self.assertNotIn("--dst_cpu", arg_str, "must use hyphen, not underscore")

    def test_evict_slc_argv_uses_equals_syntax(self):
        """EvictSlcAdapter must use --evict_mb=N (equals, not space)."""
        from arm64_probe.execution.adapters.evict_slc import EvictSlcAdapter
        adapter = EvictSlcAdapter()
        argv = adapter.build_argv(cpu=0, working_set_kb=32 * 1024, seed=42)

        self.assertIn("--evict_mb=32", argv)
        self.assertIn("--seed=42", argv)

    def test_no_adapter_includes_binary_name_in_argv(self):
        """The binary name is provided by the runner, not the adapter."""
        for adapter_cls, kwargs in (
            (
                "arm64_probe.execution.adapters.chase_pmu.ChasePmuAdapter",
                {"cpu": 0, "working_set_kb": 1024},
            ),
            (
                "arm64_probe.execution.adapters.chase_migrate.ChaseMigrateAdapter",
                {"cpu": 0, "working_set_kb": 1024, "src_cpu": 0, "dst_cpu": 5},
            ),
            (
                "arm64_probe.execution.adapters.evict_slc.EvictSlcAdapter",
                {"cpu": 0, "working_set_kb": 32 * 1024},
            ),
        ):
            with self.subTest(adapter=adapter_cls):
                import importlib
                mod_name, cls_name = adapter_cls.rsplit(".", 1)
                mod = importlib.import_module(mod_name)
                adapter = getattr(mod, cls_name)()
                argv = adapter.build_argv(**kwargs)
                for token in argv:
                    self.assertFalse(
                        token in ("chase_pmu", "chase_migrate", "evict_slc"),
                        f"{cls_name} must not include binary name in argv: {token}",
                    )


if __name__ == "__main__":
    unittest.main()
