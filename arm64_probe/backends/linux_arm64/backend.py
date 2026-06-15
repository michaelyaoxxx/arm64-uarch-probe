from arm64_probe.backends.base import MutationController
from arm64_probe.backends.io import HostFilesystem, HostRuntime
from arm64_probe.backends.linux_arm64.inspector import LinuxArm64Inspector
from arm64_probe.environment.models import CapabilityObservation


class LinuxArm64Backend:
    id = "linux-arm64"

    def __init__(self, filesystem: HostFilesystem, runtime: HostRuntime):
        self.inspector = LinuxArm64Inspector(filesystem, runtime)

    def inspect(self) -> tuple[CapabilityObservation, ...]:
        return self.inspector.inspect()

    def controllers(self) -> tuple[MutationController, ...]:
        return ()
