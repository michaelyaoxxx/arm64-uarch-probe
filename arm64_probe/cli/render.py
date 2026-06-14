import json
from collections.abc import Iterable
from typing import Any

from arm64_probe.domain.models import Plan
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
    return summary + "\n" + cases


def render_error(error: ProbeError, output: str) -> str:
    if output == "json":
        return dump_json(to_data(error))
    lines = [f"error: {error.message}"]
    lines.extend(f"{key}: {value}" for key, value in error.context)
    if error.hint:
        lines.append(f"hint: {error.hint}")
    return "\n".join(lines) + "\n"
