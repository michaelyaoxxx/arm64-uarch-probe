from arm64_probe.backends.io import HostFilesystem
from arm64_probe.backends.linux_arm64.inspector import parse_bracketed_policy
from arm64_probe.domain.models import JsonScalar
from arm64_probe.environment.models import ControllerRequest, ControllerState
from arm64_probe.errors import ExitCode, ProbeError


THP_PATH = "/sys/kernel/mm/transparent_hugepage/enabled"


def _category(code: ExitCode) -> str:
    if code == ExitCode.MUTATION_AUTHORIZATION:
        return "mutation-authorization"
    if code == ExitCode.ENVIRONMENT_RESTORE:
        return "environment-restore"
    return "environment-apply"


def _error(code: ExitCode, message: str) -> ProbeError:
    return ProbeError(code, _category(code), message)


class TransparentHugepageController:
    id = "linux.transparent-hugepage"
    capability_id = "linux.transparent-hugepage"

    def __init__(self, filesystem: HostFilesystem):
        self.filesystem = filesystem

    def inspect(self) -> ControllerState:
        try:
            selected, choices = parse_bracketed_policy(
                self.filesystem.read_text(THP_PATH)
            )
        except (OSError, ValueError) as error:
            status = "permission-denied" if isinstance(error, PermissionError) else "unavailable"
            return ControllerState(self.id, status, (), (f"{THP_PATH}:{status}",))
        return ControllerState(
            self.id,
            "available",
            (
                ("available-policies", ",".join(choices)),
                ("policy", selected),
            ),
            (f"{THP_PATH}={selected}",),
        )

    def validate_request(self, request: ControllerRequest) -> None:
        requested = self._request_policy(request, ExitCode.ENVIRONMENT_APPLY)
        state = self._available_state(ExitCode.ENVIRONMENT_APPLY)
        available = str(dict(state.values)["available-policies"]).split(",")
        if requested not in available:
            raise _error(
                ExitCode.ENVIRONMENT_APPLY,
                f"transparent hugepage policy is unavailable: {requested}",
            )
        if not self.filesystem.is_writable(THP_PATH):
            raise _error(
                ExitCode.MUTATION_AUTHORIZATION,
                "transparent hugepage policy is not writable",
            )

    def apply(self, request: ControllerRequest) -> None:
        self.validate_request(request)
        self._write(
            self._request_policy(request, ExitCode.ENVIRONMENT_APPLY),
            ExitCode.ENVIRONMENT_APPLY,
        )

    def verify(self, request: ControllerRequest) -> ControllerState:
        expected = self._request_policy(request, ExitCode.ENVIRONMENT_APPLY)
        state = self._available_state(ExitCode.ENVIRONMENT_APPLY)
        if dict(state.values)["policy"] != expected:
            raise _error(
                ExitCode.ENVIRONMENT_APPLY,
                "transparent hugepage policy verification failed",
            )
        return state

    def restore(self, before: ControllerState) -> None:
        policy = self._before_policy(before)
        if not self.filesystem.is_writable(THP_PATH):
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "transparent hugepage policy is not writable during restoration",
            )
        self._write(policy, ExitCode.ENVIRONMENT_RESTORE)

    def verify_restored(self, before: ControllerState) -> ControllerState:
        self._before_policy(before)
        after = self._available_state(ExitCode.ENVIRONMENT_RESTORE)
        if after.values != before.values:
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "transparent hugepage restoration verification failed",
            )
        return after

    def _request_policy(self, request: ControllerRequest, code: ExitCode) -> str:
        if request.controller_id != self.id or tuple(key for key, _ in request.values) != (
            "policy",
        ):
            raise _error(code, "invalid transparent hugepage controller request")
        policy: JsonScalar = request.values[0][1]
        if not isinstance(policy, str) or not policy:
            raise _error(code, "transparent hugepage policy must be a nonempty string")
        return policy

    def _available_state(self, code: ExitCode) -> ControllerState:
        state = self.inspect()
        if state.status != "available":
            raise _error(code, "transparent hugepage policy is not inspectable")
        return state

    def _before_policy(self, before: ControllerState) -> str:
        if before.controller_id != self.id or before.status != "available":
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "invalid transparent hugepage before state",
            )
        values = dict(before.values)
        policy = values.get("policy")
        available = values.get("available-policies")
        if (
            set(values) != {"available-policies", "policy"}
            or not isinstance(policy, str)
            or not isinstance(available, str)
            or policy not in available.split(",")
        ):
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "invalid transparent hugepage before state",
            )
        return policy

    def _write(self, policy: str, code: ExitCode) -> None:
        try:
            self.filesystem.write_text(THP_PATH, f"{policy}\n")
        except (OSError, ValueError) as error:
            raise _error(code, "transparent hugepage policy write failed") from error
