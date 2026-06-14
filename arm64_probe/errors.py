from dataclasses import dataclass
from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    CONFIG = 3
    CAPABILITY = 4
    PLANNING = 5


@dataclass(frozen=True)
class ProbeError(Exception):
    code: ExitCode
    category: str
    message: str
    context: tuple[tuple[str, str], ...] = ()
    hint: str | None = None
