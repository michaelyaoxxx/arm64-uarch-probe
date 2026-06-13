#!/usr/bin/env python3
import argparse
import fnmatch
import functools
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
ROOT_RESOLVED = ROOT.resolve()
DEFAULT_MANIFEST = Path("legacy/manifest.json")
CANONICAL_MANIFEST = ROOT / DEFAULT_MANIFEST
LEGACY_PATHS = ("runner/run_pmu*.sh", "data/**/*.txt")
MANIFEST_KEYS = {"source_commit", "files"}
HEX_DIGITS = frozenset("0123456789abcdef")
OID_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
REGULAR_GIT_MODES = {"100644", "100755"}


class ManifestError(Exception):
    pass


class DuplicateKeyError(ValueError):
    pass


def digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                sha256.update(chunk)
    except OSError as error:
        raise ManifestError(f"cannot read file: {path}") from error
    return sha256.hexdigest()


def resolve_manifest(path: Path) -> Path:
    if path.is_absolute():
        return path
    return ROOT / path


def is_canonical_manifest(path: Path) -> bool:
    return path.resolve(strict=False) == CANONICAL_MANIFEST.resolve(strict=False)


@functools.lru_cache(maxsize=1)
def repository_git_dir() -> Path:
    dot_git = ROOT / ".git"
    try:
        mode = dot_git.lstat().st_mode
        if stat.S_ISDIR(mode):
            git_dir = dot_git.resolve(strict=True)
        elif stat.S_ISREG(mode):
            pointer = dot_git.read_text(encoding="utf-8").strip()
            prefix = "gitdir: "
            if not pointer.startswith(prefix):
                raise ManifestError("invalid checkout .git file")
            git_dir = Path(pointer[len(prefix) :])
            if not git_dir.is_absolute():
                git_dir = ROOT / git_dir
            git_dir = git_dir.resolve(strict=True)
        else:
            raise ManifestError("checkout .git entry is not a file or directory")
    except (OSError, UnicodeDecodeError) as error:
        raise ManifestError("unable to resolve checkout Git directory") from error
    if not git_dir.is_dir():
        raise ManifestError("checkout Git directory is not a directory")
    return git_dir


def sanitized_git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def run_git(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [
                "git",
                f"--git-dir={repository_git_dir()}",
                f"--work-tree={ROOT}",
                *args,
            ],
            cwd=ROOT,
            env=sanitized_git_environment(),
            capture_output=True,
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise ManifestError("unable to run Git plumbing") from error


def tracked_legacy_paths() -> list[str]:
    result = run_git("ls-files", "-z", *LEGACY_PATHS)
    if result.returncode != 0:
        raise ManifestError("unable to list tracked legacy files")
    try:
        return sorted(
            raw_path.decode("utf-8")
            for raw_path in result.stdout.split(b"\0")
            if raw_path
        )
    except UnicodeDecodeError as error:
        raise ManifestError("tracked legacy path is not valid UTF-8") from error


def resolve_commit(source_commit: str) -> str:
    result = run_git(
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{source_commit}^{{commit}}",
    )
    if result.returncode != 0:
        raise ManifestError(
            f"invalid source_commit: {source_commit!r} does not resolve to a commit"
        )
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ManifestError("unable to parse resolved source_commit") from error


def require_full_commit_oid(source_commit: str) -> str:
    resolved_commit = resolve_commit(source_commit.lower())
    if source_commit.lower() != resolved_commit.lower():
        raise ManifestError("source_commit must be a full resolved commit OID")
    return resolved_commit


def require_ancestor(source_commit: str) -> None:
    result = run_git("merge-base", "--is-ancestor", source_commit, "HEAD")
    if result.returncode == 1:
        raise ManifestError("source_commit is not an ancestor of HEAD")
    if result.returncode != 0:
        raise ManifestError("unable to validate source_commit ancestry")


def source_tree_entries(source_commit: str) -> dict[str, tuple[str, str, str]]:
    result = run_git("ls-tree", "-r", "-z", "--full-tree", source_commit)
    if result.returncode != 0:
        raise ManifestError("unable to read source_commit tree")

    entries = {}
    try:
        for record in result.stdout.split(b"\0"):
            if not record:
                continue
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_oid = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8")
            entries[path] = (
                mode.decode("ascii"),
                object_type.decode("ascii"),
                object_oid.decode("ascii"),
            )
    except (UnicodeDecodeError, ValueError) as error:
        raise ManifestError("unable to parse source_commit tree") from error
    return entries


def is_legacy_path(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in LEGACY_PATHS)


def git_blob_digest(object_oid: str, path: str) -> str:
    result = run_git("cat-file", "blob", object_oid)
    if result.returncode != 0:
        raise ManifestError(f"unable to read source tree blob: {path}")
    return digest_bytes(result.stdout)


def regular_working_path(raw_path: str) -> Path:
    parts = PurePosixPath(raw_path).parts
    path = ROOT
    for index, part in enumerate(parts):
        path /= part
        try:
            mode = path.lstat().st_mode
        except OSError as error:
            raise ManifestError(f"missing file: {raw_path}") from error
        if index < len(parts) - 1:
            if stat.S_ISLNK(mode):
                raise ManifestError(f"working tree path contains symlink: {raw_path}")
            if not stat.S_ISDIR(mode):
                raise ManifestError(
                    f"working tree path component is not a directory: {raw_path}"
                )
        elif not stat.S_ISREG(mode):
            raise ManifestError(f"working tree entry is not a regular file: {raw_path}")
    try:
        path.resolve(strict=True).relative_to(ROOT_RESOLVED)
    except (OSError, ValueError) as error:
        raise ManifestError(f"working tree path escapes repository: {raw_path}") from error
    return path


def is_normalized_repo_relative(raw_path: str) -> bool:
    path = PurePosixPath(raw_path)
    return (
        bool(raw_path)
        and not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == raw_path
    )


def is_full_commit_oid(source_commit: str) -> bool:
    return len(source_commit) == 40 and set(source_commit) <= OID_HEX_DIGITS


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def load_manifest(manifest_path: Path, canonical: bool) -> dict:
    try:
        raw_manifest = manifest_path.read_text(encoding="utf-8")
        payload = json.loads(raw_manifest, object_pairs_hook=reject_duplicate_keys)
    except OSError as error:
        raise ManifestError(f"invalid manifest: cannot read {manifest_path}") from error
    except UnicodeDecodeError as error:
        raise ManifestError("invalid manifest: content is not valid UTF-8") from error
    except DuplicateKeyError as error:
        raise ManifestError(f"invalid manifest: duplicate key: {error}") from error
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
    if canonical and not is_full_commit_oid(source_commit):
        raise ManifestError("invalid manifest: source_commit must be a 40-hex OID")
    if not isinstance(files, dict):
        raise ManifestError("invalid manifest: files must be an object")
    if not canonical and not files:
        raise ManifestError("invalid manifest: external manifest must contain files")

    for raw_path, expected in files.items():
        if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path:
            raise ManifestError("invalid manifest: file paths must be non-empty strings")
        if canonical and not is_normalized_repo_relative(raw_path):
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


def require_complete_inventory(files: dict, expected_paths: list[str]) -> None:
    manifest_paths = set(files)
    expected = set(expected_paths)
    missing = sorted(expected - manifest_paths)
    extra = sorted(manifest_paths - expected)
    failures = []
    if missing:
        failures.append(f"missing entries: {summarize_paths(missing)}")
    if extra:
        failures.append(f"extra entries: {summarize_paths(extra)}")
    if failures:
        raise ManifestError(f"inventory mismatch: {'; '.join(failures)}")


def source_files_for_commit(
    source_commit: str, tracked_paths: list[str]
) -> dict[str, str]:
    entries = source_tree_entries(source_commit)
    source_legacy_paths = sorted(path for path in entries if is_legacy_path(path))
    require_complete_inventory(
        {path: None for path in tracked_paths},
        source_legacy_paths,
    )

    files = {}
    for raw_path in tracked_paths:
        mode, object_type, object_oid = entries[raw_path]
        if mode not in REGULAR_GIT_MODES or object_type != "blob":
            raise ManifestError(
                f"source tree entry is not a regular file: {raw_path}"
            )
        files[raw_path] = git_blob_digest(object_oid, raw_path)
    return files


def require_current_files_match(source_files: dict[str, str]) -> None:
    for raw_path, source_digest in source_files.items():
        path = regular_working_path(raw_path)
        if digest(path) != source_digest:
            raise ManifestError(
                f"current file digest differs from source_commit: {raw_path}"
            )


def write_manifest(manifest_path: Path, source_commit: str) -> None:
    resolved_commit = resolve_commit(source_commit)
    require_ancestor(resolved_commit)
    files = source_files_for_commit(resolved_commit, tracked_legacy_paths())
    require_current_files_match(files)
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
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


def verify_canonical_manifest(payload: dict) -> None:
    files = payload["files"]
    tracked_paths = tracked_legacy_paths()
    require_complete_inventory(files, tracked_paths)
    source_commit = require_full_commit_oid(payload["source_commit"])
    require_ancestor(source_commit)
    source_files = source_files_for_commit(source_commit, tracked_paths)
    for raw_path, expected in files.items():
        if source_files[raw_path] != expected:
            raise ManifestError(f"source tree digest mismatch: {raw_path}")
    require_current_files_match(source_files)


def verify_external_manifest(files: dict) -> None:
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
        raise ManifestError("\n".join(failures))


def verify_manifest(manifest_path: Path) -> None:
    canonical = is_canonical_manifest(manifest_path)
    payload = load_manifest(manifest_path, canonical)
    if canonical:
        verify_canonical_manifest(payload)
        print(f"legacy manifest verified ({len(payload['files'])} files)")
    else:
        verify_external_manifest(payload["files"])
        print(f"external manifest digests verified ({len(payload['files'])} files)")


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    write = subcommands.add_parser("write")
    write.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    write.add_argument("--source-commit", required=True)

    verify = subcommands.add_parser(
        "verify",
        description=(
            "The default manifest is the repository integrity contract; "
            "an external manifest is an ad hoc digest-check input."
        ),
    )
    verify.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="manifest to verify; external manifests may contain absolute file paths",
    )

    args = parser.parse_args()
    manifest_path = resolve_manifest(args.manifest)
    try:
        if args.command == "write":
            write_manifest(manifest_path, args.source_commit)
        else:
            verify_manifest(manifest_path)
    except ManifestError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
