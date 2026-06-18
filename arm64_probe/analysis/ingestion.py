"""RunResult ingestion and legacy import protocol."""
from pathlib import Path
from typing import Protocol, runtime_checkable

from arm64_probe.analysis.models import ImportedRecord
from arm64_probe.execution.result_store import ResultStore


@runtime_checkable
class LegacyImporter(Protocol):
    """Protocol for importing historical text logs into ImportedRecord."""

    source_format: str
    parser_version: str

    def can_handle(self, path: Path) -> bool:
        """Return True if this importer can handle the given file."""
        ...

    def import_log(self, path: Path) -> ImportedRecord:
        """Parse the file and return an ImportedRecord."""
        ...


class ResultIngester:
    """Loads and validates RunResult files via ResultStore."""

    def __init__(self, store: ResultStore) -> None:
        self._store = store

    def ingest(self, paths: tuple[Path, ...]) -> tuple:
        """Load RunResult files, rejecting duplicate run_ids.

        Args:
            paths: Tuple of paths to RunResult JSON files.

        Returns:
            Tuple of loaded RunResult objects.

        Raises:
            ValueError: If any two paths resolve to the same run_id.
        """
        results = []
        seen_ids: set[str] = set()
        for p in paths:
            result = self._store.read(p)
            if result.run_id in seen_ids:
                raise ValueError(f"duplicate run_id: {result.run_id}")
            seen_ids.add(result.run_id)
            results.append(result)
        return tuple(results)
