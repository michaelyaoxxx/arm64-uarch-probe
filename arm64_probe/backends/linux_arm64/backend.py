from arm64_probe.backends.base import MutationController
from arm64_probe.backends.io import HostFilesystem, HostRuntime
from arm64_probe.backends.linux_arm64.cpu_frequency import CpuFrequencyController
from arm64_probe.backends.linux_arm64.inspector import LinuxArm64Inspector
from arm64_probe.environment.models import CapabilityObservation


class LinuxArm64Backend:
    id = "linux-arm64"

    def __init__(self, filesystem: HostFilesystem, runtime: HostRuntime):
        self.inspector = LinuxArm64Inspector(filesystem, runtime)
        self.cpu_frequency = CpuFrequencyController(filesystem)

    def inspect(self) -> tuple[CapabilityObservation, ...]:
        observations = list(self.inspector.inspect())
        state = self.cpu_frequency.inspect()
        observations.append(
            CapabilityObservation(
                self.cpu_frequency.capability_id,
                state.status,
                state.values,
                state.evidence,
                None if state.status == "available" else "inspect Linux CPU frequency policies",
                state.status == "available",
            )
        )
        return tuple(sorted(observations, key=lambda item: item.capability_id))

    def controllers(self) -> tuple[MutationController, ...]:
        if self.cpu_frequency.inspect().status == "available":
            return (self.cpu_frequency,)
        return ()
