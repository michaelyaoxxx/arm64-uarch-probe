"""Phase 4 immutable analysis domain models.

All models are @dataclass(frozen=True). Tuple fields are normalized
in __post_init__ to ensure sorted uniqueness where applicable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _to_tuple(value: Any) -> tuple:
    """Normalize a value to a tuple for immutability."""
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, (list, set, frozenset)):
        return tuple(value)
    return (value,)


@dataclass(frozen=True)
class MetricStats:
    """Statistics for a single metric across a case's samples."""

    metric_name: str
    unit: str
    sample_count: int
    success_count: int
    error_count: int
    min_value: float | None = None
    max_value: float | None = None
    median: float | None = None
    mad: float | None = None
    mean: float | None = None
    stddev: float | None = None


@dataclass(frozen=True)
class CaseAnalysis:
    """Analysis of a single case's results across runs."""

    case_id: str
    scenario_id: str
    platform_id: str
    status: str  # "ok" | "partial" | "failed"
    total_samples: int
    ok_samples: int
    error_samples: int
    metric_stats: tuple[tuple[str, MetricStats], ...] = ()
    anomalies: tuple[str, ...] = ()
    source_run_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Sort metric_stats by metric name for deterministic ordering (SPEC requirement).
        raw = _to_tuple(self.metric_stats)
        object.__setattr__(
            self, "metric_stats",
            tuple(sorted(raw, key=lambda x: x[0])),
        )
        object.__setattr__(self, "anomalies", _to_tuple(self.anomalies))
        object.__setattr__(self, "source_run_ids", _to_tuple(self.source_run_ids))


@dataclass(frozen=True)
class CrossRunMetricDelta:
    """Difference of a single metric between two runs."""

    metric_name: str
    unit: str
    baseline_value: float | None = None
    current_value: float | None = None
    delta_pct: float | None = None


@dataclass(frozen=True)
class CrossRunComparison:
    """Comparison of a single case across two runs."""

    case_id: str
    runs_compared: tuple[str, str]
    classification: str  # "unchanged" | "improved" | "regressed" | "missing" | "incompatible"
    metric_deltas: tuple[tuple[str, CrossRunMetricDelta], ...] = ()
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "runs_compared", _to_tuple(self.runs_compared))
        object.__setattr__(self, "metric_deltas", _to_tuple(self.metric_deltas))


@dataclass(frozen=True)
class AnalysisSummary:
    """Top-level analysis result combining multiple runs."""

    analysis_id: str
    schema_version: int
    source_runs: tuple[str, ...]
    platform_id: str
    repository_id: str
    repository_commit: str
    dirty_tree: bool
    toolchain: tuple[tuple[str, str], ...]
    case_analyses: tuple[CaseAnalysis, ...] = ()
    cross_run_comparisons: tuple[CrossRunComparison, ...] = ()
    anomalies: tuple[str, ...] = ()
    generated_at: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_runs", _to_tuple(self.source_runs))
        object.__setattr__(self, "toolchain", _to_tuple(self.toolchain))
        object.__setattr__(self, "case_analyses", _to_tuple(self.case_analyses))
        object.__setattr__(self, "cross_run_comparisons", _to_tuple(self.cross_run_comparisons))
        object.__setattr__(self, "anomalies", _to_tuple(self.anomalies))


@dataclass(frozen=True)
class FigureManifest:
    """Metadata for a single figure in a report."""

    figure_id: str
    path: str
    caption: str
    source_analysis_id: str
    regeneration_command: str


@dataclass(frozen=True)
class ReportManifest:
    """Metadata for a generated report."""

    report_id: str
    report_path: str
    source_analysis_id: str
    figure_manifests: tuple[FigureManifest, ...] = ()
    claim_count: int = 0
    section_count: int = 0
    generated_at: str = ""
    regeneration_command: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "figure_manifests", _to_tuple(self.figure_manifests))


@dataclass(frozen=True)
class ImportedRecord:
    """A single record imported from an external tool."""

    source_path: str
    parser_version: str
    format: str
    case_id: str | None = None
    platform_id: str | None = None
    metrics: tuple[tuple[str, str | int | float | bool | None], ...] = ()
    loss_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "metrics",
            tuple(sorted(_to_tuple(self.metrics), key=lambda x: x[0])),
        )
        object.__setattr__(self, "loss_notes", _to_tuple(self.loss_notes))


@dataclass(frozen=True)
class BaselineManifest:
    """Baseline promotion record — ties analysis, report, and figure IDs to a version."""

    baseline_id: str
    version: str
    source_run_ids: tuple[str, ...]
    analysis_id: str
    report_id: str | None = None
    figure_ids: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()
    repository_commit: str = ""
    dirty_tree: bool = False
    toolchain: tuple[tuple[str, str], ...] = ()
    promoted_at: str = ""
    approved_by: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_run_ids", _to_tuple(self.source_run_ids))
        object.__setattr__(self, "figure_ids", _to_tuple(self.figure_ids))
        object.__setattr__(self, "commands", _to_tuple(self.commands))
        object.__setattr__(self, "toolchain", _to_tuple(self.toolchain))
