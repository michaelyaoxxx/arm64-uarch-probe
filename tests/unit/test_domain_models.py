import dataclasses
import unittest

from arm64_probe.domain.models import (
    Capability,
    Case,
    EnvironmentPhase,
    EnvironmentRequirement,
    Experiment,
    NamedCpuSet,
    ParameterSpec,
    Plan,
    Platform,
    Profile,
    ResolvedValue,
    Scenario,
)


def build_models():
    capability = Capability("cpu-binding", "bind a logical CPU")
    cpu_set = NamedCpuSet("c0", (0, 1))
    parameter = ParameterSpec("samples", "integer")
    resolved = ResolvedValue(7, "platform-default")
    platform = Platform(
        id="gb10",
        display_name="NVIDIA GB10",
        description="GB10 measurement platform",
        measurement_support="supported",
        capabilities=("cpu-binding",),
        clusters=(cpu_set,),
        core_groups=(NamedCpuSet("x925", (0, 1)),),
        representative_cpus=(("c0.x925", 0),),
        defaults=(("samples", 7),),
        environment_defaults=(),
    )
    scenario = Scenario(
        id="cache-latency.l1-latency",
        display_name="L1 latency",
        cpu_mode="single",
        required_capabilities=("cpu-binding",),
        parameters=(parameter,),
    )
    experiment = Experiment("cache-latency", "Cache latency", (scenario,))
    profile = Profile(
        "smoke",
        "Smoke",
        (scenario.id,),
        (("samples", 1),),
        (),
    )
    case = Case(
        id="cache-latency.l1-latency@gb10.x925.c0.32kib.default",
        scenario_id=scenario.id,
        platform_id=platform.id,
        status="ready",
        reason=None,
        cpu=0,
        src_cpu=None,
        dst_cpu=None,
        selectors=(("cpu", ResolvedValue(0, "platform-selector:x925")),),
        parameters=(("samples", resolved),),
        execution_requirements=(
            EnvironmentRequirement(
                "cpu-affinity",
                "cpu-binding",
                "case",
                (("selection", "cpu-0"),),
                False,
                False,
            ),
        ),
    )
    phase = EnvironmentPhase(
        "default",
        (case.id,),
        (
            EnvironmentRequirement(
                "cpu-frequency",
                "linux.cpufreq",
                "host",
                (("governor", "performance"),),
                True,
                True,
            ),
        ),
    )
    plan = Plan(platform.id, profile.id, (scenario.id,), (case,), (phase,), False)
    return (
        capability,
        cpu_set,
        parameter,
        resolved,
        platform,
        scenario,
        experiment,
        profile,
        case,
        case.execution_requirements[0],
        phase,
        plan,
    )


class DomainModelTests(unittest.TestCase):
    def test_models_are_frozen(self):
        for model in build_models():
            with self.subTest(model=type(model).__name__):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    model.id = "changed"

    def test_models_use_immutable_collections(self):
        for model in build_models():
            for field in dataclasses.fields(model):
                value = getattr(model, field.name)
                with self.subTest(model=type(model).__name__, field=field.name):
                    self.assertNotIsInstance(value, (dict, list, set))

    def test_same_logical_models_compare_equal(self):
        self.assertEqual(build_models(), build_models())


if __name__ == "__main__":
    unittest.main()
