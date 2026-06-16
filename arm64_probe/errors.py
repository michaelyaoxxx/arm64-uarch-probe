from dataclasses import dataclass
from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    CONFIG = 3
    CAPABILITY = 4
    PLANNING = 5
    HOST_INSPECTION = 10
    MUTATION_AUTHORIZATION = 11
    ENVIRONMENT_APPLY = 12
    ENVIRONMENT_RESTORE = 13
    ENVIRONMENT_BUSY = 14
    PROBE_EXECUTION = 15
    RUN_RESULT = 16


@dataclass(frozen=True)
class ProbeError(Exception):
    code: ExitCode
    category: str
    message: str
    context: tuple[tuple[str, str], ...] = ()
    hint: str | None = None
