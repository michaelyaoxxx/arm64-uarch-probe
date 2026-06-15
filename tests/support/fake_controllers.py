"""Reusable fake controllers and host backends for transaction tests."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol

from arm64_probe.environment.models import (
    CapabilityObservation,
    ControllerRequest,
    ControllerState,
)


@dataclass
class FakeController:
    controller_id: str
    capability_id: str
    inspect_status: str = "available"
    inspect_values: tuple[tuple[str, object], ...] = ()
    before_values: tuple[tuple[str, object], ...] = ()
    applied_values: tuple[tuple[str, object], ...] = ()
    request_handler: Callable[[ControllerRequest], None] | None = None
    apply_handler: Callable[[ControllerRequest], None] | None = None
    verify_handler: Callable[[ControllerRequest], ControllerState] | None = None
    restore_handler: Callable[[ControllerState], None] | None = None
    events: list[tuple[str, str]] = field(default_factory=list)
    raise_on_validate: Exception | None = None
    raise_on_apply: Exception | None = None
    raise_on_verify: Exception | None = None
    raise_on_restore: Exception | None = None
    raise_on_verify_restored: Exception | None = None

    @property
    def id(self) -> str:
        return self.controller_id
    inspect_values: tuple[tuple[str, object], ...] = ()
    before_values: tuple[tuple[str, object], ...] = ()
    applied_values: tuple[tuple[str, object], ...] = ()
    request_handler: Callable[[ControllerRequest], None] | None = None
    apply_handler: Callable[[ControllerRequest], None] | None = None
    verify_handler: Callable[[ControllerRequest], ControllerState] | None = None
    restore_handler: Callable[[ControllerState], None] | None = None
    events: list[tuple[str, str]] = field(default_factory=list)
    raise_on_validate: Exception | None = None
    raise_on_apply: Exception | None = None
    raise_on_verify: Exception | None = None
    raise_on_restore: Exception | None = None
    raise_on_verify_restored: Exception | None = None

    def record(self, label: str) -> None:
        self.events.append((label, self.controller_id))

    def inspect(self) -> ControllerState:
        return ControllerState(
            self.controller_id,
            self.inspect_status,
            tuple(sorted(self.inspect_values, key=lambda item: item[0])),
            (),
        )

    def validate_request(self, request: ControllerRequest) -> None:
        self.record("validate")
        if self.raise_on_validate is not None:
            raise self.raise_on_validate
        if self.request_handler is not None:
            self.request_handler(request)

    def apply(self, request: ControllerRequest) -> None:
        self.record("apply")
        if self.raise_on_apply is not None:
            raise self.raise_on_apply
        if self.apply_handler is not None:
            self.apply_handler(request)

    def verify(self, request: ControllerRequest) -> ControllerState:
        self.record("verify")
        if self.raise_on_verify is not None:
            raise self.raise_on_verify
        if self.verify_handler is not None:
            return self.verify_handler(request)
        return ControllerState(
            self.controller_id,
            "available",
            tuple(sorted(self.applied_values, key=lambda item: item[0])),
            (),
        )

    def restore(self, before: ControllerState) -> None:
        self.record("restore")
        if self.raise_on_restore is not None:
            raise self.raise_on_restore
        if self.restore_handler is not None:
            self.restore_handler(before)

    def verify_restored(self, before: ControllerState) -> ControllerState:
        self.record("verify-restored")
        if self.raise_on_verify_restored is not None:
            raise self.raise_on_verify_restored
        return ControllerState(
            self.controller_id,
            "available",
            tuple(sorted(self.before_values, key=lambda item: item[0])),
            (),
        )


class FakeBackend:
    def __init__(self, controllers: Iterable[FakeController], observations: tuple[CapabilityObservation, ...] = ()):
        self._controllers = tuple(controllers)
        self._observations = tuple(sorted(observations, key=lambda item: item.capability_id))

    @property
    def id(self) -> str:
        return "fake-backend"

    def inspect(self) -> tuple[CapabilityObservation, ...]:
        return self._observations

    def controllers(self) -> tuple[FakeController, ...]:
        return self._controllers


class SignalInjector(Protocol):
    def send(self, signum: int) -> None: ...


class NoopSignalInjector:
    def send(self, signum: int) -> None:  # pragma: no cover - never called
        return None


__all__ = [
    "FakeBackend",
    "FakeController",
    "NoopSignalInjector",
    "SignalInjector",
]
