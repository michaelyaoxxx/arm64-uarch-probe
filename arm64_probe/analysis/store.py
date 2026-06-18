"""Atomic persistence for analysis artifacts."""
import os
import uuid
from pathlib import Path

from arm64_probe.serialization import json_io, model_json
from arm64_probe.analysis.models import AnalysisSummary

MAX_ANALYSIS_BYTES = 2 * 1024 * 1024  # 2 MiB


class AnalysisStore:
    def __init__(self, analysis_dir: Path):
        self._dir = Path(analysis_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def write_analysis(self, summary: AnalysisSummary) -> Path:
        data = model_json.to_data(summary)
        dest = self._dir / f"{summary.analysis_id}.json"
        tmp = self._dir / f".{summary.analysis_id}.{uuid.uuid4().hex[:8]}.tmp"
        tmp.write_text(json_io.dump_json(data), encoding="utf-8")
        # fsync the temp file
        fd = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, dest)
        self._fsync_dir()
        return dest

    def read_analysis(self, analysis_id: str) -> AnalysisSummary:
        path = self._dir / f"{analysis_id}.json"
        return self._read_path(path)

    def _read_path(self, path: Path) -> AnalysisSummary:
        if not path.is_file():
            raise FileNotFoundError(f"analysis artifact not found: {path}")
        if path.stat().st_size > MAX_ANALYSIS_BYTES:
            raise ValueError(f"analysis artifact too large: {path.stat().st_size} bytes")
        data = json_io.load_json(path)
        if data.get("schema_version") != 1:
            raise ValueError(f"unsupported schema_version: {data.get('schema_version')}")
        return model_json._dict_to_analysis_summary(data)

    def list_analyses(self) -> tuple[str, ...]:
        return tuple(sorted(
            p.stem for p in self._dir.glob("*.json")
            if not p.name.startswith(".")
        ))

    def _fsync_dir(self):
        fd = os.open(str(self._dir), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
