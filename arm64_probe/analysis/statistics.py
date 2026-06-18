"""Deterministic statistics computation. Pure functions, zero I/O."""

from __future__ import annotations

import statistics as stdlib_stats

from arm64_probe.analysis.models import CaseAnalysis, MetricStats


_UNIT_RULES = [
    ("_ns", "ns"),
    ("_cycles", "cycles"),
    ("_bytes", "bytes"),
]

_SPECIAL_UNITS: dict[str, str] = {
    "accesses": "count",
}


class StatisticsEngine:
    """Pure-function statistics engine using stdlib statistics.

    All methods are classmethods or staticmethods; no state, no I/O.
    Inferred unit rules:

    - ``_ns`` suffix -> ``"ns"``
    - ``_cycles`` suffix -> ``"cycles"``
    - ``_bytes`` suffix -> ``"bytes"``
    - ``accesses`` exact match -> ``"count"``
    - everything else -> ``"unknown"``
    """

    # ------------------------------------------------------------------
    # Unit inference
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_unit(metric_name: str) -> str:
        """Return a unit string guessed from *metric_name*."""
        if metric_name in _SPECIAL_UNITS:
            return _SPECIAL_UNITS[metric_name]
        for suffix, unit in _UNIT_RULES:
            if metric_name.endswith(suffix):
                return unit
        return "unknown"

    # ------------------------------------------------------------------
    # Per-metric statistics
    # ------------------------------------------------------------------

    @classmethod
    def compute_metric_stats(
        cls,
        samples: tuple,
        metric_name: str,
        unit: str | None = None,
    ) -> MetricStats:
        """Compute descriptive statistics for *metric_name* across *samples*.

        Parameters
        ----------
        samples:
            Iterable of :class:`~arm64_probe.domain.models.Sample`.
        metric_name:
            The metric key to extract from each sample's ``metrics`` dict.
        unit:
            Explicit unit override.  When ``None`` the engine infers the
            unit from *metric_name*.

        Returns
        -------
        MetricStats
            A frozen record with min, max, median, MAD, mean, stddev.
            When no successful sample carries *metric_name* the central
            tendency fields are ``None``.
        """
        if unit is None:
            unit = cls._infer_unit(metric_name)

        values: list[float] = []
        ok_count = 0
        error_count = 0

        for s in samples:
            if s.status == "ok":
                ok_count += 1
                metrics_dict = dict(s.metrics)
                if metric_name in metrics_dict:
                    values.append(float(metrics_dict[metric_name]))
            else:
                error_count += 1

        if not values:
            return MetricStats(
                metric_name=metric_name,
                unit=unit,
                sample_count=len(samples),
                success_count=ok_count,
                error_count=error_count,
                min_value=None,
                max_value=None,
                median=None,
                mad=None,
                mean=None,
                stddev=None,
            )

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        median = stdlib_stats.median(sorted_vals)
        mean = stdlib_stats.mean(sorted_vals)
        stddev = stdlib_stats.stdev(sorted_vals) if n >= 2 else 0.0
        mad = float(stdlib_stats.median([abs(v - median) for v in sorted_vals]))

        return MetricStats(
            metric_name=metric_name,
            unit=unit,
            sample_count=len(samples),
            success_count=ok_count,
            error_count=error_count,
            min_value=sorted_vals[0],
            max_value=sorted_vals[-1],
            median=median,
            mad=mad,
            mean=mean,
            stddev=stddev,
        )

    # ------------------------------------------------------------------
    # Per-case analysis
    # ------------------------------------------------------------------

    @classmethod
    def compute_case_analysis(
        cls,
        case_id: str,
        samples: tuple,
        scenario_id: str,
        platform_id: str,
    ) -> CaseAnalysis:
        """Aggregate *samples* into a :class:`CaseAnalysis`.

        The status is determined as:

        * ``"ok"`` -- every sample has status ``"ok"``.
        * ``"failed"`` -- every sample has status ``"error"``.
        * ``"partial"`` -- a mix of ok and error samples.

        Anomaly detection is run for every metric; the union of all
        metric-level anomalies is reported on the :class:`CaseAnalysis`.
        """
        ok_count = sum(1 for s in samples if s.status == "ok")
        error_count = sum(1 for s in samples if s.status == "error")

        if ok_count == len(samples):
            status = "ok"
        elif ok_count == 0:
            status = "failed"
        else:
            status = "partial"

        # Collect all metric names present in ok samples.
        metric_names: set[str] = set()
        for s in samples:
            if s.status == "ok":
                metric_names.update(dict(s.metrics).keys())

        # Compute per-metric stats, sorted by name for determinism.
        metric_stats = tuple(
            (name, cls.compute_metric_stats(samples, name))
            for name in sorted(metric_names)
        )

        # Union of all metric-level anomalies.
        all_anomalies: list[str] = []
        for _name, stats in metric_stats:
            for anomaly in cls.detect_anomalies(stats):
                if anomaly not in all_anomalies:
                    all_anomalies.append(anomaly)
        all_anomalies.sort()

        run_ids = tuple(sorted(set(s.run_id for s in samples)))

        return CaseAnalysis(
            case_id=case_id,
            scenario_id=scenario_id,
            platform_id=platform_id,
            status=status,
            total_samples=len(samples),
            ok_samples=ok_count,
            error_samples=error_count,
            metric_stats=metric_stats,
            anomalies=tuple(all_anomalies),
            source_run_ids=run_ids,
        )

    # ------------------------------------------------------------------
    # Anomaly detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_anomalies(stats: MetricStats) -> tuple[str, ...]:
        """Return a sorted tuple of anomaly labels for *stats*.

        Rules (checked in this order, though order in the result is
        alphabetical):

        * ``all_errors`` -- no successful samples (``success_count == 0``).
        * ``single_sample`` -- only one successful sample.
        * ``zero_variance`` -- more than one sample but ``stddev == 0.0``.
        * ``high_variance`` -- ``stddev > 2 * abs(mean)``.
        * ``extreme_outlier`` -- ``max_value > mean + 5 * stddev``.
        """
        anomalies: list[str] = []

        if stats.success_count == 0:
            anomalies.append("all_errors")
            return tuple(anomalies)

        if stats.success_count == 1:
            anomalies.append("single_sample")

        if stats.stddev is not None and stats.stddev == 0.0 and stats.sample_count > 1:
            anomalies.append("zero_variance")

        if (
            stats.mean is not None
            and stats.mean != 0
            and stats.stddev is not None
            and stats.stddev > 2 * abs(stats.mean)
        ):
            anomalies.append("high_variance")

        if (
            stats.mean is not None
            and stats.stddev is not None
            and stats.stddev > 0
            and stats.max_value is not None
            and stats.max_value > stats.mean + 5 * stats.stddev
        ):
            anomalies.append("extreme_outlier")

        return tuple(sorted(anomalies))
