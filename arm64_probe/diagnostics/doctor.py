from typing import Protocol

from arm64_probe.backends.base import HostBackend
from arm64_probe.environment.models import DoctorReport, EnvironmentJournal
from arm64_probe.errors import ExitCode, ProbeError


class JournalReader(Protocol):
    def unfinished(self) -> tuple[EnvironmentJournal, ...]: ...


class EmptyJournalReader:
    def unfinished(self) -> tuple[EnvironmentJournal, ...]:
        return ()


class Doctor:
    def __init__(self, backend: HostBackend, journal_reader: JournalReader):
        self.backend = backend
        self.journal_reader = journal_reader

    def inspect(self, platform_id: str | None) -> DoctorReport:
        try:
            observations = tuple(
                sorted(
                    self.backend.inspect(),
                    key=lambda item: item.capability_id,
                )
            )
            journals = tuple(
                sorted(
                    self.journal_reader.unfinished(),
                    key=lambda item: item.transaction_id,
                )
            )
            return DoctorReport(self.backend.id, platform_id, observations, journals)
        except Exception as error:
            raise ProbeError(
                ExitCode.HOST_INSPECTION,
                "host-inspection",
                f"unable to inspect host with backend {self.backend.id}",
                (
                    ("backend", self.backend.id),
                    ("error-type", type(error).__name__),
                ),
                "inspect backend availability and permissions",
            ) from error
