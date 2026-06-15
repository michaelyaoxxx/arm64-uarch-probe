"""Main-thread signal conversion for environment transactions.

Only the main thread can install Python signal handlers; this module records
the previous handler so a transient conversion does not leak across the
transaction boundary.
"""

from __future__ import annotations

import signal
import threading
from collections.abc import Iterable
from types import TracebackType


class TransactionInterrupted(Exception):
    """Raised inside a transaction when a converted signal is delivered."""

    def __init__(self, signum: int) -> None:
        super().__init__(f"transaction interrupted by signal {signum}")
        self.signum = signum


class CommonSignalScope:
    """Convert common signals into a private exception inside a transaction.

    Only the main thread accepts handlers. On other threads, the context
    manager refuses to install handlers and the caller must guarantee the
    thread is not the main thread.
    """

    DEFAULT_SIGNALS: tuple[int, ...] = (signal.SIGINT, signal.SIGTERM)

    def __init__(
        self,
        signals: Iterable[int] | None = None,
        exc_factory: type[TransactionInterrupted] | None = None,
    ) -> None:
        self._signals: tuple[int, ...] = tuple(signals) if signals is not None else self.DEFAULT_SIGNALS
        self._exc_factory = exc_factory or TransactionInterrupted
        self._previous: dict[int, signal._HANDLER] = {}
        self._active = False

    def __enter__(self) -> "CommonSignalScope":
        if not threading.current_thread() is threading.main_thread():
            raise RuntimeError("CommonSignalScope may only be used on the main thread")
        if self._active:
            raise RuntimeError("CommonSignalScope is already active")
        self._active = True
        for signum in self._signals:
            self._previous[signum] = signal.signal(signum, self._handle)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._active:
            return
        try:
            for signum, previous in self._previous.items():
                signal.signal(signum, previous)
        finally:
            self._previous.clear()
            self._active = False

    def _handle(self, signum: int, _frame: object) -> None:
        # Use raise later in the Python frame; raise here would surface only
        # from C-level dispatchers. Defer to the next Python instruction.
        signal.signal(signum, self._raise_handler)
        self._raise_handler(signum, _frame)

    def _raise_handler(self, signum: int, _frame: object) -> None:
        raise self._exc_factory(signum)

    def raise_for_test(self, signum: int) -> None:
        """Test-only entry point to raise the configured exception."""

        raise self._exc_factory(signum)


__all__ = ["CommonSignalScope", "TransactionInterrupted"]
