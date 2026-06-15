from typing import Protocol

from arm64_probe.environment.models import (
    CapabilityObservation,
    ControllerRequest,
    ControllerState,
)


class MutationController(Protocol):
    id: str
    capability_id: str

    def inspect(self) -> ControllerState: ...

    def validate_request(self, request: ControllerRequest) -> None: ...

    def apply(self, request: ControllerRequest) -> None: ...

    def verify(self, request: ControllerRequest) -> ControllerState: ...

    def restore(self, before: ControllerState) -> None: ...

    def verify_restored(self, before: ControllerState) -> ControllerState: ...


class HostBackend(Protocol):
    id: str

    def inspect(self) -> tuple[CapabilityObservation, ...]: ...

    def controllers(self) -> tuple[MutationController, ...]: ...
