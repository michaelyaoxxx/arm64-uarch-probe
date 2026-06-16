"""
Base probe adapter protocol and related types.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable, Any


@dataclass(frozen=True)
class ProbeOutput:
    """Normalized output from a probe execution."""
    latency_ns: float
    accesses: int
    elapsed_ns: int
    sink_address: str | None = None
    additional_metrics: dict[str, Any] = None

    def __post_init__(self):
        if self.additional_metrics is None:
            object.__setattr__(self, 'additional_metrics', {})


@dataclass(frozen=True)
class ProbeError:
    """Error from probe execution."""
    error_type: str  # "launch", "timeout", "nonzero_exit", "parse_failure"
    message: str
    exit_code: int | None = None
    stderr: str | None = None


@runtime_checkable
class ProbeAdapter(Protocol):
    """
    Protocol for probe adapters.

    Each adapter knows how to:
    1. Build the command-line arguments for a specific probe
    2. Parse the probe's output into normalized ProbeOutput
    """

    @property
    def probe_name(self) -> str:
        """Name of the probe (e.g., 'chase_pmu', 'evict_slc')."""
        ...

    @property
    def version(self) -> str:
        """Version of the probe (e.g., 'v2.7.3')."""
        ...

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
        Build command-line arguments for the probe.

        Returns a list of strings suitable for subprocess execution.
        """
        ...

    def parse_output(self, stdout: str, stderr: str) -> ProbeOutput | ProbeError:
        """
        Parse probe output into normalized ProbeOutput.

        Returns ProbeError if parsing fails or probe reported an error.
        """
        ...

    def characterize_output(self) -> dict[str, str]:
        """
        Return characterization fixtures for testing.

        Returns a dict mapping scenario names to expected output strings.
        """
        ...
