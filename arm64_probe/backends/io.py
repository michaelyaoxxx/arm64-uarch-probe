import os
import subprocess
from pathlib import Path, PurePosixPath
from typing import Protocol


class HostFilesystem(Protocol):
    def exists(self, path: str) -> bool: ...

    def read_text(self, path: str) -> str: ...

    def write_text(self, path: str, value: str) -> None: ...

    def glob(self, pattern: str) -> tuple[str, ...]: ...

    def is_writable(self, path: str) -> bool: ...


class CommandExecutor(Protocol):
    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]: ...


class HostRuntime(Protocol):
    def load_average(self) -> tuple[float, float, float]: ...


class PathHostFilesystem:
    def __init__(self, root: Path):
        self.root = root.resolve()

    @staticmethod
    def _relative(path: str) -> Path:
        virtual = PurePosixPath(path)
        if not virtual.is_absolute() or ".." in virtual.parts:
            raise ValueError(f"invalid virtual host path: {path}")
        return Path(*virtual.parts[1:])

    def _ensure_within_root(self, path: Path) -> None:
        if not path.resolve(strict=False).is_relative_to(self.root):
            raise ValueError(f"virtual host path escapes fixture root: {path}")

    def _path(self, path: str) -> Path:
        result = self.root / self._relative(path)
        self._ensure_within_root(result)
        return result

    def exists(self, path: str) -> bool:
        return self._path(path).exists()

    def read_text(self, path: str) -> str:
        return self._path(path).read_text()

    def write_text(self, path: str, value: str) -> None:
        target = self._path(path)
        if target.is_symlink():
            raise ValueError(f"refusing to write symlink: {path}")
        if not target.exists():
            raise FileNotFoundError(path)
        if not target.is_file():
            raise ValueError(f"refusing to write non-file: {path}")
        target.write_text(value)

    def glob(self, pattern: str) -> tuple[str, ...]:
        relative = self._relative(pattern)
        results: list[str] = []
        for path in self.root.glob(relative.as_posix()):
            self._ensure_within_root(path)
            results.append(f"/{path.relative_to(self.root).as_posix()}")
        return tuple(sorted(results))

    def is_writable(self, path: str) -> bool:
        target = self._path(path)
        return target.exists() and not target.is_symlink() and os.access(target, os.W_OK)


class LocalCommandExecutor:
    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
        )


class LocalHostRuntime:
    def load_average(self) -> tuple[float, float, float]:
        return os.getloadavg()
