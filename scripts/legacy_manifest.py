#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("legacy/manifest.json")
LEGACY_PATHS = ("runner/run_pmu*.sh", "data/**/*.txt")


def digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def resolve_manifest(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT / path


def tracked_legacy_paths() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", *LEGACY_PATHS],
        cwd=ROOT,
        text=True,
    )
    return [ROOT / line for line in output.splitlines() if line]


def write_manifest(manifest_path: Path, source_commit: str) -> None:
    files = {
        str(path.relative_to(ROOT)): digest(path)
        for path in sorted(tracked_legacy_paths())
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"source_commit": source_commit, "files": files},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {manifest_path} ({len(files)} files)")


def verify_manifest(manifest_path: Path) -> int:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = payload["files"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"invalid legacy manifest: {error}", file=sys.stderr)
        return 1

    failures = []
    for raw_path, expected in files.items():
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            failures.append(f"missing file: {raw_path}")
        elif digest(path) != expected:
            failures.append(f"digest mismatch: {raw_path}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1

    print(f"legacy manifest verified ({len(files)} files)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    write = subcommands.add_parser("write")
    write.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    write.add_argument("--source-commit", required=True)

    verify = subcommands.add_parser("verify")
    verify.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)

    args = parser.parse_args()
    manifest_path = resolve_manifest(args.manifest)
    if args.command == "write":
        write_manifest(manifest_path, args.source_commit)
        return 0
    return verify_manifest(manifest_path)


if __name__ == "__main__":
    raise SystemExit(main())
