from dataclasses import dataclass


JsonScalar = str | int | float | bool | None


def _validate_mapping(
    values: tuple[tuple[str, JsonScalar], ...],
    label: str,
) -> None:
    keys = tuple(key for key, _ in values)
    if keys != tuple(sorted(set(keys))):
        raise ValueError(f"{label} must have sorted unique keys")


@dataclass(frozen=True)
class NamedCpuSet:
    id: str
    cpus: tuple[int, ...]


@dataclass(frozen=True)
class Capability:
    id: str
    description: str


@dataclass(frozen=True)
class ParameterSpec:
    id: str
    kind: str
    choices: tuple[JsonScalar, ...] = ()


@dataclass(frozen=True)
class ResolvedValue:
    value: JsonScalar
    source: str


@dataclass(frozen=True)
class EnvironmentRequirement:
    id: str
    capability_id: str
    scope: str
    values: tuple[tuple[str, JsonScalar], ...]
    mutation: bool
    requires_privilege: bool

    def __post_init__(self) -> None:
        if self.scope not in {"host", "case"}:
            raise ValueError(f"unsupported environment requirement scope: {self.scope}")
        _validate_mapping(self.values, "environment requirement values")


@dataclass(frozen=True)
class Platform:
    id: str
    display_name: str
    description: str
    measurement_support: str
    capabilities: tuple[str, ...]
    clusters: tuple[NamedCpuSet, ...]
    core_groups: tuple[NamedCpuSet, ...]
    representative_cpus: tuple[tuple[str, int], ...]
    defaults: tuple[tuple[str, JsonScalar], ...]
    environment_defaults: tuple[tuple[str, JsonScalar], ...] = ()


@dataclass(frozen=True)
class Scenario:
    id: str
    display_name: str
    cpu_mode: str
    required_capabilities: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]


@dataclass(frozen=True)
class Experiment:
    id: str
    display_name: str
    scenarios: tuple[Scenario, ...]


@dataclass(frozen=True)
class Profile:
    id: str
    display_name: str
    selections: tuple[str, ...]
    overrides: tuple[tuple[str, JsonScalar], ...]
    environment: tuple[tuple[str, JsonScalar], ...]


@dataclass(frozen=True)
class Case:
    id: str
    scenario_id: str
    platform_id: str
    status: str
    reason: str | None
    cpu: int | None
    src_cpu: int | None
    dst_cpu: int | None
    selectors: tuple[tuple[str, ResolvedValue], ...]
    parameters: tuple[tuple[str, ResolvedValue], ...]
    execution_requirements: tuple[EnvironmentRequirement, ...] = ()


@dataclass(frozen=True)
class EnvironmentPhase:
    id: str
    case_ids: tuple[str, ...]
    host_requirements: tuple[EnvironmentRequirement, ...]

    @property
    def requirements(self) -> tuple[tuple[str, JsonScalar], ...]:
        """Expose the Phase 1 scalar view until planning migrates in Task 3."""
        result: list[tuple[str, JsonScalar]] = []
        for requirement in self.host_requirements:
            if len(requirement.values) != 1 or requirement.values[0][0] != "value":
                raise ValueError(
                    f"requirement {requirement.id} has no Phase 1 scalar view"
                )
            result.append((requirement.id, requirement.values[0][1]))
        return tuple(result)


@dataclass(frozen=True)
class Plan:
    platform_id: str
    profile_id: str | None
    selections: tuple[str, ...]
    cases: tuple[Case, ...]
    environment_phases: tuple[EnvironmentPhase, ...]
    skip_unavailable: bool


@dataclass(frozen=True)
class Sample:
    run_id: str
    case_id: str
    sample_index: int
    status: str
    metrics: tuple[tuple[str, JsonScalar], ...]

    def __post_init__(self) -> None:
        if self.sample_index < 0:
            raise ValueError("sample_index must be nonnegative")
        if self.status not in {"ok", "error", "skipped"}:
            raise ValueError(f"unsupported sample status: {self.status}")


@dataclass(frozen=True)
class RunResult:
    run_id: str
    plan: Plan
    samples: tuple[Sample, ...]
    summary: tuple[tuple[str, JsonScalar], ...]
    environment: tuple[tuple[str, JsonScalar], ...]


def make_run_result(
    run_id: str,
    plan: Plan,
    samples: tuple[Sample, ...],
    summary: tuple[tuple[str, JsonScalar], ...],
    environment: tuple[tuple[str, JsonScalar], ...],
) -> RunResult:
    case_ids = {case.id for case in plan.cases}
    identities: set[tuple[str, int]] = set()
    for sample in samples:
        if sample.run_id != run_id:
            raise ValueError(
                f"sample run_id {sample.run_id} does not match result run_id {run_id}"
            )
        if sample.case_id not in case_ids:
            raise ValueError(f"sample references unknown case: {sample.case_id}")
        identity = (sample.case_id, sample.sample_index)
        if identity in identities:
            raise ValueError(f"duplicate sample identity: {identity}")
        identities.add(identity)
    return RunResult(run_id, plan, samples, summary, environment)
