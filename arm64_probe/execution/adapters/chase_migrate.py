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
        """Parse chase_migrate output.

        The C probe (v1.0) produces::

            === chase_migrate v1.0 ===
            label=(none)
            src_cpu=0 dst_cpu=10 size=4096 KB n_lines=65536 ...
            [src] bound before alloc/init: requested=0 current=0
            [alloc] buf=... alloc_size=... KB chain_size=... KB hugepage_actual=0
            [src] warm elapsed=... ns accesses=...
            [src] measure elapsed=... ns accesses=... cpu_before=... cpu_after=...
            >>> src_latency = 4.36 ns/access  (sink=0x...)
            [dst] bound after migration: requested=10 current=10
            [dst] measure elapsed=... ns accesses=... cpu_before=... cpu_after=...
            >>> migrate_latency = 5.04 ns/access  (sink=0x...)
            >>> migrate_penalty = 0.68 ns/access
        """
        try:
            # Primary metric: migration penalty
            # Format: ">>> migrate_penalty = 0.68 ns/access"
            penalty_match = re.search(
                r">>>\s+migrate_penalty\s*=\s*([\d.]+)\s*ns",
                stdout,
            )
            # Source-side latency
            # Format: ">>> src_latency = 4.36 ns/access  (sink=0x...)"
            src_lat_match = re.search(
                r">>>\s+src_latency\s*=\s*([\d.]+)\s*ns/access\s*\(sink=(0x[0-9a-fA-F]+)\)",
                stdout,
            )
            # Destination-side latency
            # Format: ">>> migrate_latency = 5.04 ns/access  (sink=0x...)"
            dst_lat_match = re.search(
                r">>>\s+migrate_latency\s*=\s*([\d.]+)\s*ns/access\s*\(sink=(0x[0-9a-fA-F]+)\)",
                stdout,
            )

            # Penalty is the primary metric; requires measure_src=1 (default).
            if not penalty_match:
                # Fall back to migrate_latency when penalty not computed
                if dst_lat_match:
                    dst_lat_ns = float(dst_lat_match.group(1))
                    return ProbeOutput(
                        latency_ns=dst_lat_ns,
                        accesses=0,
                        elapsed_ns=0,
                        sink_address=None,
                        additional_metrics={"migrate_latency_ns": dst_lat_ns},
                    )
                return ProbeError(
                    error_type="parse_failure",
                    message="Could not find migrate_penalty or migrate_latency in output",
                    stderr=stderr,
                )

            migration_penalty_ns = float(penalty_match.group(1))

            additional_metrics: dict[str, object] = {
                "migration_penalty_ns": migration_penalty_ns,
            }

            if src_lat_match:
                additional_metrics["src_latency_ns"] = float(src_lat_match.group(1))
                additional_metrics["src_sink"] = src_lat_match.group(2)

            if dst_lat_match:
                additional_metrics["migrate_latency_ns"] = float(dst_lat_match.group(1))
                additional_metrics["dst_sink"] = dst_lat_match.group(2)

            # Extract src/dst CPU from header line
            # Format: "src_cpu=0 dst_cpu=10 size=4096 KB ..."
            src_cpu_match = re.search(r"src_cpu\s*=\s*(\d+)", stdout)
            if src_cpu_match:
                additional_metrics["src_cpu"] = int(src_cpu_match.group(1))

            dst_cpu_match = re.search(r"dst_cpu\s*=\s*(\d+)", stdout)
            if dst_cpu_match:
                additional_metrics["dst_cpu"] = int(dst_cpu_match.group(1))

            # Extract measurement accesses from [dst] measure line
            dst_access_match = re.search(
                r"\[dst\]\s+measure.*?accesses\s*=\s*(\d+)", stdout,
            )
            if dst_access_match:
                additional_metrics["dst_accesses"] = int(dst_access_match.group(1))

            return ProbeOutput(
                latency_ns=migration_penalty_ns,
                accesses=0,
                elapsed_ns=0,
                sink_address=None,
                additional_metrics=additional_metrics,
            )

        except Exception as e:
            return ProbeError(
                error_type="parse_failure",
                message=f"Unexpected error parsing output: {str(e)}",
                stderr=stderr,
            )

    def characterize_output(self) -> dict[str, str]:
        """Return characterization fixtures for testing."""
        fixture_dir = (
            Path(__file__).parent.parent.parent.parent
            / "tests" / "fixtures" / "probe_output"
            / "chase_migrate" / "chase_migrate_v1_0"
        )

        fixtures = {}
        if fixture_dir.exists():
            for fixture_file in fixture_dir.glob("*.stdout"):
                scenario_name = fixture_file.stem
                fixtures[scenario_name] = fixture_file.read_text()

        return fixtures
