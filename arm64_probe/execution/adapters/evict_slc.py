"""
Adapter for evict_slc probe (SLC eviction latency measurement).
"""

import re
from pathlib import Path
from arm64_probe.execution.adapters.base import ProbeAdapter, ProbeOutput, ProbeError


class EvictSlcAdapter(ProbeAdapter):
    """Adapter for evict_slc v1.2 probe."""

    @property
    def probe_name(self) -> str:
        return "evict_slc"

    @property
    def version(self) -> str:
        return "v1.2"

    def build_argv(
        self,
        cpu: int = 0,
        working_set_kb: int = 1024,
        warm_passes: int = 0,
        measure_passes: int = 50,
        force_rounds: int = 0,
        seed: int = 42,
        hugepage: bool = False,
        **kwargs
    ) -> list[str]:
        """
        Build command-line arguments for evict_slc.

        Args:
            cpu: CPU affinity (applied externally, not via argv)
            working_set_kb: Working set size in KB (converted to MB for evict_mb)
            warm_passes: Not used for evict_slc
            measure_passes: Not used for evict_slc
            force_rounds: Not used for evict_slc
            seed: Random seed
            hugepage: Not used for evict_slc
        """
        # evict_slc uses evict_mb parameter (in MB), with = syntax per C probe
        evict_mb = max(1, working_set_kb // 1024)  # Convert KB to MB, minimum 1MB

        return [
            f"--evict_mb={evict_mb}",
            f"--seed={seed}",
        ]

    def parse_output(self, stdout: str, stderr: str) -> ProbeOutput | ProbeError:
        """Parse evict_slc output."""
        try:
            # Look for the key output line
            # Format: ">>> latency = 0.031 ns/access  (sink=0x7f5678000000)"
            latency_match = re.search(
                r">>>\s+latency\s*=\s*([\d.]+)\s*ns/access\s*\(sink=0x([0-9a-fA-F]+)\)",
                stdout
            )

            # Look for elapsed and accesses
            # Format: "elapsed=4194304 ns  accesses=134217728"
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

            # Extract additional metrics
            additional_metrics = {}

            # Look for evict_mb if present
            evict_mb_match = re.search(r"evict_mb\s*=\s*(\d+)", stdout)
            if evict_mb_match:
                additional_metrics["evict_mb"] = int(evict_mb_match.group(1))

            # Look for n_lines if present
            n_lines_match = re.search(r"n_lines\s*=\s*(\d+)", stdout)
            if n_lines_match:
                additional_metrics["n_lines"] = int(n_lines_match.group(1))

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
        fixture_dir = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "probe_output" / "evict_slc" / "evict_slc_v1_2"

        fixtures = {}
        if fixture_dir.exists():
            for fixture_file in fixture_dir.glob("*.stdout"):
                scenario_name = fixture_file.stem
                fixtures[scenario_name] = fixture_file.read_text()

        return fixtures
