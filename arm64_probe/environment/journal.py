import json
import os
import re
import stat
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arm64_probe.domain.models import JsonScalar
from arm64_probe.environment.models import (
    ControllerRequest,
    ControllerState,
    EnvironmentJournal,
    JournalFailure,
)
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.serialization.json_io import dump_json
from arm64_probe.serialization.model_json import to_data


JOURNAL_FIELDS = {
    "schema_version",
    "transaction_id",
    "repository_id",
    "backend_id",
    "platform_id",
    "state",
    "created_at",
    "updated_at",
    "requested",
    "before",
    "applied",
    "active_controller",
    "effective",
    "after",
    "restoration_status",
    "failures",
}
UNFINISHED_STATES = {"created", "applying", "prepared", "restoring", "restore-failed"}
TRANSITIONS = {
    "created": {"applying", "restoring"},
    "applying": {"prepared", "restoring"},
    "prepared": {"restoring"},
    "restoring": {"restored", "restore-failed"},
    "restore-failed": {"restoring"},
    "restored": set(),
}
TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_JOURNAL_BYTES = 1024 * 1024


def _error(message: str, *, authorization: bool = False) -> ProbeError:
    code = ExitCode.MUTATION_AUTHORIZATION if authorization else ExitCode.ENVIRONMENT_RESTORE
    category = "mutation-authorization" if authorization else "environment-restore"
    return ProbeError(code, category, message)


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _exact(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        raise ValueError(f"unknown {label} field: {min(unknown)}")
    if missing:
        raise ValueError(f"missing {label} field: {min(missing)}")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _mapping(value: object, label: str) -> tuple[tuple[str, JsonScalar], ...]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    result: list[tuple[str, JsonScalar]] = []
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be nonempty strings")
        if item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError(f"{label}.{key} must be a JSON scalar")
        result.append((key, item))
    return tuple(sorted(result))


def _request(value: object) -> ControllerRequest:
    item = _exact(value, {"controller_id", "values"}, "controller request")
    return ControllerRequest(
        _string(item["controller_id"], "controller_id"),
        _mapping(item["values"], "controller request values"),
    )


def _state(value: object) -> ControllerState:
    item = _exact(
        value,
        {"controller_id", "status", "values", "evidence"},
        "controller state",
    )
    return ControllerState(
        _string(item["controller_id"], "controller_id"),
        _string(item["status"], "controller status"),
        _mapping(item["values"], "controller state values"),
        _strings(item["evidence"], "controller evidence"),
    )


def _failure(value: object) -> JournalFailure:
    item = _exact(value, {"stage", "category", "message"}, "journal failure")
    return JournalFailure(
        _string(item["stage"], "failure stage"),
        _string(item["category"], "failure category"),
        _string(item["message"], "failure message"),
    )


def _items(value: object, parser: Callable[[object], Any], label: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return tuple(parser(item) for item in value)


def _timestamp(value: str) -> None:
    if len(value) > 32 or not value.endswith("Z"):
        raise ValueError(f"invalid UTC timestamp: {value}")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"invalid UTC timestamp: {value}")


class JournalStore:
    def __init__(
        self,
        root: Path,
        *,
        repository_id: str,
        required_owner_uid: int = 0,
        clock: Callable[[], datetime] | None = None,
        transaction_id_factory: Callable[[], str] | None = None,
    ):
        self.root = root
        self.journals = root / "journals"
        self.repository_id = repository_id
        self.required_owner_uid = required_owner_uid
        self.clock = clock or (lambda: datetime.now(UTC))
        self.transaction_id_factory = transaction_id_factory or (lambda: uuid.uuid4().hex)

    def new(
        self,
        backend_id: str,
        platform_id: str,
        requested: tuple[ControllerRequest, ...],
        before: tuple[ControllerState, ...],
    ) -> EnvironmentJournal:
        timestamp = self._now()
        journal = EnvironmentJournal(
            schema_version=1,
            transaction_id=self.transaction_id_factory(),
            repository_id=self.repository_id,
            backend_id=backend_id,
            platform_id=platform_id,
            state="created",
            created_at=timestamp,
            updated_at=timestamp,
            requested=requested,
            before=before,
            applied=(),
            active_controller=None,
            effective=(),
            after=(),
            restoration_status="not-started",
            failures=(),
        )
        self._validate_journal(journal)
        return journal

    def create(self, journal: EnvironmentJournal) -> Path:
        self._validate_journal(journal)
        if journal.state != "created":
            raise _error("new journal must start in created state")
        self._ensure_layout()
        path = self.journals / f"{journal.transaction_id}.json"
        if os.path.lexists(path):
            raise _error(f"journal already exists: {journal.transaction_id}")
        self._atomic_write(path, journal)
        return path

    def read(self, path: Path) -> EnvironmentJournal:
        managed = self.validate_managed_path(path)
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(managed, flags)
            try:
                chunks: list[bytes] = []
                size = 0
                while True:
                    chunk = os.read(fd, 65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_JOURNAL_BYTES:
                        raise ValueError("journal exceeds size limit")
                    chunks.append(chunk)
            finally:
                os.close(fd)
            payload = json.loads(
                b"".join(chunks).decode("utf-8"),
                object_pairs_hook=_duplicates,
            )
            journal = self._parse(payload)
            self._validate_journal(journal)
            if managed.name != f"{journal.transaction_id}.json":
                raise ValueError("journal path does not match transaction ID")
            return journal
        except ProbeError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise _error(f"cannot read managed journal: {type(error).__name__}") from error

    def update(self, journal: EnvironmentJournal) -> Path:
        self._validate_journal(journal)
        path = self.journals / f"{journal.transaction_id}.json"
        current = self.read(path)
        immutable_fields = (
            "schema_version",
            "transaction_id",
            "repository_id",
            "backend_id",
            "platform_id",
            "created_at",
            "requested",
            "before",
        )
        if any(getattr(current, field) != getattr(journal, field) for field in immutable_fields):
            raise _error("journal update changes immutable transaction fields")
        allowed = TRANSITIONS[current.state]
        if journal.state != current.state and journal.state not in allowed:
            raise _error(f"invalid journal transition: {current.state} -> {journal.state}")
        if current.state == "restored":
            raise _error("restored journal is immutable")
        self._atomic_write(path, journal)
        return path

    def unfinished(self) -> tuple[EnvironmentJournal, ...]:
        if not os.path.lexists(self.root):
            return ()
        self._validate_directory(self.root, 0o755, "state root")
        if not os.path.lexists(self.journals):
            return ()
        self._validate_directory(self.journals, 0o755, "journal directory")
        journals = tuple(
            self.read(path)
            for path in sorted(self.journals.glob("*.json"))
        )
        return tuple(journal for journal in journals if journal.state in UNFINISHED_STATES)

    def validate_managed_path(self, path: Path) -> Path:
        if (
            not path.is_absolute()
            or path.parent != self.journals
            or re.fullmatch(r"[0-9a-f]{32}\.json", path.name) is None
        ):
            raise _error("journal path is outside the managed journal directory")
        if os.path.lexists(self.root):
            self._validate_directory(self.root, 0o755, "state root")
        if os.path.lexists(self.journals):
            self._validate_directory(self.journals, 0o755, "journal directory")
        if os.path.lexists(path):
            self._validate_file(path, 0o644, "journal")
        return path

    def _ensure_layout(self) -> None:
        if os.geteuid() != self.required_owner_uid:
            raise _error(
                "caller does not match required journal owner",
                authorization=True,
            )
        self._ensure_directory(self.root, "state root")
        self._ensure_directory(self.journals, "journal directory")

    def _ensure_directory(self, path: Path, label: str) -> None:
        if os.path.lexists(path):
            self._validate_directory(path, 0o755, label)
            return
        try:
            os.mkdir(path, 0o755)
            os.chmod(path, 0o755)
        except OSError as error:
            raise _error(f"cannot create {label}", authorization=True) from error
        self._validate_directory(path, 0o755, label)

    def _validate_directory(self, path: Path, mode: int, label: str) -> None:
        try:
            details = path.lstat()
        except OSError as error:
            raise _error(f"cannot inspect {label}") from error
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or stat.S_IMODE(details.st_mode) != mode
            or details.st_uid != self.required_owner_uid
        ):
            raise _error(f"unsafe {label}")

    def _validate_file(self, path: Path, mode: int, label: str) -> None:
        try:
            details = path.lstat()
        except OSError as error:
            raise _error(f"cannot inspect {label}") from error
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or stat.S_IMODE(details.st_mode) != mode
            or details.st_uid != self.required_owner_uid
        ):
            raise _error(f"unsafe {label}")

    def _atomic_write(self, path: Path, journal: EnvironmentJournal) -> None:
        self.validate_managed_path(path)
        data = dump_json(to_data(journal)).encode("utf-8")
        temporary = self.journals / f".{journal.transaction_id}.{uuid.uuid4().hex}.tmp"
        fd: int | None = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(temporary, flags, 0o644)
            os.fchmod(fd, 0o644)
            offset = 0
            while offset < len(data):
                offset += os.write(fd, data[offset:])
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(temporary, path)
            directory_fd = os.open(
                self.journals,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            self._validate_file(path, 0o644, "journal")
        except OSError as error:
            raise _error("cannot atomically persist managed journal") from error
        finally:
            if fd is not None:
                os.close(fd)
            if os.path.lexists(temporary):
                temporary.unlink()

    def _validate_journal(self, journal: EnvironmentJournal) -> None:
        try:
            if journal.repository_id != self.repository_id:
                raise ValueError("journal repository identity does not match")
            if TRANSACTION_ID.fullmatch(journal.transaction_id) is None:
                raise ValueError("invalid journal transaction ID")
            _timestamp(journal.created_at)
            _timestamp(journal.updated_at)
        except ValueError as error:
            raise _error(str(error)) from error

    def _now(self) -> str:
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise _error("journal clock must return UTC")
        return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    @staticmethod
    def _parse(value: object) -> EnvironmentJournal:
        item = _exact(value, JOURNAL_FIELDS, "journal")
        active = item["active_controller"]
        if active is not None and not isinstance(active, str):
            raise ValueError("active_controller must be a string or null")
        schema_version = item["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError("schema_version must be an integer")
        return EnvironmentJournal(
            schema_version=schema_version,
            transaction_id=_string(item["transaction_id"], "transaction_id"),
            repository_id=_string(item["repository_id"], "repository_id"),
            backend_id=_string(item["backend_id"], "backend_id"),
            platform_id=_string(item["platform_id"], "platform_id"),
            state=_string(item["state"], "state"),
            created_at=_string(item["created_at"], "created_at"),
            updated_at=_string(item["updated_at"], "updated_at"),
            requested=_items(item["requested"], _request, "requested"),
            before=_items(item["before"], _state, "before"),
            applied=_strings(item["applied"], "applied"),
            active_controller=active,
            effective=_items(item["effective"], _state, "effective"),
            after=_items(item["after"], _state, "after"),
            restoration_status=_string(item["restoration_status"], "restoration_status"),
            failures=_items(item["failures"], _failure, "failures"),
        )
