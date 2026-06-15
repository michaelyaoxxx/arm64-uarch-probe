from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from types import TracebackType

from arm64_probe.backends.io import PathHostFilesystem


class HostFixture:
    def __init__(self):
        self._temporary = TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.filesystem = PathHostFilesystem(self.root)

    def __enter__(self) -> "HostFixture":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._temporary.cleanup()

    def path(self, virtual_path: str) -> Path:
        virtual = PurePosixPath(virtual_path)
        if not virtual.is_absolute() or ".." in virtual.parts:
            raise ValueError(f"invalid virtual host path: {virtual_path}")
        return self.root.joinpath(*virtual.parts[1:])

    def write(self, virtual_path: str, value: str) -> Path:
        path = self.path(virtual_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        return path

    def read(self, virtual_path: str) -> str:
        return self.path(virtual_path).read_text()

    def symlink(self, virtual_path: str, target: Path) -> Path:
        path = self.path(virtual_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
        return path
