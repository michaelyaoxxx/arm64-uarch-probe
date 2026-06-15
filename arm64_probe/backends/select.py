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
