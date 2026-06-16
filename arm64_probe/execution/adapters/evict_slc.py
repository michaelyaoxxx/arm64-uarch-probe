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
            "--verbose",
        ]

    def parse_output(self, stdout: str, stderr: str) -> ProbeOutput | ProbeError:
        """Parse evict_slc output.

        The C probe (v1.2) produces::

            [evict_slc] version=v1.2 mode=random evict_mb=32 bytes=...
            [evict_slc] touch_ms=2.555 evict_ms=4.872 approx_bw=6.41 GB/s sink=66846720
            [evict_slc] done
        """
        # The C probe writes its performance output to stderr
        combined = (stdout + stderr) if stdout or stderr else ""
        try:
            # Primary performance line
            # Format: "[evict_slc] touch_ms=2.555 evict_ms=4.872 approx_bw=6.41 GB/s sink=66846720"
            perf_match = re.search(
                r"\[evict_slc\]\s+touch_ms\s*=\s*([\d.]+)\s+"
                r"evict_ms\s*=\s*([\d.]+)\s+"
                r"approx_bw\s*=\s*([\d.]+)\s*GB/s\s+"
                r"sink\s*=\s*(\d+)",
                combined,
            )

            if not perf_match:
                return ProbeError(
                    error_type="parse_failure",
                    message="Could not find evict_slc performance line in output",
                    stderr=stderr,
                )

            touch_ms = float(perf_match.group(1))
            evict_ms = float(perf_match.group(2))
            approx_bw_gbs = float(perf_match.group(3))
            sink_value = int(perf_match.group(4))

            # Extract evict_mb from the version/config line
            # Format: "[evict_slc] version=v1.2 mode=random evict_mb=32 bytes=..."
            evict_mb_match = re.search(r"evict_mb\s*=\s*(\d+)", combined)
            evict_mb = int(evict_mb_match.group(1)) if evict_mb_match else 0

            # Extract n_lines from the config line
            n_lines_match = re.search(r"n_lines\s*=\s*(\d+)", combined)
            n_lines = int(n_lines_match.group(1)) if n_lines_match else 0

            additional_metrics: dict[str, object] = {
                "touch_ms": touch_ms,
                "evict_ms": evict_ms,
                "approx_bw_gbs": approx_bw_gbs,
                "sink_value": sink_value,
                "evict_mb": evict_mb,
                "n_lines": n_lines,
            }

            # Convert evict_ms to ns as the primary latency
            latency_ns = evict_ms * 1_000_000.0

            return ProbeOutput(
                latency_ns=latency_ns,
                accesses=n_lines * 2,  # touch + evict
                elapsed_ns=int((touch_ms + evict_ms) * 1_000_000),
                sink_address=None,
                additional_metrics=additional_metrics,
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
