"""Candidate baseline promotion (Python API only, no CLI command)."""
import shutil
from pathlib import Path

from arm64_probe.serialization import json_io, model_json
from arm64_probe.analysis.models import BaselineManifest


class BaselinePromoter:
    """Promotes analysis artifacts to a reviewed baseline evidence package."""

    def __init__(self, baseline_root: Path):
        self._root = Path(baseline_root)
        self._root.mkdir(parents=True, exist_ok=True)

    def validate_candidate(self, *, run_ids, analysis_id, report_id,
                           figure_ids, repository_commit, dirty_tree):
        errors = []
        if dirty_tree:
            errors.append("dirty_tree must be False for baseline promotion")
        if not run_ids:
            errors.append("at least one source run_id is required")
        if not analysis_id:
            errors.append("analysis_id is required")
        return tuple(errors)

    def promote(self, manifest, artifacts=(), approved_by=None):
        dest = self._root / manifest.baseline_id
        dest.mkdir(parents=True, exist_ok=True)

        # Set approved_by if provided
        if approved_by is not None:
            object.__setattr__(manifest, "approved_by", approved_by)

        # Write manifest
        manifest_path = dest / "baseline-manifest.json"
        manifest_path.write_text(
            json_io.dump_json(model_json.to_data(manifest)),
            encoding="utf-8",
        )

        # Copy artifacts
        for art in artifacts:
            art_path = Path(art)
            if art_path.is_file():
                shutil.copy2(art_path, dest / art_path.name)

        return dest
