"""Atomic persistence for analysis artifacts."""
import os
import uuid
from pathlib import Path

from arm64_probe.serialization import json_io, model_json
from arm64_probe.analysis.models import AnalysisSummary

MAX_ANALYSIS_BYTES = 2 * 1024 * 1024  # 2 MiB


class AnalysisStore:
    def __init__(self, analysis_dir: Path):
        self._dir = Path(analysis_dir).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_analysis_id(analysis_id: str) -> None:
        if not analysis_id:
            raise ValueError("analysis_id must not be empty")
        if "/" in analysis_id or "\\" in analysis_id:
            raise ValueError(
                f"analysis_id must not contain path separators: {analysis_id!r}"
            )
        if ".." in analysis_id:
            raise ValueError(
                f"analysis_id must not contain '..': {analysis_id!r}"
            )
        if "\0" in analysis_id:
            raise ValueError("analysis_id must not contain null bytes")

    def _resolve_path(self, analysis_id: str) -> Path:
        self._validate_analysis_id(analysis_id)
        path = (self._dir / f"{analysis_id}.json").resolve()
        dir_prefix = str(self._dir)
        if not dir_prefix.endswith("/"):
            dir_prefix += "/"
        if not str(path).startswith(dir_prefix):
            raise ValueError(
                f"analysis_id escapes base directory: {analysis_id!r}"
            )
        return path

    def write_analysis(self, summary: AnalysisSummary) -> Path:
        data = model_json.to_data(summary)
        analysis_id = summary.analysis_id
        self._validate_analysis_id(analysis_id)
        dest = self._dir / f"{analysis_id}.json"
        # Defense-in-depth: verify resolved path stays under self._dir
        resolved_dest = dest.resolve()
        dir_prefix = str(self._dir)
        if not dir_prefix.endswith("/"):
            dir_prefix += "/"
        if not str(resolved_dest).startswith(dir_prefix):
            raise ValueError(
                f"analysis_id escapes base directory: {analysis_id!r}"
            )
        tmp = self._dir / f".{analysis_id}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(tmp, "w") as f:
                f.write(json_io.dump_json(data))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, dest)
            self._fsync_dir()
        except BaseException:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            raise
        return dest

    def read_analysis(self, analysis_id: str) -> AnalysisSummary:
        path = self._resolve_path(analysis_id)
        return self._read_path(path)

    def _read_path(self, path: Path) -> AnalysisSummary:
        if not path.is_file():
            raise FileNotFoundError(f"analysis artifact not found: {path}")
        if path.stat().st_size > MAX_ANALYSIS_BYTES:
            raise ValueError(
                f"analysis artifact too large: {path.stat().st_size} bytes"
            )
        data = json_io.load_json(path)
        if data.get("schema_version") != 1:
            raise ValueError(
                f"unsupported schema_version: {data.get('schema_version')}"
            )
        return model_json.dict_to_analysis_summary(data)

    def list_analyses(self) -> tuple[str, ...]:
        return tuple(sorted(
            p.stem for p in self._dir.glob("*.json")
            if not p.name.startswith(".")
        ))

    def _fsync_dir(self):
        if not self._dir.is_dir():
            raise FileNotFoundError(
                f"analysis directory does not exist: {self._dir}"
            )
        fd = os.open(str(self._dir), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
