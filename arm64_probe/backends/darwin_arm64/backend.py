from arm64_probe.backends.base import MutationController
from arm64_probe.backends.io import HostRuntime
from arm64_probe.environment.models import CapabilityObservation


UNSUPPORTED_CAPABILITIES = (
    "cpu-binding",
    "linux.cpufreq",
    "linux.hugepage",
    "linux.transparent-hugepage",
    "pmu.armv9",
)


class DarwinArm64Backend:
    id = "darwin-arm64"

    def __init__(self, runtime: HostRuntime, system: str, machine: str):
        self.runtime = runtime
        self.system = system
        self.machine = machine

    def inspect(self) -> tuple[CapabilityObservation, ...]:
        observations = [
            CapabilityObservation(
                "host.os",
                "available",
                (("architecture", self.machine), ("system", self.system)),
                (f"platform={self.system}/{self.machine}",),
                None,
                False,
            ),
            self._load(),
        ]
        observations.extend(
            CapabilityObservation(
                capability_id,
                "unsupported",
                (),
                (f"{self.id}:{capability_id}=unsupported",),
                "use a supported Linux ARM64 measurement host",
                False,
            )
            for capability_id in UNSUPPORTED_CAPABILITIES
        )
        return tuple(sorted(observations, key=lambda item: item.capability_id))

    def controllers(self) -> tuple[MutationController, ...]:
        return ()

    def _load(self) -> CapabilityObservation:
        try:
            one, five, fifteen = self.runtime.load_average()
        except OSError:
            return CapabilityObservation(
                "host.load",
                "unavailable",
                (),
                ("os.getloadavg:unavailable",),
                "load average is unavailable",
                False,
            )
        return CapabilityObservation(
            "host.load",
            "available",
            (("load-15m", fifteen), ("load-1m", one), ("load-5m", five)),
            (f"os.getloadavg={one},{five},{fifteen}",),
            None,
            True,
        )
