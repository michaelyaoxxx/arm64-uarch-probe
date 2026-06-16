"""Recording fake for the CommandExecutor protocol (arm64_probe/backends/io.py)."""
import subprocess
from collections.abc import Sequence


class ExecutorRecorder:
    """Records argv tuples and returns scripted CompletedProcess responses.

    Implements the CommandExecutor Protocol from arm64_probe/backends/io.py:19.
    """

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []
        self._responses: list[subprocess.CompletedProcess[str]] = []
        self._default_returncode = 0
        self._default_stdout = ""
        self._default_stderr = ""
        self._timeouts: list[int | None] = []

    def enqueue_response(
        self,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """Add a response to be returned by the next run() call."""
        self._responses.append(
            subprocess.CompletedProcess(
                args=(),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )
        )

    def run(
        self,
        argv: tuple[str, ...],
        timeout: int | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a command (recorded) and return a scripted response."""
        self.calls.append(argv)
        self._timeouts.append(timeout)

        if self._responses:
            return self._responses.pop(0)

        return subprocess.CompletedProcess(
            args=argv,
            returncode=self._default_returncode,
            stdout=self._default_stdout,
            stderr=self._default_stderr,
        )

    @property
    def last_timeout(self) -> int | None:
        if self._timeouts:
            return self._timeouts[-1]
        return None
