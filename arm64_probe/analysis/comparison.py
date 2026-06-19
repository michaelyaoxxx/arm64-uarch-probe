"""Cross-run comparison engine (Phase 4 stub)."""
from arm64_probe.analysis.models import CaseAnalysis, CrossRunComparison


class ComparisonEngine:
    """Phase 4 protocol stub. Full implementation deferred to Phase 5."""

    @staticmethod
    def compare_runs(
        baseline: CaseAnalysis, current: CaseAnalysis,
        tolerance_pct: float = 5.0
    ) -> CrossRunComparison:
        return CrossRunComparison(
            case_id=current.case_id,
            runs_compared=(
                baseline.source_run_ids[0] if baseline.source_run_ids else "?",
                current.source_run_ids[0] if current.source_run_ids else "?",
            ),
            classification="incompatible",
            metric_deltas=(),
            note="Cross-run comparison deferred to Phase 5",
        )
