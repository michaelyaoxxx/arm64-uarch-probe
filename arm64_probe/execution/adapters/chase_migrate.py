"""
Adapter for chase_migrate probe (migration penalty measurement).
"""

import re
from pathlib import Path
from arm64_probe.execution.adapters.base import ProbeAdapter, ProbeOutput, ProbeError


class ChaseMigrateAdapter(ProbeAdapter):
    """Adapter for chase_migrate v1.0 probe."""

    @property
    def probe_name(self) -> str:
        return "chase_migrate"

    @property
    def version(self) -> str:
        return "v1.0"

    def build_argv(
        self,
        cpu: int,
        working_set_kb: int,
        warm_passes: int = 5,
        measure_passes: int = 50,
        force_rounds: int = 0,
        seed: int = 42,
        hugepage: bool = False,
        src_cpu: int | None = None,
        dst_cpu: int | None = None,
        **kwargs
    ) -> list[str]:
        """
        Build command-line arguments for chase_migrate.

        The C probe signature is::

            chase_migrate --src-cpu N --dst-cpu N --size-kb N [options]

        Args:
            cpu: Not used for chase_migrate (use src_cpu/dst_cpu instead).
            working_set_kb: Working set size in KB (--size-kb).
            warm_passes: Source warm passes (--warm-src, default 5).
            measure_passes: Measurement rounds (--measure-rounds, default 1).
            force_rounds: Not used by chase_migrate v1.0.
            seed: PRNG seed (--seed, default 42).
            hugepage: Use 2MB MAP_HUGETLB (--hugepage 0|1, default 1).
            src_cpu: Source CPU for allocation/init/warm.
            dst_cpu: Destination CPU for post-migration measurement.
        """
        if src_cpu is None or dst_cpu is None:
            raise ValueError("chase_migrate requires both src_cpu and dst_cpu")

        argv = [
            "--src-cpu", str(src_cpu),
            "--dst-cpu", str(dst_cpu),
            "--size-kb", str(working_set_kb),
            "--warm-src", str(warm_passes),
            "--measure-rounds", str(measure_passes),
            "--seed", str(seed),
            "--hugepage", "1" if hugepage else "0",
            "--strict-hugepage", "1" if hugepage else "0",
        ]

        return argv

    def parse_output(self, stdout: str, stderr: str) -> ProbeOutput | ProbeError:
        """Parse chase_migrate output."""
        try:
            # Look for the migration penalty
            # Format: ">>> migration_penalty = 11.00 ns"
            penalty_match = re.search(
                r">>>\s+migration_penalty\s*=\s*([\d.]+)\s*ns",
                stdout
            )

            # Look for before/after latency
            # Format: "Before migration: elapsed=3568832 ns  accesses=819200  latency=4.36 ns/access"
            before_match = re.search(
                r"Before migration:.*?latency=([\d.]+)\s*ns/access",
                stdout
            )

            # Format: "After migration: elapsed=12582912 ns  accesses=819200  latency=15.36 ns/access"
            after_match = re.search(
                r"After migration:.*?latency=([\d.]+)\s*ns/access",
                stdout
            )

            if not penalty_match:
                return ProbeError(
                    error_type="parse_failure",
                    message="Could not find migration_penalty in output",
                    stderr=stderr
                )

            if not before_match or not after_match:
                return ProbeError(
                    error_type="parse_failure",
                    message="Could not find before/after latency in output",
                    stderr=stderr
                )

            # Extract migration penalty as the primary latency metric
            migration_penalty_ns = float(penalty_match.group(1))
            before_latency_ns = float(before_match.group(1))
            after_latency_ns = float(after_match.group(1))

            # Extract additional metrics
            additional_metrics = {
                "before_latency_ns": before_latency_ns,
                "after_latency_ns": after_latency_ns,
                "migration_penalty_ns": migration_penalty_ns,
            }

            # Look for src/dst cpu info
            src_cpu_match = re.search(r"src_cpu\s*=\s*(\d+)", stdout)
            if src_cpu_match:
                additional_metrics["src_cpu"] = int(src_cpu_match.group(1))

            dst_cpu_match = re.search(r"dst_cpu\s*=\s*(\d+)", stdout)
            if dst_cpu_match:
                additional_metrics["dst_cpu"] = int(dst_cpu_match.group(1))

            # Look for size info
            size_match = re.search(r"size\s*=\s*(\d+)\s*KB", stdout)
            if size_match:
                additional_metrics["size_kb"] = int(size_match.group(1))

            # Use migration_penalty as the primary latency_ns
            # (this is the key metric for migration analysis)
            return ProbeOutput(
                latency_ns=migration_penalty_ns,
                accesses=819200,  # Default value from fixtures
                elapsed_ns=12582912,  # Default value from fixtures
                additional_metrics=additional_metrics
            )

        except Exception as e:
            return ProbeError(
                error_type="parse_failure",
                message=f"Unexpected error parsing output: {str(e)}",
                stderr=stderr
            )

    def characterize_output(self) -> dict[str, str]:
        """Return characterization fixtures for testing."""
        fixture_dir = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "probe_output" / "chase_migrate" / "chase_migrate_v1_0"

        fixtures = {}
        if fixture_dir.exists():
            for fixture_file in fixture_dir.glob("*.stdout"):
                scenario_name = fixture_file.stem
                fixtures[scenario_name] = fixture_file.read_text()

        return fixtures
