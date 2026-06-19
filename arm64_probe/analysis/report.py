"""Deterministic Markdown report generation."""
from pathlib import Path

from arm64_probe.analysis.models import (
    AnalysisSummary,
    FigureManifest,
    ReportManifest,
)


class ReportGenerator:
    """Generate a deterministic Markdown report from an AnalysisSummary and figure manifests.

    The report includes: provenance metadata, executive summary, per-scenario
    analysis with metric tables, cross-run comparison notes, figure references,
    methodology links, and limitations.
    """

    def __init__(
        self,
        analysis: AnalysisSummary,
        figures: tuple[FigureManifest, ...],
    ) -> None:
        self._analysis = analysis
        self._figures = figures

    def generate(self) -> str:
        """Generate the full Markdown report string.

        Returns:
            Deterministic Markdown string.
        """
        a = self._analysis
        sections: list[str] = []

        # Title + Provenance
        sections.append("# GB10 Microarchitecture Baseline Report\n")
        sections.append("**Provenance**  ")
        sections.append(f"**Analysis ID:** `{a.analysis_id}`  ")
        sections.append(f"**Platform:** {a.platform_id}  ")
        sections.append(f"**Commit:** `{a.repository_commit}`  ")
        sections.append(f"**Dirty tree:** {a.dirty_tree}  ")
        sections.append(f"**Generated:** {a.generated_at}  ")
        sections.append("")

        # Executive Summary
        sections.append("## Executive Summary\n")
        ok_count = sum(1 for ca in a.case_analyses if ca.status == "ok")
        partial_count = sum(1 for ca in a.case_analyses if ca.status == "partial")
        failed_count = sum(1 for ca in a.case_analyses if ca.status == "failed")
        sections.append(f"- **{len(a.case_analyses)}** cases analyzed")
        sections.append(
            f"- **{ok_count}** ok, **{partial_count}** partial, "
            f"**{failed_count}** failed"
        )
        if a.anomalies:
            sections.append(f"- **Anomalies:** {', '.join(a.anomalies)}")
        sections.append("")

        # Per-Scenario Analysis
        sections.append("## Per-Scenario Analysis\n")
        if not a.case_analyses:
            sections.append("> *No cases to analyze.*\n")
        for ca in a.case_analyses:
            badge = {"ok": "OK", "partial": "PARTIAL", "failed": "FAILED"}.get(
                ca.status, "?"
            )
            sections.append(f"### [{badge}] {ca.case_id}\n")
            sections.append(f"- **Scenario:** {ca.scenario_id}")
            sections.append(
                f"- **Samples:** {ca.ok_samples}/{ca.total_samples} ok"
            )
            if ca.anomalies:
                sections.append(
                    f"- **Anomalies:** {', '.join(ca.anomalies)}"
                )
            sections.append("")
            sections.append(
                "| Metric | Unit | Median | Mean | StdDev | Min | Max |"
            )
            sections.append(
                "|--------|------|--------|------|--------|-----|-----|"
            )
            for name, stats in ca.metric_stats:
                sections.append(
                    f"| {name} | {stats.unit} | "
                    f"{_fmt(stats.median)} | {_fmt(stats.mean)} | "
                    f"{_fmt(stats.stddev)} | {_fmt(stats.min_value)} | "
                    f"{_fmt(stats.max_value)} |"
                )
            sections.append("")

        # Cross-Run Comparison
        sections.append("## Cross-Run Comparison\n")
        if not a.cross_run_comparisons:
            sections.append("> Cross-run comparison deferred to Phase 5.\n")
        else:
            sections.append("*Phase 5 implementation.*\n")

        # Figures
        sections.append("## Figures\n")
        if not self._figures:
            sections.append("> *No figures generated.*\n")
        for f in self._figures:
            sections.append(f"### {f.figure_id}\n")
            sections.append(f"![{f.caption}]({f.path})\n")
            sections.append(f"*{f.caption}*\n")

        # Methodology
        sections.append("## Methodology\n")
        sections.append("See methodology docs:\n")
        sections.append("- [Cache Latency](../docs/methodology/cache-latency.md)")
        sections.append(
            "- [Migration Latency](../docs/methodology/migration-latency.md)"
        )

        # Limitations
        sections.append("## Limitations\n")
        sections.append(
            "- Phase 4: single-run analysis; "
            "cross-run comparison deferred to Phase 5.\n"
        )

        return "\n".join(sections)

    def write(
        self,
        output_dir: Path,
        regeneration_command: str,
    ) -> ReportManifest:
        """Write the report Markdown file and return its manifest.

        Args:
            output_dir: Directory to write the report into.
            regeneration_command: CLI command used to regenerate this report.

        Returns:
            ReportManifest with metadata about the generated report.
        """
        md = self.generate()
        report_path = output_dir / "report.md"
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(md, encoding="utf-8")
        section_count = md.count("## ")
        claim_count = md.count("| ") - 2

        return ReportManifest(
            report_id=self._analysis.analysis_id,
            report_path=str(report_path),
            source_analysis_id=self._analysis.analysis_id,
            figure_manifests=self._figures,
            claim_count=claim_count,
            section_count=section_count,
            generated_at=self._analysis.generated_at,
            regeneration_command=regeneration_command,
        )


def _fmt(value: float | None) -> str:
    """Format a float or None for table cells."""
    if value is not None:
        return f"{value:.2f}"
    return "N/A"
