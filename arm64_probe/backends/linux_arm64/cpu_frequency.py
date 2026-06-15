import re
from dataclasses import dataclass

from arm64_probe.backends.io import HostFilesystem
from arm64_probe.backends.linux_arm64.inspector import parse_cpu_list
from arm64_probe.domain.models import JsonScalar
from arm64_probe.environment.models import ControllerRequest, ControllerState
from arm64_probe.errors import ExitCode, ProbeError


POLICY_GLOB = "/sys/devices/system/cpu/cpufreq/policy*"
APPROVED_REQUEST_KEYS = {"governor", "min-khz", "max-khz"}


@dataclass(frozen=True)
class _Policy:
    id: str
    base: str
    related_cpus: tuple[int, ...]
    governor: str
    available_governors: tuple[str, ...]
    minimum: int
    maximum: int


def _category(code: ExitCode) -> str:
    if code == ExitCode.MUTATION_AUTHORIZATION:
        return "mutation-authorization"
    if code == ExitCode.ENVIRONMENT_RESTORE:
        return "environment-restore"
    return "environment-apply"


def _error(
    code: ExitCode,
    message: str,
    context: tuple[tuple[str, str], ...] = (),
) -> ProbeError:
    return ProbeError(code, _category(code), message, context)


class CpuFrequencyController:
    id = "linux.cpufreq"
    capability_id = "linux.cpufreq"

    def __init__(self, filesystem: HostFilesystem):
        self.filesystem = filesystem

    def inspect(self) -> ControllerState:
        try:
            paths = self.filesystem.glob(POLICY_GLOB)
        except (OSError, ValueError) as error:
            status = "permission-denied" if isinstance(error, PermissionError) else "unavailable"
            return ControllerState(self.id, status, (), (f"{POLICY_GLOB}:{status}",))
        policies: list[_Policy] = []
        evidence: list[str] = []
        errors: list[Exception] = []
        for path in paths:
            try:
                policy = self._read_policy(path)
                policies.append(policy)
                evidence.append(
                    f"{path}=governor:{policy.governor},"
                    f"min-khz:{policy.minimum},max-khz:{policy.maximum}"
                )
            except (OSError, ValueError) as error:
                errors.append(error)
                evidence.append(f"{path}:unavailable")
        if policies:
            status = "degraded" if errors else "available"
        elif errors and all(isinstance(error, PermissionError) for error in errors):
            status = "permission-denied"
        else:
            status = "unavailable"
        values: list[tuple[str, JsonScalar]] = []
        for policy in policies:
            prefix = policy.id
            values.extend(
                (
                    (f"{prefix}.available-governors", ",".join(policy.available_governors)),
                    (f"{prefix}.governor", policy.governor),
                    (f"{prefix}.max-khz", policy.maximum),
                    (f"{prefix}.min-khz", policy.minimum),
                    (
                        f"{prefix}.related-cpus",
                        ",".join(str(cpu) for cpu in policy.related_cpus),
                    ),
                )
            )
        return ControllerState(
            self.id,
            status,
            tuple(sorted(values)),
            tuple(sorted(evidence)),
        )

    def validate_request(self, request: ControllerRequest) -> None:
        requested = self._request_values(request, ExitCode.ENVIRONMENT_APPLY)
        state = self._available_state(ExitCode.ENVIRONMENT_APPLY)
        values = dict(state.values)
        for policy_id in self._policy_ids(state):
            if "governor" in requested:
                available = str(values[f"{policy_id}.available-governors"]).split(",")
                if requested["governor"] not in available:
                    raise _error(
                        ExitCode.ENVIRONMENT_APPLY,
                        f"governor is unavailable for {policy_id}",
                    )
            current_minimum = int(values[f"{policy_id}.min-khz"])
            current_maximum = int(values[f"{policy_id}.max-khz"])
            target_minimum = int(requested.get("min-khz", current_minimum))
            target_maximum = int(requested.get("max-khz", current_maximum))
            if target_minimum > target_maximum:
                raise _error(
                    ExitCode.ENVIRONMENT_APPLY,
                    f"requested CPU frequency interval is invalid for {policy_id}",
                )
            for key in requested:
                path = self._request_path(policy_id, key)
                if not self.filesystem.is_writable(path):
                    raise _error(
                        ExitCode.MUTATION_AUTHORIZATION,
                        f"CPU frequency interface is not writable for {policy_id}",
                        (("path", path),),
                    )

    def apply(self, request: ControllerRequest) -> None:
        self.validate_request(request)
        before = self._available_state(ExitCode.ENVIRONMENT_APPLY)
        requested = self._request_values(request, ExitCode.ENVIRONMENT_APPLY)
        self._apply_values(before, requested, ExitCode.ENVIRONMENT_APPLY, governor_first=True)

    def verify(self, request: ControllerRequest) -> ControllerState:
        requested = self._request_values(request, ExitCode.ENVIRONMENT_APPLY)
        state = self._available_state(ExitCode.ENVIRONMENT_APPLY)
        values = dict(state.values)
        for policy_id in self._policy_ids(state):
            for key, expected in requested.items():
                if values[f"{policy_id}.{key}"] != expected:
                    raise _error(
                        ExitCode.ENVIRONMENT_APPLY,
                        f"CPU frequency verification failed for {policy_id}.{key}",
                    )
        return state

    def restore(self, before: ControllerState) -> None:
        self._validate_before(before)
        current = self._available_state(ExitCode.ENVIRONMENT_RESTORE)
        before_values = dict(before.values)
        current_values = dict(current.values)
        if self._policy_ids(before) != self._policy_ids(current):
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "CPU frequency policy set changed before restoration",
            )
        for policy_id in self._policy_ids(before):
            paths = (
                self._request_path(policy_id, "min-khz"),
                self._request_path(policy_id, "max-khz"),
                self._request_path(policy_id, "governor"),
            )
            if any(not self.filesystem.is_writable(path) for path in paths):
                raise _error(
                    ExitCode.ENVIRONMENT_RESTORE,
                    f"CPU frequency interface is not writable for {policy_id}",
                )
            target = {
                "governor": before_values[f"{policy_id}.governor"],
                "min-khz": before_values[f"{policy_id}.min-khz"],
                "max-khz": before_values[f"{policy_id}.max-khz"],
            }
            self._write_bounds(
                policy_id,
                int(current_values[f"{policy_id}.min-khz"]),
                target,
                ExitCode.ENVIRONMENT_RESTORE,
            )
            self._write(
                self._request_path(policy_id, "governor"),
                target["governor"],
                ExitCode.ENVIRONMENT_RESTORE,
            )

    def verify_restored(self, before: ControllerState) -> ControllerState:
        self._validate_before(before)
        after = self._available_state(ExitCode.ENVIRONMENT_RESTORE)
        if after.values != before.values:
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "CPU frequency restoration verification failed",
            )
        return after

    def _read_policy(self, base: str) -> _Policy:
        policy_id = base.rsplit("/", 1)[-1]
        if re.fullmatch(r"policy[0-9]+", policy_id) is None:
            raise ValueError(f"invalid CPU frequency policy identity: {policy_id}")
        related = parse_cpu_list(self.filesystem.read_text(f"{base}/related_cpus"))
        governor = self.filesystem.read_text(f"{base}/scaling_governor").strip()
        available = tuple(
            sorted(
                self.filesystem.read_text(
                    f"{base}/scaling_available_governors"
                ).split()
            )
        )
        minimum = int(self.filesystem.read_text(f"{base}/scaling_min_freq").strip())
        maximum = int(self.filesystem.read_text(f"{base}/scaling_max_freq").strip())
        if (
            not governor
            or not available
            or len(available) != len(set(available))
            or governor not in available
            or minimum <= 0
            or maximum <= 0
            or minimum > maximum
        ):
            raise ValueError(f"invalid CPU frequency policy state: {policy_id}")
        return _Policy(
            policy_id,
            base,
            related,
            governor,
            available,
            minimum,
            maximum,
        )

    def _request_values(
        self,
        request: ControllerRequest,
        code: ExitCode,
    ) -> dict[str, JsonScalar]:
        if request.controller_id != self.id or not request.values:
            raise _error(code, "invalid CPU frequency controller request")
        requested = dict(request.values)
        unknown = set(requested) - APPROVED_REQUEST_KEYS
        if unknown:
            raise _error(code, f"unknown CPU frequency request value: {min(unknown)}")
        governor = requested.get("governor")
        if governor is not None and (not isinstance(governor, str) or not governor):
            raise _error(code, "governor must be a nonempty string")
        for key in ("min-khz", "max-khz"):
            value = requested.get(key)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
            ):
                raise _error(code, f"{key} must be a positive integer")
        if (
            "min-khz" in requested
            and "max-khz" in requested
            and int(requested["min-khz"]) > int(requested["max-khz"])
        ):
            raise _error(code, "min-khz must not exceed max-khz")
        return requested

    def _available_state(self, code: ExitCode) -> ControllerState:
        state = self.inspect()
        if state.status != "available":
            raise _error(
                code,
                "CPU frequency interface is not fully inspectable",
                (("status", state.status),),
            )
        return state

    def _validate_before(self, before: ControllerState) -> None:
        if before.controller_id != self.id or before.status != "available":
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "invalid CPU frequency before state",
            )

    @staticmethod
    def _policy_ids(state: ControllerState) -> tuple[str, ...]:
        return tuple(
            key.removesuffix(".governor")
            for key, _ in state.values
            if key.endswith(".governor")
        )

    @staticmethod
    def _request_path(policy_id: str, key: str) -> str:
        names = {
            "governor": "scaling_governor",
            "min-khz": "scaling_min_freq",
            "max-khz": "scaling_max_freq",
        }
        return f"/sys/devices/system/cpu/cpufreq/{policy_id}/{names[key]}"

    def _apply_values(
        self,
        before: ControllerState,
        requested: dict[str, JsonScalar],
        code: ExitCode,
        governor_first: bool,
    ) -> None:
        values = dict(before.values)
        for policy_id in self._policy_ids(before):
            if governor_first and "governor" in requested:
                self._write(
                    self._request_path(policy_id, "governor"),
                    requested["governor"],
                    code,
                )
            self._write_bounds(
                policy_id,
                int(values[f"{policy_id}.min-khz"]),
                requested,
                code,
            )

    def _write_bounds(
        self,
        policy_id: str,
        current_minimum: int,
        requested: dict[str, JsonScalar],
        code: ExitCode,
    ) -> None:
        target_maximum = requested.get("max-khz")
        order = (
            ("min-khz", "max-khz")
            if target_maximum is not None and int(target_maximum) < current_minimum
            else ("max-khz", "min-khz")
        )
        for key in order:
            if key in requested:
                self._write(self._request_path(policy_id, key), requested[key], code)

    def _write(self, path: str, value: JsonScalar, code: ExitCode) -> None:
        try:
            self.filesystem.write_text(path, f"{value}\n")
        except (OSError, ValueError) as error:
            raise _error(
                code,
                "CPU frequency write failed",
                (("path", path), ("error-type", type(error).__name__)),
            ) from error
