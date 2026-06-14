from typing import Any

from arm64_probe.domain.models import (
    Capability,
    Case,
    EnvironmentPhase,
    Experiment,
    NamedCpuSet,
    ParameterSpec,
    Plan,
    Platform,
    Profile,
    ResolvedValue,
    RunResult,
    Sample,
    Scenario,
)
from arm64_probe.errors import ProbeError


def _mapping(items: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    return {key: to_data(value) for key, value in sorted(items)}


def to_data(value: object) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [to_data(item) for item in value]
    if isinstance(value, Capability):
        return {"id": value.id, "description": value.description}
    if isinstance(value, NamedCpuSet):
        return {"id": value.id, "cpus": to_data(value.cpus)}
    if isinstance(value, ParameterSpec):
        return {
            "id": value.id,
            "kind": value.kind,
            "choices": to_data(value.choices),
        }
    if isinstance(value, ResolvedValue):
        return {"value": to_data(value.value), "source": value.source}
    if isinstance(value, Platform):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "description": value.description,
            "measurement_support": value.measurement_support,
            "capabilities": to_data(value.capabilities),
            "clusters": to_data(value.clusters),
            "core_groups": to_data(value.core_groups),
            "representative_cpus": _mapping(value.representative_cpus),
            "defaults": _mapping(value.defaults),
        }
    if isinstance(value, Scenario):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "cpu_mode": value.cpu_mode,
            "required_capabilities": to_data(value.required_capabilities),
            "parameters": to_data(value.parameters),
        }
    if isinstance(value, Experiment):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "scenarios": to_data(value.scenarios),
        }
    if isinstance(value, Profile):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "selections": to_data(value.selections),
            "overrides": _mapping(value.overrides),
            "environment": _mapping(value.environment),
        }
    if isinstance(value, Case):
        return {
            "id": value.id,
            "scenario_id": value.scenario_id,
            "platform_id": value.platform_id,
            "status": value.status,
            "reason": value.reason,
            "cpu": value.cpu,
            "src_cpu": value.src_cpu,
            "dst_cpu": value.dst_cpu,
            "selectors": _mapping(value.selectors),
            "parameters": _mapping(value.parameters),
        }
    if isinstance(value, EnvironmentPhase):
        return {
            "id": value.id,
            "case_ids": to_data(value.case_ids),
            "requirements": _mapping(value.requirements),
        }
    if isinstance(value, Plan):
        return {
            "platform_id": value.platform_id,
            "profile_id": value.profile_id,
            "selections": to_data(value.selections),
            "cases": to_data(value.cases),
            "environment_phases": to_data(value.environment_phases),
            "skip_unavailable": value.skip_unavailable,
        }
    if isinstance(value, Sample):
        return {
            "run_id": value.run_id,
            "case_id": value.case_id,
            "sample_index": value.sample_index,
            "status": value.status,
            "metrics": _mapping(value.metrics),
        }
    if isinstance(value, RunResult):
        return {
            "run_id": value.run_id,
            "plan": to_data(value.plan),
            "samples": to_data(value.samples),
            "summary": _mapping(value.summary),
            "environment": _mapping(value.environment),
        }
    if isinstance(value, ProbeError):
        return {
            "code": int(value.code),
            "category": value.category,
            "message": value.message,
            "context": _mapping(value.context),
            "hint": value.hint,
        }
    raise TypeError(f"unsupported public serialization type: {type(value).__name__}")
