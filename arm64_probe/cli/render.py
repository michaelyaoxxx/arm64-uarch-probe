import json
from collections.abc import Iterable
from typing import Any

from arm64_probe.domain.models import Plan
from arm64_probe.environment.models import DoctorReport
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
