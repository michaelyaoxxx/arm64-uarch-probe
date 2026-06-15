import platform
from pathlib import Path

from arm64_probe.backends.base import HostBackend
from arm64_probe.backends.io import (
    HostFilesystem,
    HostRuntime,
    LocalHostRuntime,
    PathHostFilesystem,
)
from arm64_probe.errors import ExitCode, ProbeError


def backend_id_for_host(system: str, machine: str) -> str:
    normalized_system = system.lower()
    normalized_machine = machine.lower()
    if normalized_machine not in {"arm64", "aarch64"}:
        raise ProbeError(
            ExitCode.HOST_INSPECTION,
            "host-inspection",
            f"unsupported host architecture: {machine}",
        )
    if normalized_system == "linux":
        return "linux-arm64"
    if normalized_system == "darwin":
        return "darwin-arm64"
    raise ProbeError(
        ExitCode.HOST_INSPECTION,
        "host-inspection",
        f"unsupported host operating system: {system}",
    )


def select_backend(
    *,
    system: str | None = None,
    machine: str | None = None,
    filesystem: HostFilesystem | None = None,
    runtime: HostRuntime | None = None,
) -> HostBackend:
    selected_system = system or platform.system()
    selected_machine = machine or platform.machine()
    backend_id = backend_id_for_host(selected_system, selected_machine)
    selected_runtime = runtime or LocalHostRuntime()
    if backend_id == "linux-arm64":
        from arm64_probe.backends.linux_arm64.backend import LinuxArm64Backend

        selected_filesystem = filesystem or PathHostFilesystem(Path("/"))
        return LinuxArm64Backend(selected_filesystem, selected_runtime)

    from arm64_probe.backends.darwin_arm64.backend import DarwinArm64Backend

    return DarwinArm64Backend(selected_runtime, selected_system, selected_machine)
