from dataclasses import dataclass

from arm64_probe.domain.models import JsonScalar, ResolvedValue, Scenario


@dataclass(frozen=True)
class PlanRequest:
    platform_id: str = "auto"
    profile_id: str | None = None
    selections: tuple[str, ...] = ()
    cluster: str | None = None
    core_group: str | None = None
    cpu: int | None = None
    src_cpu: int | None = None
    dst_cpu: int | None = None
    overrides: tuple[tuple[str, JsonScalar], ...] = ()
    skip_unavailable: bool = False


@dataclass(frozen=True)
class ResolvedScenario:
    scenario: Scenario
    parameters: tuple[tuple[str, ResolvedValue], ...]
    environment: tuple[tuple[str, JsonScalar], ...]
