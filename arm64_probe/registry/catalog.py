from dataclasses import dataclass
from pathlib import Path

from arm64_probe.domain.models import Capability, Experiment, Platform, Profile, Scenario
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.registry.validation import (
    load_capabilities,
    load_experiment,
    load_platform,
    load_profile,
)


def _config_error(message: str) -> ProbeError:
    return ProbeError(ExitCode.CONFIG, "configuration", message)


def _unique(items: tuple[object, ...], label: str) -> None:
    seen: set[str] = set()
    for item in items:
        item_id = getattr(item, "id")
        if item_id in seen:
            raise _config_error(f"duplicate {label} id: {item_id}")
        seen.add(item_id)


@dataclass(frozen=True)
class Catalog:
    _capabilities: tuple[Capability, ...]
    _platforms: tuple[Platform, ...]
    _experiments: tuple[Experiment, ...]
    _profiles: tuple[Profile, ...]

    @classmethod
    def load(cls, root: Path) -> "Catalog":
        configs = root / "configs"
        capabilities = load_capabilities(configs / "capabilities.json")
        platforms = tuple(
            load_platform(path) for path in sorted((configs / "platforms").glob("*.json"))
        )
        experiments = tuple(
            load_experiment(path)
            for path in sorted((configs / "experiments").glob("*.json"))
        )
        profiles = tuple(
            load_profile(path) for path in sorted((configs / "profiles").glob("*.json"))
        )
        _unique(capabilities, "capability")
        _unique(platforms, "platform")
        _unique(experiments, "experiment")
        _unique(profiles, "profile")
        scenarios = tuple(
            scenario for experiment in experiments for scenario in experiment.scenarios
        )
        _unique(scenarios, "scenario")
        catalog = cls(capabilities, platforms, experiments, profiles)
        catalog._validate_references()
        return catalog

    def capabilities(self) -> tuple[Capability, ...]:
        return self._capabilities

    def platforms(self) -> tuple[Platform, ...]:
        return self._platforms

    def experiments(self) -> tuple[Experiment, ...]:
        return self._experiments

    def profiles(self) -> tuple[Profile, ...]:
        return self._profiles

    def scenarios(self) -> tuple[Scenario, ...]:
        return tuple(
            scenario
            for experiment in self._experiments
            for scenario in experiment.scenarios
        )

    def expand_selection(self, target_id: str) -> tuple[Scenario, ...]:
        for experiment in self._experiments:
            if experiment.id == target_id:
                return experiment.scenarios
        for scenario in self.scenarios():
            if scenario.id == target_id:
                return (scenario,)
        raise _config_error(f"unknown target: {target_id}")

    def get_profile(self, profile_id: str) -> Profile:
        for profile in self._profiles:
            if profile.id == profile_id:
                return profile
        raise _config_error(f"unknown profile: {profile_id}")

    def get_platform(self, platform_id: str) -> Platform:
        for platform in self._platforms:
            if platform.id == platform_id:
                return platform
        raise _config_error(f"unknown platform: {platform_id}")

    def _validate_references(self) -> None:
        capabilities = {item.id for item in self._capabilities}
        scenarios = {item.id: item for item in self.scenarios()}
        experiments = {item.id for item in self._experiments}
        targets = experiments | set(scenarios)
        parameters = {
            scenario.id: {parameter.id for parameter in scenario.parameters}
            for scenario in scenarios.values()
        }
        all_parameters = set().union(*parameters.values())
        for platform in self._platforms:
            unknown = set(platform.capabilities) - capabilities
            if unknown:
                raise _config_error(
                    f"platform {platform.id} references unknown capability: {min(unknown)}"
                )
            for key, _ in platform.defaults:
                if key in all_parameters:
                    continue
                scenario_id, separator, parameter_id = key.rpartition(".")
                if (
                    not separator
                    or scenario_id not in parameters
                    or parameter_id not in parameters[scenario_id]
                ):
                    raise _config_error(
                        f"platform {platform.id} has unknown scoped default: {key}"
                    )
        for scenario in scenarios.values():
            unknown = set(scenario.required_capabilities) - capabilities
            if unknown:
                raise _config_error(
                    f"scenario {scenario.id} references unknown capability: {min(unknown)}"
                )
        for profile in self._profiles:
            for selection in profile.selections:
                if selection not in targets:
                    raise _config_error(
                        f"profile {profile.id} references unknown selection: {selection}"
                    )
