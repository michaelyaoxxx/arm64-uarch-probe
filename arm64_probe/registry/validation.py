from pathlib import Path
from typing import Any

from arm64_probe.domain.ids import (
    validate_capability_id,
    validate_id,
    validate_scenario_id,
)
from arm64_probe.domain.models import (
    Capability,
    Experiment,
    JsonScalar,
    NamedCpuSet,
    ParameterSpec,
    Platform,
    Profile,
    Scenario,
)
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.serialization.json_io import load_json


PLATFORM_FIELDS = {
    "id",
    "display_name",
    "description",
    "measurement_support",
    "capabilities",
    "clusters",
    "core_groups",
    "representative_cpus",
    "defaults",
}


def _error(path: Path, message: str) -> ProbeError:
    return ProbeError(ExitCode.CONFIG, "configuration", f"{path}: {message}")


def _require_fields(
    path: Path,
    value: dict[str, Any],
    required: set[str],
) -> None:
    unknown = sorted(set(value) - required)
    missing = sorted(required - set(value))
    if unknown:
        raise _error(path, f"unknown field: {unknown[0]}")
    if missing:
        raise _error(path, f"missing field: {missing[0]}")


def _canonical(path: Path, value: object, label: str) -> str:
    if not isinstance(value, str):
        raise _error(path, f"{label} must be a string")
    try:
        return validate_id(value)
    except ValueError as error:
        raise _error(path, str(error)) from error


def _string(path: Path, value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error(path, f"{label} must be a nonempty string")
    return value


def _cpu_sets(path: Path, value: object, label: str) -> tuple[NamedCpuSet, ...]:
    if not isinstance(value, list) or not value:
        raise _error(path, f"{label} must be a nonempty array")
    result: list[NamedCpuSet] = []
    seen_ids: set[str] = set()
    seen_cpus: set[int] = set()
    for item in value:
        if not isinstance(item, dict):
            raise _error(path, f"{label} entries must be objects")
        _require_fields(path, item, {"id", "cpus"})
        item_id = _canonical(path, item["id"], f"{label} id")
        cpus = item["cpus"]
        if (
            not isinstance(cpus, list)
            or not cpus
            or any(not isinstance(cpu, int) or isinstance(cpu, bool) or cpu < 0 for cpu in cpus)
            or cpus != sorted(set(cpus))
        ):
            raise _error(path, f"{label} {item_id} CPUs must be sorted unique nonnegative integers")
        if item_id in seen_ids:
            raise _error(path, f"duplicate {label} id: {item_id}")
        overlap = seen_cpus.intersection(cpus)
        if overlap:
            raise _error(path, f"{label} CPU overlap: {min(overlap)}")
        seen_ids.add(item_id)
        seen_cpus.update(cpus)
        result.append(NamedCpuSet(item_id, tuple(cpus)))
    return tuple(sorted(result, key=lambda item: item.id))


def _string_list(path: Path, value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _error(path, f"{label} must be an array")
    try:
        result = tuple(validate_capability_id(item) for item in value)
    except (TypeError, ValueError) as error:
        raise _error(path, str(error)) from error
    if len(result) != len(set(result)):
        raise _error(path, f"duplicate {label}")
    return tuple(sorted(result))


def _scalar_mapping(
    path: Path,
    value: object,
    label: str,
) -> tuple[tuple[str, JsonScalar], ...]:
    if not isinstance(value, dict):
        raise _error(path, f"{label} must be an object")
    result: list[tuple[str, JsonScalar]] = []
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise _error(path, f"{label} keys must be nonempty strings")
        if item is not None and not isinstance(item, (str, int, float, bool)):
            raise _error(path, f"{label}.{key} must be a JSON scalar")
        result.append((key, item))
    return tuple(sorted(result))


def load_capabilities(path: Path) -> tuple[Capability, ...]:
    payload = load_json(path)
    _require_fields(path, payload, {"capabilities"})
    raw = payload["capabilities"]
    if not isinstance(raw, list):
        raise _error(path, "capabilities must be an array")
    result: list[Capability] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise _error(path, "capability entries must be objects")
        _require_fields(path, item, {"id", "description"})
        try:
            item_id = validate_capability_id(item["id"])
        except (TypeError, ValueError) as error:
            raise _error(path, str(error)) from error
        if item_id in seen:
            raise _error(path, f"duplicate capability id: {item_id}")
        seen.add(item_id)
        result.append(Capability(item_id, _string(path, item["description"], "description")))
    return tuple(sorted(result, key=lambda item: item.id))


def load_platform(path: Path) -> Platform:
    payload = load_json(path)
    _require_fields(path, payload, PLATFORM_FIELDS)
    platform_id = _canonical(path, payload["id"], "platform id")
    support = payload["measurement_support"]
    if support not in {"supported", "contract-only"}:
        raise _error(path, "measurement_support must be supported or contract-only")
    clusters = _cpu_sets(path, payload["clusters"], "clusters")
    core_groups = _cpu_sets(path, payload["core_groups"], "core_groups")
    cluster_map = {item.id: set(item.cpus) for item in clusters}
    group_map = {item.id: set(item.cpus) for item in core_groups}
    raw_representatives = payload["representative_cpus"]
    if not isinstance(raw_representatives, dict):
        raise _error(path, "representative_cpus must be an object")
    representatives: list[tuple[str, int]] = []
    for key, cpu in raw_representatives.items():
        if not isinstance(key, str) or key.count(".") != 1:
            raise _error(path, f"invalid representative key: {key!r}")
        cluster_id, group_id = key.split(".")
        if cluster_id not in cluster_map or group_id not in group_map:
            raise _error(path, f"unknown representative selector: {key}")
        if (
            not isinstance(cpu, int)
            or isinstance(cpu, bool)
            or cpu not in cluster_map[cluster_id].intersection(group_map[group_id])
        ):
            raise _error(path, f"representative CPU for {key} is outside its selector intersection")
        representatives.append((key, cpu))
    return Platform(
        id=platform_id,
        display_name=_string(path, payload["display_name"], "display_name"),
        description=_string(path, payload["description"], "description"),
        measurement_support=support,
        capabilities=_string_list(path, payload["capabilities"], "capabilities"),
        clusters=clusters,
        core_groups=core_groups,
        representative_cpus=tuple(sorted(representatives)),
        defaults=_scalar_mapping(path, payload["defaults"], "defaults"),
    )


def _capability_list(path: Path, value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _error(path, "required_capabilities must be an array")
    try:
        result = tuple(validate_capability_id(item) for item in value)
    except (TypeError, ValueError) as error:
        raise _error(path, str(error)) from error
    if len(result) != len(set(result)):
        raise _error(path, "duplicate required capability")
    return tuple(sorted(result))


def _parameters(path: Path, value: object) -> tuple[ParameterSpec, ...]:
    if not isinstance(value, list) or not value:
        raise _error(path, "parameters must be a nonempty array")
    result: list[ParameterSpec] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise _error(path, "parameter entries must be objects")
        _require_fields(path, item, {"id", "kind", "choices"})
        item_id = _canonical(path, item["id"], "parameter id")
        if item_id in seen:
            raise _error(path, f"duplicate parameter id: {item_id}")
        kind = item["kind"]
        if kind not in {"integer", "size", "string"}:
            raise _error(path, f"unknown parameter kind: {kind}")
        choices = item["choices"]
        if not isinstance(choices, list) or any(
            choice is not None and not isinstance(choice, (str, int, float, bool))
            for choice in choices
        ):
            raise _error(path, f"parameter {item_id} choices must be JSON scalars")
        seen.add(item_id)
        result.append(ParameterSpec(item_id, kind, tuple(choices)))
    return tuple(result)


def load_experiment(path: Path) -> Experiment:
    payload = load_json(path)
    _require_fields(path, payload, {"id", "display_name", "scenarios"})
    experiment_id = _canonical(path, payload["id"], "experiment id")
    raw_scenarios = payload["scenarios"]
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise _error(path, "scenarios must be a nonempty array")
    scenarios: list[Scenario] = []
    seen: set[str] = set()
    for item in raw_scenarios:
        if not isinstance(item, dict):
            raise _error(path, "scenario entries must be objects")
        _require_fields(
            path,
            item,
            {
                "id",
                "display_name",
                "cpu_mode",
                "required_capabilities",
                "parameters",
            },
        )
        try:
            scenario_id = validate_scenario_id(item["id"])
        except (TypeError, ValueError) as error:
            raise _error(path, str(error)) from error
        if not scenario_id.startswith(f"{experiment_id}."):
            raise _error(path, f"scenario {scenario_id} does not belong to {experiment_id}")
        if scenario_id in seen:
            raise _error(path, f"duplicate scenario id: {scenario_id}")
        cpu_mode = item["cpu_mode"]
        if cpu_mode not in {
            "single",
            "pair-same-core",
            "pair-same-cluster",
            "pair-cross-cluster",
        }:
            raise _error(path, f"unknown CPU mode: {cpu_mode}")
        seen.add(scenario_id)
        scenarios.append(
            Scenario(
                id=scenario_id,
                display_name=_string(path, item["display_name"], "display_name"),
                cpu_mode=cpu_mode,
                required_capabilities=_capability_list(
                    path, item["required_capabilities"]
                ),
                parameters=_parameters(path, item["parameters"]),
            )
        )
    return Experiment(
        experiment_id,
        _string(path, payload["display_name"], "display_name"),
        tuple(scenarios),
    )


def load_profile(path: Path) -> Profile:
    payload = load_json(path)
    _require_fields(
        path,
        payload,
        {"id", "display_name", "selections", "overrides", "environment"},
    )
    selections = payload["selections"]
    if (
        not isinstance(selections, list)
        or not selections
        or any(not isinstance(item, str) or not item for item in selections)
    ):
        raise _error(path, "selections must be a nonempty string array")
    if len(selections) != len(set(selections)):
        raise _error(path, "duplicate profile selection")
    environment = _scalar_mapping(path, payload["environment"], "environment")
    allowed_environment = {"cpu-governor", "cpu-frequency-policy", "hugepages"}
    for key, value in environment:
        if key not in allowed_environment:
            raise _error(path, f"unknown environment field: {key}")
        if key == "hugepages":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise _error(path, "hugepages must be a nonnegative integer")
        elif not isinstance(value, str) or not value:
            raise _error(path, f"{key} must be a nonempty string")
    return Profile(
        id=_canonical(path, payload["id"], "profile id"),
        display_name=_string(path, payload["display_name"], "display_name"),
        selections=tuple(selections),
        overrides=_scalar_mapping(path, payload["overrides"], "overrides"),
        environment=environment,
    )
