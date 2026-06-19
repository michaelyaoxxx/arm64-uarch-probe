"""Figure generation from analysis artifacts (matplotlib Agg backend)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pathlib import Path

from arm64_probe.analysis.models import AnalysisSummary, FigureManifest


class FigureGenerator:
    """Generate PNG figures from an AnalysisSummary using matplotlib.

    Produces three chart types:
        1. latency_bar_chart   — median latency per case
        2. migration_penalty_chart — median migration penalty per case
        3. metric_summary_table   — tabular summary of all metrics

    Each method writes a PNG and returns a FigureManifest with
    metadata (caption, source_analysis_id, regeneration_command).
    """

    def __init__(self, analysis: AnalysisSummary) -> None:
        self._analysis = analysis

    # ------------------------------------------------------------------
    # Public figure methods
    # ------------------------------------------------------------------

    def latency_bar_chart(self, output_dir: Path) -> FigureManifest:
        """Bar chart of median latency_ns per case."""
        figure_id = "latency_comparison"
        labels, values = self._collect_metric("latency_ns")

        fig, ax = plt.subplots(figsize=(8, 5))
        if labels:
            ax.bar(labels, values)
            ax.set_xlabel("Case")
            ax.set_ylabel("Latency (ns)")
            ax.set_title("Cache/Memory Latency Comparison")
            plt.xticks(rotation=45, ha="right")
        else:
            ax.text(
                0.5, 0.5, "No latency data",
                ha="center", va="center",
                transform=ax.transAxes, fontsize=14,
            )
        fig.tight_layout()
        path = output_dir / f"{figure_id}.png"
        fig.savefig(str(path), dpi=100)
        plt.close(fig)

        return FigureManifest(
            figure_id=figure_id,
            path=str(path),
            caption="Cache/Memory Latency Comparison",
            source_analysis_id=self._analysis.analysis_id,
            regeneration_command=(
                f"probe report --analysis {self._analysis.analysis_id}"
            ),
        )

    def migration_penalty_chart(self, output_dir: Path) -> FigureManifest:
        """Bar chart of median migration_penalty_ns per case."""
        figure_id = "migration_penalty"
        labels, values = [], []
        for ca in self._analysis.case_analyses:
            if "migration" in ca.scenario_id.lower():
                for name, stats in ca.metric_stats:
                    if name == "migration_penalty_ns" and stats.median is not None:
                        labels.append(ca.case_id)
                        values.append(stats.median)
                        break

        fig, ax = plt.subplots(figsize=(8, 5))
        if labels:
            ax.bar(labels, values)
            ax.set_xlabel("Migration Pair")
            ax.set_ylabel("Penalty (ns)")
            ax.set_title("Migration Penalty Comparison")
            plt.xticks(rotation=45, ha="right")
        else:
            ax.text(
                0.5, 0.5, "No migration data",
                ha="center", va="center",
                transform=ax.transAxes, fontsize=14,
            )
        fig.tight_layout()
        path = output_dir / f"{figure_id}.png"
        fig.savefig(str(path), dpi=100)
        plt.close(fig)

        return FigureManifest(
            figure_id=figure_id,
            path=str(path),
            caption="Migration Penalty Comparison",
            source_analysis_id=self._analysis.analysis_id,
            regeneration_command=(
                f"probe report --analysis {self._analysis.analysis_id}"
            ),
        )

    def metric_summary_table(self, output_dir: Path) -> FigureManifest:
        """Tabular figure showing case, metric, and median for all metrics."""
        figure_id = "metric_summary"
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.axis("off")
        rows = []
        for ca in self._analysis.case_analyses:
            for name, stats in ca.metric_stats:
                median_str = (
                    f"{stats.median:.2f} {stats.unit}"
                    if stats.median is not None
                    else "N/A"
                )
                rows.append([ca.case_id, name, median_str])
        if rows:
            table = ax.table(
                cellText=rows,
                colLabels=["Case", "Metric", "Median"],
                loc="center",
                cellLoc="left",
            )
            table.auto_set_font_size(False)
            table.set_fontsize(8)
        else:
            ax.text(
                0.5, 0.5, "No data",
                ha="center", va="center",
                transform=ax.transAxes, fontsize=14,
            )
        fig.tight_layout()
        path = output_dir / f"{figure_id}.png"
        fig.savefig(str(path), dpi=100)
        plt.close(fig)

        return FigureManifest(
            figure_id=figure_id,
            path=str(path),
            caption="Metric Summary Table",
            source_analysis_id=self._analysis.analysis_id,
            regeneration_command=(
                f"probe report --analysis {self._analysis.analysis_id}"
            ),
        )

    def generate_all(self, output_dir: Path) -> tuple[FigureManifest, ...]:
        """Generate all figure types and return their manifests."""
        return (
            self.latency_bar_chart(output_dir),
            self.migration_penalty_chart(output_dir),
            self.metric_summary_table(output_dir),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_metric(
        self, metric_name: str,
    ) -> tuple[list[str], list[float]]:
        """Collect case labels and median values for *metric_name."""
        labels: list[str] = []
        values: list[float] = []
        for ca in self._analysis.case_analyses:
            for name, stats in ca.metric_stats:
                if name == metric_name and stats.median is not None:
                    labels.append(ca.case_id)
                    values.append(stats.median)
                    break
        return labels, values
