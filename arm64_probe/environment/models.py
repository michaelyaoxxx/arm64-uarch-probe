from dataclasses import dataclass

from arm64_probe.domain.models import JsonScalar
from arm64_probe.environment.constants import JOURNAL_STATES, OBSERVATION_STATUSES


def _validate_mapping(
    values: tuple[tuple[str, JsonScalar], ...],
    label: str,
) -> None:
    keys = tuple(key for key, _ in values)
    if keys != tuple(sorted(set(keys))):
        raise ValueError(f"{label} must have sorted unique keys")


def _validate_status(status: str, label: str) -> None:
    if status not in OBSERVATION_STATUSES:
        raise ValueError(f"unsupported {label} status: {status}")


def _ids_are_unique(values: tuple[object, ...], attribute: str) -> bool:
    identities = tuple(getattr(value, attribute) for value in values)
    return len(identities) == len(set(identities))


@dataclass(frozen=True)
class CapabilityObservation:
    capability_id: str
    status: str
    values: tuple[tuple[str, JsonScalar], ...]
    evidence: tuple[str, ...]
    hint: str | None
    permits_formal_measurement: bool

    def __post_init__(self) -> None:
        _validate_status(self.status, "observation")
        _validate_mapping(self.values, "observation values")


@dataclass(frozen=True)
class ControllerRequest:
    controller_id: str
    values: tuple[tuple[str, JsonScalar], ...]

    def __post_init__(self) -> None:
        _validate_mapping(self.values, "controller request values")


@dataclass(frozen=True)
class ControllerState:
    controller_id: str
    status: str
    values: tuple[tuple[str, JsonScalar], ...]
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_status(self.status, "controller")
        _validate_mapping(self.values, "controller state values")


@dataclass(frozen=True)
class JournalFailure:
    stage: str
    category: str
    message: str


@dataclass(frozen=True)
class EnvironmentJournal:
    schema_version: int
    transaction_id: str
    repository_id: str
    backend_id: str
    platform_id: str
    state: str
    created_at: str
    updated_at: str
    requested: tuple[ControllerRequest, ...]
    before: tuple[ControllerState, ...]
    applied: tuple[str, ...]
    active_controller: str | None
    effective: tuple[ControllerState, ...]
    after: tuple[ControllerState, ...]
    restoration_status: str
    failures: tuple[JournalFailure, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(
                f"unsupported journal schema version: {self.schema_version}"
            )
        if self.state not in JOURNAL_STATES:
            raise ValueError(f"unsupported journal state: {self.state}")
        for values, label in (
            (self.requested, "requested controllers"),
            (self.before, "before controller states"),
            (self.effective, "effective controller states"),
            (self.after, "after controller states"),
        ):
            if not _ids_are_unique(values, "controller_id"):
                raise ValueError(f"{label} must have unique controller IDs")
        if len(self.applied) != len(set(self.applied)):
            raise ValueError("applied controllers must be unique")
        requested_ids = {request.controller_id for request in self.requested}
        before_ids = {state.controller_id for state in self.before}
        restorable_ids = requested_ids.intersection(before_ids)
        if not set(self.applied).issubset(restorable_ids):
            raise ValueError("applied controllers must be requested and captured")
        if self.active_controller is not None:
            if self.active_controller not in restorable_ids:
                raise ValueError("active controller must be requested and captured")
            if self.active_controller in self.applied:
                raise ValueError("active controller must not already be applied")


@dataclass(frozen=True)
class DoctorReport:
    backend_id: str
    platform_id: str | None
    observations: tuple[CapabilityObservation, ...]
    journals: tuple[EnvironmentJournal, ...]

    def __post_init__(self) -> None:
        if not _ids_are_unique(self.observations, "capability_id"):
            raise ValueError("observations must have unique capability IDs")
        if not _ids_are_unique(self.journals, "transaction_id"):
            raise ValueError("journals must have unique transaction IDs")
