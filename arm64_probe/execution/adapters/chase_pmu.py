"""
Adapter for chase_pmu probe (memory latency measurement).
"""

import re
from pathlib import Path
from arm64_probe.execution.adapters.base import ProbeAdapter, ProbeOutput, ProbeError


class ChasePmuAdapter(ProbeAdapter):
    """Adapter for chase_pmu v2.7.3 probe."""

    @property
    def probe_name(self) -> str:
        return "chase_pmu"

    @property
    def version(self) -> str:
        return "v2.7.3"

    def build_argv(
        self,
        cpu: int,
        working_set_kb: int,
        warm_passes: int = 0,
        measure_passes: int = 50,
        force_rounds: int = 0,
        seed: int = 42,
        hugepage: bool = False,
        **kwargs
    ) -> list[str]:
        """
        Build positional command-line arguments for chase_pmu.

        The C probe signature is::

            chase_pmu <size_kb> <warm> [force_rounds] [seed] [clflush] [hugepage]

        Args:
            cpu: CPU affinity (applied externally, not via argv).
            working_set_kb: Working set size in KB (positional arg 1).
            warm_passes: Number of warmup passes (positional arg 2).
            measure_passes: (unused by v2.7.3 C probe).
            force_rounds: Force specific number of rounds (positional arg 3).
            seed: Random seed (positional arg 4).
            hugepage: Use hugepages (positional arg 6).
        """
        return [
            str(working_set_kb),
            str(warm_passes),
            str(force_rounds if force_rounds > 0 else 0),
            str(seed),
            "0",                         # clflush
            "1" if hugepage else "0",    # hugepage
        ]

    def parse_output(self, stdout: str, stderr: str) -> ProbeOutput | ProbeError:
        """Parse chase_pmu output."""
        try:
            # Look for the key output line
            # Format: ">>> latency = 4.36 ns/access  (sink=0x437530c3e000)"
            latency_match = re.search(
                r">>>\s+latency\s*=\s*([\d.]+)\s*ns/access\s*\(sink=0x([0-9a-fA-F]+)\)",
                stdout
            )

            # Look for elapsed and accesses
            # Format: "elapsed=3568832 ns  accesses=819200"
            perf_match = re.search(
                r"elapsed\s*=\s*(\d+)\s*ns\s+accesses\s*=\s*(\d+)",
                stdout
            )

            if not latency_match:
                return ProbeError(
                    error_type="parse_failure",
                    message="Could not find latency in output",
                    stderr=stderr
                )

            if not perf_match:
                return ProbeError(
                    error_type="parse_failure",
                    message="Could not find elapsed/accesses in output",
                    stderr=stderr
                )

            latency_ns = float(latency_match.group(1))
            sink_address = "0x" + latency_match.group(2)
            elapsed_ns = int(perf_match.group(1))
            accesses = int(perf_match.group(2))

            # Extract additional metrics if present
            additional_metrics = {}

            # Look for cache line size if present
            cache_line_match = re.search(r"cache_line_size\s*=\s*(\d+)", stdout)
            if cache_line_match:
                additional_metrics["cache_line_size"] = int(cache_line_match.group(1))

            # Look for tlb entries if present
            tlb_match = re.search(r"tlb_entries\s*=\s*(\d+)", stdout)
            if tlb_match:
                additional_metrics["tlb_entries"] = int(tlb_match.group(1))

            return ProbeOutput(
                latency_ns=latency_ns,
                accesses=accesses,
                elapsed_ns=elapsed_ns,
                sink_address=sink_address,
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
        fixture_dir = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "probe_output" / "chase_pmu" / "chase_pmu_v2_7_3"

        fixtures = {}
        if fixture_dir.exists():
            for fixture_file in fixture_dir.glob("*.stdout"):
                scenario_name = fixture_file.stem
                fixtures[scenario_name] = fixture_file.read_text()

        return fixtures
