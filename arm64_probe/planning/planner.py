import re

from arm64_probe.domain.ids import build_case_id
from arm64_probe.domain.models import (
    Case,
    EnvironmentPhase,
    JsonScalar,
    ParameterSpec,
    Plan,
    ResolvedValue,
    Scenario,
)
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.platforms.configured import ConfiguredPlatformAdapter
from arm64_probe.planning.request import PlanRequest, ResolvedScenario
from arm64_probe.registry.catalog import Catalog


SIZE_RE = re.compile(r"^[1-9][0-9]*(?:KiB|MiB|GiB)$", re.ASCII)


def _planning_error(message: str, hint: str | None = None) -> ProbeError:
    return ProbeError(ExitCode.PLANNING, "planning", message, hint=hint)


def _as_unique_mapping(
    values: tuple[tuple[str, JsonScalar], ...],
    label: str,
) -> dict[str, JsonScalar]:
    result: dict[str, JsonScalar] = {}
    for key, value in values:
        if key in result:
            raise _planning_error(f"duplicate {label}: {key}")
        result[key] = value
    return result


def _validate_value(spec: ParameterSpec, value: JsonScalar) -> None:
    if spec.kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool) and value > 0
    elif spec.kind == "size":
        valid = isinstance(value, str) and SIZE_RE.fullmatch(value) is not None
    elif spec.kind == "string":
        valid = isinstance(value, str) and (
            not spec.choices or value in spec.choices
        )
    else:
        valid = False
    if not valid:
        raise _planning_error(f"invalid value for {spec.id}: {value!r}")


class Planner:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.adapter = ConfiguredPlatformAdapter()

    def plan(self, request: PlanRequest) -> Plan:
        platform = self._platform(request.platform_id)
        profile = self._profile(request.profile_id)
        resolved = self.resolve(request)
        self._validate_selector_applicability(request, resolved)
        cases_with_requirements: list[
            tuple[Case, tuple[tuple[str, JsonScalar], ...]]
        ] = []
        for item in resolved:
            case, requirements = self._case(platform, request, item)
            cases_with_requirements.append((case, requirements))
        cases = tuple(
            sorted(
                (case for case, _ in cases_with_requirements),
                key=lambda case: (
                    case.scenario_id,
                    case.platform_id,
                    case.cpu if case.cpu is not None else -1,
                    case.src_cpu if case.src_cpu is not None else -1,
                    case.dst_cpu if case.dst_cpu is not None else -1,
                    case.id,
                ),
            )
        )
        requirements_by_case = {
            case.id: requirements for case, requirements in cases_with_requirements
        }
        phases = self._environment_phases(cases, requirements_by_case)
        return Plan(
            platform_id=platform.id,
            profile_id=profile.id if profile else None,
            selections=tuple(case.scenario_id for case in cases),
            cases=cases,
            environment_phases=phases,
            skip_unavailable=request.skip_unavailable,
        )

    def resolve(self, request: PlanRequest) -> tuple[ResolvedScenario, ...]:
        platform = self._platform(request.platform_id)
        profile = self._profile(request.profile_id)
        scenarios = self._scenarios(request, profile)
        platform_defaults = dict(platform.defaults)
        profile_overrides = (
            _as_unique_mapping(profile.overrides, "profile override") if profile else {}
        )
        cli_overrides = _as_unique_mapping(request.overrides, "CLI override")
        common_parameters = set.intersection(
            *({parameter.id for parameter in scenario.parameters} for scenario in scenarios)
        )
        for key in (*profile_overrides, *cli_overrides):
            if key not in common_parameters:
                raise _planning_error(
                    f"parameter {key} does not apply to every selected scenario"
                )
        result: list[ResolvedScenario] = []
        for scenario in scenarios:
            parameters: list[tuple[str, ResolvedValue]] = []
            for spec in scenario.parameters:
                scoped_key = f"{scenario.id}.{spec.id}"
                if scoped_key in platform_defaults:
                    value = platform_defaults[scoped_key]
                elif spec.id in platform_defaults:
                    value = platform_defaults[spec.id]
                else:
                    raise _planning_error(
                        f"platform {platform.id} has no default for {scenario.id}.{spec.id}"
                    )
                source = "platform-default"
                if spec.id in profile_overrides:
                    value = profile_overrides[spec.id]
                    source = "profile"
                if spec.id in cli_overrides:
                    value = cli_overrides[spec.id]
                    source = "cli"
                _validate_value(spec, value)
                parameters.append((spec.id, ResolvedValue(value, source)))
            result.append(
                ResolvedScenario(
                    scenario,
                    tuple(sorted(parameters)),
                    profile.environment if profile else (),
                )
            )
        return tuple(result)

    def _platform(self, platform_id: str):
        if platform_id == "auto":
            raise ProbeError(
                ExitCode.CAPABILITY,
                "platform",
                "auto platform resolution belongs to the CLI boundary",
            )
        try:
            return self.catalog.get_platform(platform_id)
        except ProbeError as error:
            raise ProbeError(
                ExitCode.CAPABILITY,
                "platform",
                error.message,
                hint="use `probe list platforms`",
            ) from error

    def _profile(self, profile_id: str | None):
        if profile_id is None:
            return None
        try:
            return self.catalog.get_profile(profile_id)
        except ProbeError as error:
            raise _planning_error(
                error.message,
                hint="use `probe list profiles`",
            ) from error

    def _scenarios(self, request: PlanRequest, profile) -> tuple[Scenario, ...]:
        selections = list(profile.selections if profile else ())
        selections.extend(request.selections)
        if not selections:
            raise _planning_error("plan requires at least one profile or selection")
        selected: set[str] = set()
        for selection in selections:
            try:
                selected.update(
                    scenario.id for scenario in self.catalog.expand_selection(selection)
                )
            except ProbeError as error:
                raise _planning_error(
                    f"unknown selection: {selection}",
                    hint="use `probe list targets`",
                ) from error
        return tuple(
            scenario for scenario in self.catalog.scenarios() if scenario.id in selected
        )

    def _validate_selector_applicability(
        self,
        request: PlanRequest,
        resolved: tuple[ResolvedScenario, ...],
    ) -> None:
        has_single = any(item.scenario.cpu_mode == "single" for item in resolved)
        has_pair = any(item.scenario.cpu_mode != "single" for item in resolved)
        if request.cpu is not None and has_pair:
            raise _planning_error("--cpu does not apply to selected migration scenarios")
        if (request.src_cpu is not None or request.dst_cpu is not None) and has_single:
            raise _planning_error(
                "--src-cpu and --dst-cpu do not apply to selected single-CPU scenarios"
            )

    def _case(
        self,
        platform,
        request: PlanRequest,
        resolved: ResolvedScenario,
    ) -> tuple[Case, tuple[tuple[str, JsonScalar], ...]]:
        parameters = dict(resolved.parameters)
        page_policy = parameters["page-policy"].value
        working_set = parameters["working-set"].value
        requirements = dict(resolved.environment)
        requirements["page-policy"] = page_policy
        capability_requirements = set(resolved.scenario.required_capabilities)
        if page_policy == "hugepage" or requirements.get("hugepages", 0):
            capability_requirements.add("linux.hugepage")
        if "cpu-governor" in requirements or "cpu-frequency-policy" in requirements:
            capability_requirements.add("linux.cpufreq")

        selectors: list[tuple[str, ResolvedValue]] = []
        if request.cluster is not None:
            selectors.append(("cluster", ResolvedValue(request.cluster, "cli")))
        if request.core_group is not None:
            selectors.append(("core-group", ResolvedValue(request.core_group, "cli")))
        try:
            if resolved.scenario.cpu_mode == "single":
                cpu, source = self.adapter.resolve_single(
                    platform,
                    request.cluster,
                    request.core_group,
                    request.cpu,
                )
                src_cpu = dst_cpu = None
                selectors.append(("cpu", ResolvedValue(cpu, source)))
                dimensions = self._single_dimensions(
                    request,
                    cpu,
                    working_set,
                    page_policy,
                )
                blocked = cpu is None
            else:
                cpu = None
                src_cpu, dst_cpu, source = self.adapter.resolve_pair(
                    platform,
                    resolved.scenario.cpu_mode,
                    request.cluster,
                    request.core_group,
                    request.src_cpu,
                    request.dst_cpu,
                )
                selectors.append(
                    (
                        "src-cpu",
                        ResolvedValue(
                            src_cpu,
                            "cli" if request.src_cpu is not None else source,
                        ),
                    )
                )
                selectors.append(
                    (
                        "dst-cpu",
                        ResolvedValue(
                            dst_cpu,
                            "cli" if request.dst_cpu is not None else source,
                        ),
                    )
                )
                dimensions = (
                    f"src-{src_cpu}" if src_cpu is not None else "src-unresolved",
                    f"dst-{dst_cpu}" if dst_cpu is not None else "dst-unresolved",
                    self._dimension(working_set),
                    self._dimension(page_policy),
                )
                blocked = src_cpu is None or dst_cpu is None
        except ValueError as error:
            raise _planning_error(str(error)) from error

        missing = sorted(capability_requirements - set(platform.capabilities))
        if blocked:
            status = "blocked"
            reason = "semantic CPU selectors did not resolve a complete case"
        elif missing:
            status = "unsupported"
            reason = f"missing capabilities: {', '.join(missing)}"
        else:
            status = "ready"
            reason = None
        case = Case(
            id=build_case_id(resolved.scenario.id, platform.id, dimensions),
            scenario_id=resolved.scenario.id,
            platform_id=platform.id,
            status=status,
            reason=reason,
            cpu=cpu,
            src_cpu=src_cpu,
            dst_cpu=dst_cpu,
            selectors=tuple(sorted(selectors)),
            parameters=resolved.parameters,
        )
        return case, tuple(sorted(requirements.items()))

    def _single_dimensions(
        self,
        request: PlanRequest,
        cpu: int | None,
        working_set: JsonScalar,
        page_policy: JsonScalar,
    ) -> tuple[str, ...]:
        if request.cpu is not None:
            cpu_dimension = f"cpu-{request.cpu}"
        elif request.core_group is not None:
            cpu_dimension = request.core_group
        elif cpu is not None:
            cpu_dimension = f"cpu-{cpu}"
        else:
            cpu_dimension = "cpu-unresolved"
        return (
            self._dimension(cpu_dimension),
            self._dimension(request.cluster or "any"),
            self._dimension(working_set),
            self._dimension(page_policy),
        )

    @staticmethod
    def _dimension(value: JsonScalar) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
        if not normalized:
            raise _planning_error(f"cannot normalize case dimension: {value!r}")
        return normalized

    @staticmethod
    def _environment_phases(
        cases: tuple[Case, ...],
        requirements_by_case: dict[str, tuple[tuple[str, JsonScalar], ...]],
    ) -> tuple[EnvironmentPhase, ...]:
        groups: dict[tuple[tuple[str, JsonScalar], ...], list[str]] = {}
        for case in cases:
            requirements = requirements_by_case[case.id]
            groups.setdefault(requirements, []).append(case.id)
        phases = [
            EnvironmentPhase(
                id=f"phase-{index}",
                case_ids=tuple(case_ids),
                requirements=requirements,
            )
            for index, (requirements, case_ids) in enumerate(
                sorted(groups.items(), key=lambda item: repr(item[0])),
                start=1,
            )
        ]
        return tuple(phases)
