import re

from arm64_probe.backends.io import HostFilesystem, HostRuntime
from arm64_probe.domain.models import JsonScalar
from arm64_probe.environment.models import CapabilityObservation


CPU_ONLINE = "/sys/devices/system/cpu/online"
TOPOLOGY_CLUSTER_GLOB = "/sys/devices/system/cpu/cpu*/topology/cluster_id"
CACHE_LEVEL_GLOB = "/sys/devices/system/cpu/cpu*/cache/index*/level"
PERF_EVENT_PARANOID = "/proc/sys/kernel/perf_event_paranoid"
ARMV8_PMU_TYPE = "/sys/bus/event_source/devices/armv8_pmuv3/type"
CPUFREQ_POLICY_GLOB = "/sys/devices/system/cpu/cpufreq/policy*"
HUGEPAGE_POOL_GLOB = "/sys/kernel/mm/hugepages/hugepages-*"
THP_ENABLED = "/sys/kernel/mm/transparent_hugepage/enabled"
MAX_EVIDENCE = 32


def parse_cpu_list(value: str) -> tuple[int, ...]:
    text = value.strip()
    if not text:
        raise ValueError("empty CPU list")
    result: list[int] = []
    for item in text.split(","):
        if re.fullmatch(r"[0-9]+", item):
            result.append(int(item))
            continue
        match = re.fullmatch(r"([0-9]+)-([0-9]+)", item)
        if match is None:
            raise ValueError(f"invalid CPU-list item: {item}")
        start, end = (int(part) for part in match.groups())
        if end < start:
            raise ValueError(f"descending CPU-list range: {item}")
        result.extend(range(start, end + 1))
    if result != sorted(set(result)):
        raise ValueError("CPU list must be sorted and unique")
    return tuple(result)


def parse_bracketed_policy(value: str) -> tuple[str, tuple[str, ...]]:
    choices = value.strip().split()
    selected = tuple(item[1:-1] for item in choices if item.startswith("[") and item.endswith("]"))
    if len(selected) != 1 or not selected[0]:
        raise ValueError("policy must contain exactly one bracketed selection")
    normalized = tuple(item.strip("[]") for item in choices)
    if any(not item for item in normalized) or len(normalized) != len(set(normalized)):
        raise ValueError("policy choices must be nonempty and unique")
    return selected[0], normalized


def _observation(
    capability_id: str,
    status: str,
    values: tuple[tuple[str, JsonScalar], ...] = (),
    evidence: tuple[str, ...] = (),
    hint: str | None = None,
    permits_formal_measurement: bool | None = None,
) -> CapabilityObservation:
    if permits_formal_measurement is None:
        permits_formal_measurement = status == "available"
    return CapabilityObservation(
        capability_id,
        status,
        tuple(sorted(values)),
        tuple(sorted(evidence))[:MAX_EVIDENCE],
        hint,
        permits_formal_measurement,
    )


def _error_observation(
    capability_id: str,
    path: str,
    error: Exception,
) -> CapabilityObservation:
    if isinstance(error, PermissionError):
        status = "permission-denied"
        hint = f"grant read permission for {path}"
    else:
        status = "unavailable"
        hint = f"provide a readable, valid {path} interface"
    return _observation(
        capability_id,
        status,
        evidence=(f"{path}:{status}",),
        hint=hint,
        permits_formal_measurement=False,
    )


def _partial_status(valid_count: int, errors: list[Exception]) -> str:
    if valid_count:
        return "degraded" if errors else "available"
    if errors and all(isinstance(error, PermissionError) for error in errors):
        return "permission-denied"
    return "unavailable"


class LinuxArm64Inspector:
    def __init__(self, filesystem: HostFilesystem, runtime: HostRuntime):
        self.filesystem = filesystem
        self.runtime = runtime

    def inspect(self) -> tuple[CapabilityObservation, ...]:
        observations = (
            self._cache(),
            self._cpu_online(),
            self._kernel_interfaces(),
            self._load(),
            self._pmu(),
            self._topology(),
        )
        return tuple(sorted(observations, key=lambda item: item.capability_id))

    def _cpu_online(self) -> CapabilityObservation:
        try:
            cpus = parse_cpu_list(self.filesystem.read_text(CPU_ONLINE))
        except (OSError, ValueError) as error:
            return _error_observation("host.cpu-online", CPU_ONLINE, error)
        normalized = ",".join(str(cpu) for cpu in cpus)
        return _observation(
            "host.cpu-online",
            "available",
            (("count", len(cpus)), ("online-cpus", normalized)),
            (f"{CPU_ONLINE}={normalized}",),
        )

    def _topology(self) -> CapabilityObservation:
        try:
            paths = self.filesystem.glob(TOPOLOGY_CLUSTER_GLOB)
        except (OSError, ValueError) as error:
            return _error_observation("host.topology", TOPOLOGY_CLUSTER_GLOB, error)
        clusters: list[int] = []
        evidence: list[str] = []
        errors: list[Exception] = []
        for path in paths:
            try:
                cluster = int(self.filesystem.read_text(path).strip())
                if cluster < 0:
                    raise ValueError("negative cluster ID")
                clusters.append(cluster)
                evidence.append(f"{path}={cluster}")
            except (OSError, ValueError) as error:
                errors.append(error)
                evidence.append(f"{path}:unavailable")
        status = _partial_status(len(clusters), errors)
        return _observation(
            "host.topology",
            status,
            (("cluster-count", len(set(clusters))), ("cpu-count", len(clusters))),
            tuple(evidence),
            None if status == "available" else "inspect CPU topology interfaces",
        )

    def _cache(self) -> CapabilityObservation:
        try:
            level_paths = self.filesystem.glob(CACHE_LEVEL_GLOB)
        except (OSError, ValueError) as error:
            return _error_observation("host.cache", CACHE_LEVEL_GLOB, error)
        levels: list[int] = []
        evidence: list[str] = []
        errors: list[Exception] = []
        for level_path in level_paths:
            base = level_path.rsplit("/", 1)[0]
            try:
                level = int(self.filesystem.read_text(level_path).strip())
                cache_type = self.filesystem.read_text(f"{base}/type").strip()
                size = self.filesystem.read_text(f"{base}/size").strip()
                if level < 1 or not cache_type or re.fullmatch(r"[1-9][0-9]*[KMG]", size) is None:
                    raise ValueError("invalid cache description")
                levels.append(level)
                evidence.append(f"{base}=level:{level},type:{cache_type},size:{size}")
            except (OSError, ValueError) as error:
                errors.append(error)
                evidence.append(f"{base}:unavailable")
        status = _partial_status(len(levels), errors)
        return _observation(
            "host.cache",
            status,
            (
                ("entry-count", len(levels)),
                ("levels", ",".join(str(level) for level in sorted(set(levels)))),
            ),
            tuple(evidence),
            None if status == "available" else "inspect CPU cache interfaces",
        )

    def _pmu(self) -> CapabilityObservation:
        values: list[tuple[str, JsonScalar]] = []
        evidence: list[str] = []
        errors: list[Exception] = []
        for key, path in (
            ("perf-event-paranoid", PERF_EVENT_PARANOID),
            ("pmu-type", ARMV8_PMU_TYPE),
        ):
            try:
                value = int(self.filesystem.read_text(path).strip())
                values.append((key, value))
                evidence.append(f"{path}={value}")
            except (OSError, ValueError) as error:
                errors.append(error)
                evidence.append(f"{path}:unavailable")
        status = _partial_status(len(values), errors)
        return _observation(
            "host.pmu",
            status,
            tuple(values),
            tuple(evidence),
            None if status == "available" else "inspect PMU and perf permission interfaces",
        )

    def _kernel_interfaces(self) -> CapabilityObservation:
        checks = (
            ("cpu-frequency-policy", CPUFREQ_POLICY_GLOB, True),
            ("explicit-hugepage-pools", HUGEPAGE_POOL_GLOB, True),
            ("online-cpus", CPU_ONLINE, False),
            ("pmu", ARMV8_PMU_TYPE, False),
            ("transparent-hugepage", THP_ENABLED, False),
        )
        values: list[tuple[str, JsonScalar]] = []
        evidence: list[str] = []
        errors: list[Exception] = []
        for key, path, is_glob in checks:
            try:
                available = bool(self.filesystem.glob(path)) if is_glob else self.filesystem.exists(path)
            except (OSError, ValueError) as error:
                errors.append(error)
                available = False
            values.append((key, available))
            evidence.append(f"{path}={'available' if available else 'unavailable'}")
        available_count = sum(bool(value) for _, value in values)
        status = "available" if available_count == len(values) and not errors else "degraded"
        return _observation(
            "host.kernel-interfaces",
            status,
            tuple(values),
            tuple(evidence),
            None if status == "available" else "some optional Linux interfaces are unavailable",
            permits_formal_measurement=status == "available",
        )

    def _load(self) -> CapabilityObservation:
        try:
            one, five, fifteen = self.runtime.load_average()
        except OSError as error:
            return _error_observation("host.load", "os.getloadavg", error)
        return _observation(
            "host.load",
            "available",
            (("load-15m", fifteen), ("load-1m", one), ("load-5m", five)),
            (f"os.getloadavg={one},{five},{fifteen}",),
        )
