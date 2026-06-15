import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from arm64_probe.backends.io import (
    LocalCommandExecutor,
    LocalHostRuntime,
    PathHostFilesystem,
)
from tests.support.host_fixture import HostFixture


class BackendIoTests(unittest.TestCase):
    def test_fixture_filesystem_reads_writes_and_sorts_virtual_globs(self):
        with HostFixture() as fixture:
            fixture.write("/sys/example/z", "z\n")
            fixture.write("/sys/example/a", "powersave\n")
            host = PathHostFilesystem(fixture.root)

            host.write_text("/sys/example/a", "performance\n")

            self.assertEqual(host.read_text("/sys/example/a"), "performance\n")
            self.assertEqual(
                host.glob("/sys/example/*"),
                ("/sys/example/a", "/sys/example/z"),
            )
            self.assertTrue(host.exists("/sys/example/a"))
            self.assertTrue(host.is_writable("/sys/example/a"))

    def test_virtual_paths_must_be_absolute_and_cannot_escape_root(self):
        with HostFixture() as fixture:
            fixture.write("/sys/example/value", "ok\n")
            outside = Path(fixture.root).parent / "outside-host-value"
            outside.write_text("outside\n")
            self.addCleanup(outside.unlink, missing_ok=True)
            fixture.symlink("/sys/example/escape", outside)

            for path in ("sys/example/value", "/sys/../outside-host-value"):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        fixture.filesystem.read_text(path)
            with self.assertRaises(ValueError):
                fixture.filesystem.read_text("/sys/example/escape")

    def test_writes_refuse_missing_files_and_symlinks(self):
        with HostFixture() as fixture:
            fixture.write("/sys/example/value", "before\n")
            fixture.symlink("/sys/example/link", fixture.path("/sys/example/value"))

            with self.assertRaises(FileNotFoundError):
                fixture.filesystem.write_text("/sys/example/missing", "new\n")
            with self.assertRaises(ValueError):
                fixture.filesystem.write_text("/sys/example/link", "changed\n")
            self.assertEqual(fixture.read("/sys/example/value"), "before\n")

    def test_local_command_executor_uses_argument_tuple_without_shell(self):
        completed = subprocess.CompletedProcess(("command", "arg"), 0, "ok", "")
        with patch("arm64_probe.backends.io.subprocess.run", return_value=completed) as run:
            result = LocalCommandExecutor().run(("command", "arg"))

        self.assertIs(result, completed)
        run.assert_called_once_with(
            ("command", "arg"),
            capture_output=True,
            check=False,
            shell=False,
            text=True,
        )

    def test_local_runtime_wraps_load_average(self):
        with patch.object(os, "getloadavg", return_value=(1.0, 2.0, 3.0)):
            self.assertEqual(LocalHostRuntime().load_average(), (1.0, 2.0, 3.0))


if __name__ == "__main__":
    unittest.main()
