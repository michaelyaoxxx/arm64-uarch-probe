import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from arm64_probe.domain.models import Plan, RunResult
from arm64_probe.analysis.models import AnalysisSummary, FigureManifest, ReportManifest
from arm64_probe.environment.models import DoctorReport, EnvironmentJournal
from arm64_probe.errors import ProbeError
from arm64_probe.registry.catalog import Catalog
from arm64_probe.serialization.json_io import dump_json
from arm64_probe.serialization.model_json import to_data


def _table(headers: tuple[str, ...], rows: Iterable[tuple[object, ...]]) -> str:
    rendered = [tuple(str(value) for value in row) for row in rows]
    widths = [
        max([len(header), *(len(row[index]) for row in rendered)])
        for index, header in enumerate(headers)
    ]
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rendered
    )
    return "\n".join(lines) + "\n"


def _compact(value: Any) -> str:
    if value is None or isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _list_items(catalog: Catalog, category: str) -> tuple[tuple[str, object], ...]:
    if category == "capabilities":
        return tuple(("capability", item) for item in catalog.capabilities())
    if category == "platforms":
        return tuple(("platform", item) for item in catalog.platforms())
    if category == "profiles":
        return tuple(("profile", item) for item in catalog.profiles())
    return (
        *((("experiment", item) for item in catalog.experiments())),
        *((("scenario", item) for item in catalog.scenarios())),
    )


def render_list(catalog: Catalog, category: str, output: str) -> str:
    items = _list_items(catalog, category)
    if output == "json":
        return dump_json(
            [{"kind": kind, **to_data(item)} for kind, item in items]
        )
    rows = []
    for kind, item in items:
        data = to_data(item)
        if kind == "platform":
            detail = (
                f"{data['measurement_support']}; "
                f"capabilities={','.join(data['capabilities'])}"
            )
        elif kind == "scenario":
            detail = (
                f"{data['cpu_mode']}; "
                f"requires={','.join(data['required_capabilities'])}"
            )
        elif kind == "profile":
            detail = f"selects={','.join(data['selections'])}"
        elif kind == "experiment":
            detail = f"scenarios={len(data['scenarios'])}"
        else:
            detail = data["description"]
        rows.append((kind, data["id"], data.get("display_name", ""), detail))
    return _table(("KIND", "ID", "NAME", "DETAIL"), rows)


def render_show(value: object, output: str) -> str:
    data = to_data(value)
    if output == "json":
        return dump_json(data)
    return _table(
        ("FIELD", "VALUE"),
        ((key, _compact(item)) for key, item in sorted(data.items())),
    )


def render_plan(plan: Plan, output: str) -> str:
    if output == "json":
        return dump_json(to_data(plan))
    summary = _table(
        ("FIELD", "VALUE"),
        (
            ("platform", plan.platform_id),
            ("profile", plan.profile_id or ""),
            ("skip_unavailable", plan.skip_unavailable),
            ("cases", len(plan.cases)),
        ),
    )
    cases = _table(
        ("CASE", "STATUS", "CPU", "REASON"),
        (
            (
                case.id,
                case.status,
                (
                    case.cpu
                    if case.cpu is not None
                    else f"{case.src_cpu}->{case.dst_cpu}"
                ),
                case.reason or "",
            )
            for case in plan.cases
        ),
    )
    host_requirements = _table(
        ("PHASE", "REQUIREMENT", "CAPABILITY", "VALUES", "MUTATION", "PRIVILEGE"),
        (
            (
                phase.id,
                requirement.id,
                requirement.capability_id,
                _compact(dict(requirement.values)),
                requirement.mutation,
                requirement.requires_privilege,
            )
            for phase in plan.environment_phases
            for requirement in phase.host_requirements
        ),
    )
    case_requirements = _table(
        ("CASE", "REQUIREMENT", "CAPABILITY", "VALUES", "MUTATION", "PRIVILEGE"),
        (
            (
                case.id,
                requirement.id,
                requirement.capability_id,
                _compact(dict(requirement.values)),
                requirement.mutation,
                requirement.requires_privilege,
            )
            for case in plan.cases
            for requirement in case.execution_requirements
        ),
    )
    return (
        summary
        + "\nHOST REQUIREMENTS\n"
        + host_requirements
        + "\nCASES\n"
        + cases
        + "\nCASE REQUIREMENTS\n"
        + case_requirements
    )


def render_doctor(report: DoctorReport, output: str) -> str:
    if output == "json":
        return dump_json(to_data(report))
    summary = _table(
        ("FIELD", "VALUE"),
        (
            ("backend", report.backend_id),
            ("platform", report.platform_id or ""),
            ("observations", len(report.observations)),
            ("recovery_journals", len(report.journals)),
        ),
    )
    observations = _table(
        ("CAPABILITY", "STATUS", "VALUES", "FORMAL", "HINT"),
        (
            (
                observation.capability_id,
                observation.status,
                _compact(dict(observation.values)),
                observation.permits_formal_measurement,
                observation.hint or "",
            )
            for observation in report.observations
        ),
    )
    journals = _table(
        ("TRANSACTION", "STATE", "RESTORATION", "UPDATED"),
        (
            (
                journal.transaction_id,
                journal.state,
                journal.restoration_status,
                journal.updated_at,
            )
            for journal in report.journals
        ),
    )
    return (
        summary
        + "\nOBSERVATIONS\n"
        + observations
        + "\nRECOVERY JOURNALS\n"
        + journals
    )


def render_error(error: ProbeError, output: str) -> str:
    if output == "json":
        return dump_json(to_data(error))
    lines = [f"error: {error.message}"]
    lines.extend(f"{key}: {value}" for key, value in error.context)
    if error.hint:
        lines.append(f"hint: {error.hint}")
    return "\n".join(lines) + "\n"


def render_restore(journal: EnvironmentJournal, output: str) -> str:
    if output == "json":
        return dump_json(to_data(journal))
    summary = _table(
        ("FIELD", "VALUE"),
        (
            ("transaction", journal.transaction_id),
            ("state", journal.state),
            ("backend", journal.backend_id),
            ("platform", journal.platform_id),
            ("restoration_status", journal.restoration_status),
            ("applied", ",".join(journal.applied) or ""),
            ("active", journal.active_controller or ""),
            ("updated", journal.updated_at),
        ),
    )
    return summary


def render_run(result: RunResult, output: str) -> str:
    """Render a RunResult for display.

    Args:
        result: The RunResult to render
        output: Output format ("json" or "table")

    Returns:
        Formatted string representation
    """
    if output == "json":
        return dump_json(to_data(result))

    # Table format
    lines = []
    lines.append("Run Result")
    lines.append("=" * 80)
    lines.append(f"Run ID: {result.run_id}")
    lines.append(f"Plan: {result.plan.platform_id}")
    lines.append(f"Cases: {len(result.plan.cases)}")
    lines.append(f"Samples: {len(result.samples)}")
    lines.append("")

    lines.append("Samples:")
    lines.append("-" * 80)

    # Group samples by case_id
    samples_by_case: dict[str, list] = {}
    for sample in result.samples:
        if sample.case_id not in samples_by_case:
            samples_by_case[sample.case_id] = []
        samples_by_case[sample.case_id].append(sample)

    for case_id, samples in samples_by_case.items():
        lines.append(f"\nCase: {case_id}")

        # Get case info from plan
        case_info = None
        for case in result.plan.cases:
            if case.id == case_id:
                case_info = case
                break

        if case_info:
            lines.append(f"  Scenario: {case_info.scenario_id}")
            if case_info.cpu is not None:
                lines.append(f"  CPU: {case_info.cpu}")
            if case_info.src_cpu is not None:
                lines.append(f"  Source CPU: {case_info.src_cpu}")
            if case_info.dst_cpu is not None:
                lines.append(f"  Destination CPU: {case_info.dst_cpu}")

        # Show samples
        for i, sample in enumerate(samples):
            lines.append(f"\n  Sample {i + 1}:")
            lines.append(f"    Status: {sample.status}")

            if sample.metrics:
                lines.append("    Metrics:")
                metrics_dict = dict(sample.metrics)
                if "latency_ns" in metrics_dict:
                    lines.append(f"      Latency: {metrics_dict['latency_ns']:.2f} ns")
                if "accesses" in metrics_dict:
                    lines.append(f"      Accesses: {metrics_dict['accesses']}")
                if "elapsed_ns" in metrics_dict:
                    lines.append(f"      Elapsed: {metrics_dict['elapsed_ns'] / 1_000_000:.2f} ms")

    return "\n".join(lines) + "\n"


def render_resume(result: RunResult, output: str) -> str:
    """Render a resumed RunResult for display.

    Args:
        result: The RunResult to render (from a resume operation)
        output: Output format ("json" or "table")

    Returns:
        Formatted string representation
    """
    if output == "json":
        return dump_json(to_data(result))

    # Table format
    lines = []
    lines.append("Resume Result")
    lines.append("=" * 80)
    lines.append(f"Run ID: {result.run_id}")
    lines.append(f"Prior Run: {result.prior_run_id or 'N/A'}")
    lines.append(f"Resume Kind: {result.resume_kind or 'N/A'}")
    lines.append(f"Cases: {len(result.plan.cases)}")
    lines.append(f"Samples: {len(result.samples)}")

    # Extract summary details
    summary = dict(result.summary)
    if "carried_ok" in summary:
        lines.append(f"Carried (ok): {summary['carried_ok']}")
    if "re_executed" in summary:
        lines.append(f"Re-executed: {summary['re_executed']}")
    if "skipped_cases" in summary:
        lines.append(f"Dropped (skipped): {summary['skipped_cases']}")
    lines.append("")

    lines.append("Samples:")
    lines.append("-" * 80)

    for sample in result.samples:
        lines.append(f"\n  Case: {sample.case_id}")
        lines.append(f"    Status: {sample.status}")
        lines.append(f"    Run ID: {sample.run_id}")

        if sample.metrics:
            metrics_dict = dict(sample.metrics)
            if "latency_ns" in metrics_dict:
                lines.append(f"    Latency: {metrics_dict['latency_ns']:.2f} ns")

    return "\n".join(lines) + "\n"


def render_analyze(summary: AnalysisSummary, output_path: Path | None, output: str) -> str:
    """Render an AnalysisSummary for display.

    Args:
        summary: The AnalysisSummary to render
        output_path: Path where the analysis was written (may be None on error)
        output: Output format ("json" or "table")

    Returns:
        Formatted string representation
    """
    if output == "json":
        return dump_json(to_data(summary))

    lines = [
        f"Analysis: {summary.analysis_id}",
        f"Written: {output_path or '(not written)'}",
        f"Platform: {summary.platform_id}",
        f"Cases analyzed: {len(summary.case_analyses)}",
        f"Source runs: {', '.join(summary.source_runs)}",
        "",
    ]
    for ca in summary.case_analyses:
        metric_names = ", ".join(k for k, _ in ca.metric_stats)
        lines.append(
            f"  {ca.case_id}: {ca.status} "
            f"({ca.ok_samples}/{ca.total_samples} ok) "
            f"[{metric_names}]"
        )
    return "\n".join(lines) + "\n"


def render_report(
    summary: AnalysisSummary,
    manifest: ReportManifest,
    figures: tuple[FigureManifest, ...],
    output: str,
) -> str:
    """Render a report generation result for display.

    Args:
        summary: The source AnalysisSummary.
        manifest: The ReportManifest produced by ReportGenerator.write().
        figures: Tuple of FigureManifests produced by FigureGenerator.
        output: Output format ("json" or "table").

    Returns:
        Formatted string representation.
    """
    if output == "json":
        return dump_json(to_data(manifest))

    lines = [
        f"Report: {manifest.report_path}",
        f"Analysis: {summary.analysis_id}",
        f"Figures: {len(figures)}",
        f"Sections: {manifest.section_count}",
    ]
    return "\n".join(lines) + "\n"
