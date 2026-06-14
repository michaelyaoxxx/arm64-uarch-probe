import json
from pathlib import Path
from typing import Any

from arm64_probe.errors import ExitCode, ProbeError


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ProbeError(
            ExitCode.CONFIG,
            "configuration",
            f"cannot load {path}: {error}",
        ) from error
    if not isinstance(value, dict):
        raise ProbeError(
            ExitCode.CONFIG,
            "configuration",
            f"{path} must contain a JSON object root",
        )
    return value


def dump_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
