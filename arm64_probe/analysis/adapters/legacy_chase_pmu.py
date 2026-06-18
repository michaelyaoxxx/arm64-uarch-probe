"""Example legacy importer for chase_pmu v2.7.x text logs."""
import re
from pathlib import Path

from arm64_probe.analysis.models import ImportedRecord


class LegacyChasePmuImporter:
    """Imports chase_pmu v2.7.x text output into ImportedRecord."""

    source_format = "chase_pmu_v2.7.x_text"
    parser_version = "1.0"

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".txt":
            return False
        try:
            # Read up to 2048 chars to find the version marker
            head = path.read_text()[:2048]
            return "=== chase_pmu v2.7" in head
        except Exception:
            return False

    def import_log(self, path: Path) -> ImportedRecord:
        text = path.read_text()
        metrics: dict[str, float | int] = {}
        loss_notes: list[str] = []

        lat_match = re.search(
            r">>>\s+latency\s*=\s*([\d.]+)\s*ns/access", text
        )
        elapsed_match = re.search(
            r"elapsed\s*=\s*(\d+)\s*ns", text
        )
        accesses_match = re.search(
            r"accesses?\s*=\s*(\d+)", text
        )

        if lat_match:
            metrics["latency_ns"] = float(lat_match.group(1))
        else:
            loss_notes.append("latency not extractable from log")

        if elapsed_match:
            metrics["elapsed_ns"] = int(elapsed_match.group(1))
        if accesses_match:
            metrics["accesses"] = int(accesses_match.group(1))

        return ImportedRecord(
            source_path=str(path),
            parser_version=self.parser_version,
            format=self.source_format,
            case_id=None,
            platform_id=None,
            metrics=tuple(sorted(metrics.items())),
            loss_notes=tuple(loss_notes),
        )
