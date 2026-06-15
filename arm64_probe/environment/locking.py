import fcntl
import json
import os
import socket
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.errors import ExitCode, ProbeError


def _error(code: ExitCode, category: str, message: str) -> ProbeError:
    return ProbeError(code, category, message)


class MutationLock:
    def __init__(
        self,
        root: Path,
        *,
        required_owner_uid: int = 0,
        backend_id: str = "unknown",
        repository_id: str = REPOSITORY_ID,
        clock: Callable[[], datetime] | None = None,
    ):
        self.root = root
        self.path = root / "mutation.lock"
        self.required_owner_uid = required_owner_uid
        self.backend_id = backend_id
        self.repository_id = repository_id
        self.clock = clock or (lambda: datetime.now(UTC))
        self._fd: int | None = None
        self.metadata: dict[str, object] = {}

    @property
    def held(self) -> bool:
        return self._fd is not None

    def __enter__(self) -> "MutationLock":
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        if self.held:
            raise _error(
                ExitCode.ENVIRONMENT_BUSY,
                "environment-busy",
                "mutation lock is already held by this object",
            )
        self._ensure_root()
        existed = os.path.lexists(self.path)
        if existed:
            self._validate_file()
        try:
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags, 0o644)
            if not existed:
                os.fchmod(fd, 0o644)
            self._validate_open_file(fd)
        except OSError as error:
            raise _error(
                ExitCode.MUTATION_AUTHORIZATION,
                "mutation-authorization",
                "cannot open host mutation lock",
            ) from error
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(fd)
            raise _error(
                ExitCode.ENVIRONMENT_BUSY,
                "environment-busy",
                "host mutation lock is already held",
            ) from error
        self._fd = fd
        try:
            self.metadata = self._metadata()
            encoded = (
                json.dumps(self.metadata, sort_keys=True, ensure_ascii=True) + "\n"
            ).encode("utf-8")
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            offset = 0
            while offset < len(encoded):
                offset += os.write(fd, encoded[offset:])
            os.fsync(fd)
        except OSError as error:
            self.release()
            raise _error(
                ExitCode.MUTATION_AUTHORIZATION,
                "mutation-authorization",
                "cannot write host mutation lock metadata",
            ) from error

    def release(self) -> None:
        if self._fd is None:
            return
        fd = self._fd
        self._fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _ensure_root(self) -> None:
        if os.geteuid() != self.required_owner_uid:
            raise _error(
                ExitCode.MUTATION_AUTHORIZATION,
                "mutation-authorization",
                "caller does not match required mutation-lock owner",
            )
        if os.path.lexists(self.root):
            self._validate_root()
            return
        try:
            os.mkdir(self.root, 0o755)
            os.chmod(self.root, 0o755)
        except OSError as error:
            raise _error(
                ExitCode.MUTATION_AUTHORIZATION,
                "mutation-authorization",
                "cannot create host mutation state root",
            ) from error
        self._validate_root()

    def _validate_root(self) -> None:
        details = self.root.lstat()
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or stat.S_IMODE(details.st_mode) != 0o755
            or details.st_uid != self.required_owner_uid
        ):
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                "unsafe host mutation state root",
            )

    def _validate_file(self) -> None:
        details = self.path.lstat()
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or stat.S_IMODE(details.st_mode) != 0o644
            or details.st_uid != self.required_owner_uid
        ):
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                "unsafe host mutation lock file",
            )

    def _validate_open_file(self, fd: int) -> None:
        details = os.fstat(fd)
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_IMODE(details.st_mode) != 0o644
            or details.st_uid != self.required_owner_uid
        ):
            os.close(fd)
            raise _error(
                ExitCode.ENVIRONMENT_RESTORE,
                "environment-restore",
                "unsafe opened host mutation lock file",
            )

    def _metadata(self) -> dict[str, object]:
        acquired = self.clock().astimezone(UTC).isoformat(timespec="seconds")
        return {
            "acquired_at": acquired,
            "backend_id": self.backend_id[:64],
            "hostname": socket.gethostname()[:64],
            "pid": os.getpid(),
            "repository_id": self.repository_id[:128],
        }
