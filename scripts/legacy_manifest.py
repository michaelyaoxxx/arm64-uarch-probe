#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("legacy/manifest.json")
CANONICAL_MANIFEST = ROOT / DEFAULT_MANIFEST
LEGACY_PATHS = ("runner/run_pmu*.sh", "data/**/*.txt")
MANIFEST_KEYS = {"source_commit", "files"}
HEX_DIGITS = frozenset("0123456789abcdef")


class ManifestError(Exception):
    pass


def digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                sha256.update(chunk)
    except OSError as error:
        raise ManifestError(f"cannot read legacy file: {path}") from error
    return sha256.hexdigest()


def resolve_manifest(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT / path


def is_canonical_manifest(path: Path) -> bool:
    return path.resolve(strict=False) == CANONICAL_MANIFEST.resolve(strict=False)


def tracked_legacy_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *LEGACY_PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ManifestError("unable to list tracked legacy files")
    return sorted(line for line in result.stdout.splitlines() if line)


def resolve_commit(source_commit: str) -> str:
    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{source_commit}^{{commit}}",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ManifestError(
            f"invalid source_commit: {source_commit!r} does not resolve to a commit"
        )
    return result.stdout.strip()


def require_ancestor(source_commit: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 1:
        raise ManifestError("source_commit is not an ancestor of HEAD")
    if result.returncode != 0:
        raise ManifestError("unable to validate source_commit ancestry")


def is_normalized_repo_relative(raw_path: str) -> bool:
    path = PurePosixPath(raw_path)
    return (
        bool(raw_path)
        and not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == raw_path
    )


def load_manifest(manifest_path: Path) -> dict:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestError(f"invalid manifest: cannot read {manifest_path}") from error
    except json.JSONDecodeError as error:
        raise ManifestError(
            f"invalid manifest: invalid JSON at line {error.lineno}"
        ) from error

    if not isinstance(payload, dict):
        raise ManifestError("invalid manifest: top level must be an object")
    if set(payload) != MANIFEST_KEYS:
        raise ManifestError("invalid manifest: expected exactly source_commit and files")

    source_commit = payload["source_commit"]
    files = payload["files"]
    if not isinstance(source_commit, str) or not source_commit:
        raise ManifestError("invalid manifest: source_commit must be a non-empty string")
    if not isinstance(files, dict):
        raise ManifestError("invalid manifest: files must be an object")

    for raw_path, expected in files.items():
        if not is_normalized_repo_relative(raw_path):
            raise ManifestError(
                f"invalid manifest: path must be normalized repo-relative: {raw_path!r}"
            )
        if (
            not isinstance(expected, str)
            or len(expected) != 64
            or not set(expected) <= HEX_DIGITS
        ):
            raise ManifestError(
                f"invalid manifest: digest must be lowercase SHA-256: {raw_path}"
            )
    return payload


def summarize_paths(paths: list[str]) -> str:
    shown = paths[:3]
    summary = ", ".join(shown)
    if len(paths) > len(shown):
        summary += f" (+{len(paths) - len(shown)} more)"
    return summary


def require_complete_inventory(files: dict, tracked: list[str]) -> None:
    manifest_paths = set(files)
    tracked_paths = set(tracked)
    missing = sorted(tracked_paths - manifest_paths)
    extra = sorted(manifest_paths - tracked_paths)
    failures = []
    if missing:
        failures.append(f"missing entries: {summarize_paths(missing)}")
    if extra:
        failures.append(f"extra entries: {summarize_paths(extra)}")
    if failures:
        raise ManifestError(f"inventory mismatch: {'; '.join(failures)}")


def require_safe_custom_scope(files: dict, tracked: list[str]) -> None:
    if not files:
        raise ManifestError("invalid manifest: custom manifest must contain files")
    untracked = sorted(set(files) - set(tracked))
    if untracked:
        raise ManifestError(
            "invalid manifest: custom paths must be tracked legacy files: "
            f"{summarize_paths(untracked)}"
        )


def write_manifest(manifest_path: Path, source_commit: str) -> None:
    resolved_commit = resolve_commit(source_commit)
    files = {
        raw_path: digest(ROOT / raw_path)
        for raw_path in tracked_legacy_paths()
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        manifest_path.write_text(
            json.dumps(
                {"source_commit": resolved_commit, "files": files},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise ManifestError(f"cannot write manifest: {manifest_path}") from error
    print(f"wrote {manifest_path} ({len(files)} files)")


def verify_manifest(manifest_path: Path, allow_custom_manifest: bool) -> None:
    canonical = is_canonical_manifest(manifest_path)
    if not canonical and not allow_custom_manifest:
        raise ManifestError("custom manifest requires --allow-custom-manifest")

    payload = load_manifest(manifest_path)
    files = payload["files"]
    tracked = tracked_legacy_paths()
    if canonical:
        require_complete_inventory(files, tracked)
        source_commit = resolve_commit(payload["source_commit"])
        require_ancestor(source_commit)
    else:
        require_safe_custom_scope(files, tracked)

    failures = []
    for raw_path, expected in files.items():
        path = ROOT / raw_path
        if not path.is_file():
            failures.append(f"missing file: {raw_path}")
        elif digest(path) != expected:
            failures.append(f"digest mismatch: {raw_path}")
    if failures:
        raise ManifestError("\n".join(failures))

    qualifier = "" if canonical else "custom "
    print(f"{qualifier}legacy manifest verified ({len(files)} files)")


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    write = subcommands.add_parser("write")
    write.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    write.add_argument("--source-commit", required=True)

    verify = subcommands.add_parser("verify")
    verify.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    verify.add_argument(
        "--allow-custom-manifest",
        action="store_true",
        help="verify an external manifest limited to tracked legacy paths",
    )

    args = parser.parse_args()
    manifest_path = resolve_manifest(args.manifest)
    try:
        if args.command == "write":
            write_manifest(manifest_path, args.source_commit)
        else:
            verify_manifest(manifest_path, args.allow_custom_manifest)
    except ManifestError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
