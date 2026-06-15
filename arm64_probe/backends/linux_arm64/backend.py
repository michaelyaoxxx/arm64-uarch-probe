from arm64_probe.backends.base import MutationController
from arm64_probe.backends.io import HostFilesystem, HostRuntime
from arm64_probe.backends.linux_arm64.cpu_frequency import CpuFrequencyController
from arm64_probe.backends.linux_arm64.hugepage import HugepageController
from arm64_probe.backends.linux_arm64.inspector import LinuxArm64Inspector
from arm64_probe.backends.linux_arm64.transparent_hugepage import (
    TransparentHugepageController,
)
from arm64_probe.environment.models import CapabilityObservation


class LinuxArm64Backend:
    id = "linux-arm64"

    def __init__(self, filesystem: HostFilesystem, runtime: HostRuntime):
        self.inspector = LinuxArm64Inspector(filesystem, runtime)
        self.cpu_frequency = CpuFrequencyController(filesystem)
        self.hugepage = HugepageController(filesystem)
        self.transparent_hugepage = TransparentHugepageController(filesystem)
        self._controllers = (
            self.cpu_frequency,
            self.hugepage,
            self.transparent_hugepage,
        )

    def inspect(self) -> tuple[CapabilityObservation, ...]:
        observations = list(self.inspector.inspect())
        for controller in self._controllers:
            state = controller.inspect()
            observations.append(
                CapabilityObservation(
                    controller.capability_id,
                    state.status,
                    state.values,
                    state.evidence,
                    None
                    if state.status == "available"
                    else f"inspect {controller.capability_id} interfaces",
                    state.status == "available",
                )
            )
        return tuple(sorted(observations, key=lambda item: item.capability_id))

    def controllers(self) -> tuple[MutationController, ...]:
        return tuple(
            controller
            for controller in self._controllers
            if controller.inspect().status == "available"
        )
