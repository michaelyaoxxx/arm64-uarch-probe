import re

from arm64_probe.backends.io import HostFilesystem
from arm64_probe.domain.models import JsonScalar
from arm64_probe.environment.models import ControllerRequest, ControllerState
from arm64_probe.errors import ExitCode, ProbeError


GLOBAL_GLOB = "/sys/kernel/mm/hugepages/hugepages-*/nr_hugepages"
GLOBAL_PATTERN = re.compile(
    r"^/sys/kernel/mm/hugepages/hugepages-([1-9][0-9]*)kB/nr_hugepages$"
)


def _category(code: ExitCode) -> str:
    if code == ExitCode.MUTATION_AUTHORIZATION:
        return "mutation-authorization"
    if code == ExitCode.ENVIRONMENT_RESTORE:
        return "environment-restore"
    return "environment-apply"


def _error(code: ExitCode, message: str, path: str | None = None) -> ProbeError:
    context = (("path", path),) if path is not None else ()
    return ProbeError(code, _category(code), message, context)


class HugepageController:
    id = "linux.hugepage"
    capability_id = "linux.hugepage"

    def __init__(self, filesystem: HostFilesystem):
        self.filesystem = filesystem

    def inspect(self) -> ControllerState:
        try:
            global_paths = self.filesystem.glob(GLOBAL_GLOB)
        except (OSError, ValueError) as error:
            status = "permission-denied" if isinstance(error, PermissionError) else "unavailable"
            return ControllerState(self.id, status, (), (f"{GLOBAL_GLOB}:{status}",))
        values: list[tuple[str, JsonScalar]] = []
        evidence: list[str] = []
        errors: list[Exception] = []
        for path in global_paths:
            match = GLOBAL_PATTERN.fullmatch(path)
            try:
                if match is None:
                    raise ValueError("invalid hugepage pool identity")
                size_kb = int(match.group(1))
                count = int(self.filesystem.read_text(path).strip())
                if count < 0:
                    raise ValueError("negative hugepage count")
                values.append((f"{size_kb}.count", count))
                evidence.append(f"{path}={count}")
                node_glob = (
                    "/sys/devices/system/node/node*/hugepages/"
                    f"hugepages-{size_kb}kB/nr_hugepages"
                )
                for node_path in self.filesystem.glob(node_glob):
                    node_count = int(self.filesystem.read_text(node_path).strip())
                    if node_count < 0:
                        raise ValueError("negative NUMA hugepage count")
                    evidence.append(f"{node_path}={node_count}")
            except (OSError, ValueError) as error:
                errors.append(error)
                evidence.append(f"{path}:unavailable")
        if values:
            status = "degraded" if errors else "available"
        elif errors and all(isinstance(error, PermissionError) for error in errors):
            status = "permission-denied"
        else:
            status = "unavailable"
        return ControllerState(
            self.id,
            status,
            tuple(sorted(values)),
            tuple(sorted(evidence)),
        )

    def validate_request(self, request: ControllerRequest) -> None:
        requested = self._request_values(request, ExitCode.ENVIRONMENT_APPLY)
        state = self._available_state(ExitCode.ENVIRONMENT_APPLY)
        size_kb = int(requested["size-kb"])
        if f"{size_kb}.count" not in dict(state.values):
            raise _error(
                ExitCode.ENVIRONMENT_APPLY,
                f"hugepage size is unavailable: {size_kb} kB",
            )
        path = self._global_path(size_kb)
        if not self.filesystem.is_writable(path):
            raise _error(
                ExitCode.MUTATION_AUTHORIZATION,
                "global hugepage pool is not writable",
                path,
            )

    def apply(self, request: ControllerRequest) -> None:
        self.validate_request(request)
        requested = self._request_values(request, ExitCode.ENVIRONMENT_APPLY)
        self._write(
            self._global_path(int(requested["size-kb"])),
            int(requested["count"]),
            ExitCode.ENVIRONMENT_APPLY,
        )

    def verify(self, request: ControllerRequest) -> ControllerState:
        requested = self._request_values(request, ExitCode.ENVIRONMENT_APPLY)
        state = self._available_state(ExitCode.ENVIRONMENT_APPLY)
        key = f"{requested['size-kb']}.count"
        if dict(state.values).get(key) != requested["count"]:
            raise _error(
                ExitCode.ENVIRONMENT_APPLY,
                "global hugepage allocation verification failed",
            )
        return state

    def restore(self, before: ControllerState) -> None:
        before_values = self._before_values(before)
        current = self._available_state(ExitCode.ENVIRONMENT_RESTORE)
        if set(before_values) != set(dict(current.values)):
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "global hugepage pool set changed before restoration",
            )
        paths = tuple(self._global_path(self._size_from_key(key)) for key in before_values)
        if any(not self.filesystem.is_writable(path) for path in paths):
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "global hugepage pool is not writable during restoration",
            )
        for key, count in sorted(before_values.items()):
            self._write(
                self._global_path(self._size_from_key(key)),
                count,
                ExitCode.ENVIRONMENT_RESTORE,
            )

    def verify_restored(self, before: ControllerState) -> ControllerState:
        before_values = self._before_values(before)
        after = self._available_state(ExitCode.ENVIRONMENT_RESTORE)
        if dict(after.values) != before_values:
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "global hugepage restoration verification failed",
            )
        return after

    def _request_values(
        self,
        request: ControllerRequest,
        code: ExitCode,
    ) -> dict[str, JsonScalar]:
        if request.controller_id != self.id or {key for key, _ in request.values} != {
            "count",
            "size-kb",
        }:
            raise _error(code, "invalid hugepage controller request")
        requested = dict(request.values)
        count = requested["count"]
        size_kb = requested["size-kb"]
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or not isinstance(size_kb, int)
            or isinstance(size_kb, bool)
            or size_kb <= 0
        ):
            raise _error(code, "hugepage count and size-kb are invalid")
        return requested

    def _available_state(self, code: ExitCode) -> ControllerState:
        state = self.inspect()
        if state.status != "available":
            raise _error(code, "global hugepage pools are not fully inspectable")
        return state

    def _before_values(self, before: ControllerState) -> dict[str, int]:
        if before.controller_id != self.id or before.status != "available":
            raise _error(ExitCode.ENVIRONMENT_RESTORE, "invalid hugepage before state")
        result: dict[str, int] = {}
        for key, value in before.values:
            self._size_from_key(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise _error(ExitCode.ENVIRONMENT_RESTORE, "invalid hugepage before state")
            result[key] = value
        if not result:
            raise _error(ExitCode.ENVIRONMENT_RESTORE, "empty hugepage before state")
        return result

    @staticmethod
    def _size_from_key(key: str) -> int:
        match = re.fullmatch(r"([1-9][0-9]*)\.count", key)
        if match is None:
            raise _error(ExitCode.ENVIRONMENT_RESTORE, "invalid hugepage before state")
        return int(match.group(1))

    @staticmethod
    def _global_path(size_kb: int) -> str:
        return f"/sys/kernel/mm/hugepages/hugepages-{size_kb}kB/nr_hugepages"

    def _write(self, path: str, count: int, code: ExitCode) -> None:
        try:
            self.filesystem.write_text(path, f"{count}\n")
        except (OSError, ValueError) as error:
            raise _error(code, "global hugepage write failed", path) from error
