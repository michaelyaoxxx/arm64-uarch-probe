import unittest

from arm64_probe.backends.linux_arm64.inspector import (
    LinuxArm64Inspector,
    parse_bracketed_policy,
    parse_cpu_list,
)
from tests.support.host_fixture import HostFixture


class FakeRuntime:
    def load_average(self):
        return (0.25, 0.5, 0.75)


class FaultFilesystem:
    def __init__(self, delegate, permission_denied=()):
        self.delegate = delegate
        self.permission_denied = set(permission_denied)

    def exists(self, path):
        return self.delegate.exists(path)

    def read_text(self, path):
        if path in self.permission_denied:
            raise PermissionError(path)
        return self.delegate.read_text(path)

    def write_text(self, path, value):
        return self.delegate.write_text(path, value)

    def glob(self, pattern):
        return self.delegate.glob(pattern)

    def is_writable(self, path):
        return self.delegate.is_writable(path)


def populate_linux_fixture(fixture):
    fixture.write("/sys/devices/system/cpu/online", "0-3\n")
    for cpu in range(4):
        fixture.write(
            f"/sys/devices/system/cpu/cpu{cpu}/topology/cluster_id",
            f"{cpu // 2}\n",
        )
    fixture.write("/sys/devices/system/cpu/cpu0/cache/index0/level", "1\n")
    fixture.write("/sys/devices/system/cpu/cpu0/cache/index0/type", "Data\n")
    fixture.write("/sys/devices/system/cpu/cpu0/cache/index0/size", "64K\n")
    fixture.write("/proc/sys/kernel/perf_event_paranoid", "2\n")
    fixture.write("/sys/bus/event_source/devices/armv8_pmuv3/type", "5\n")


class LinuxInspectorTests(unittest.TestCase):
    def test_parses_linux_cpu_lists_and_bracketed_policies(self):
        self.assertEqual(parse_cpu_list("0-3,8,10-11"), (0, 1, 2, 3, 8, 10, 11))
        self.assertEqual(
            parse_bracketed_policy("always [madvise] never"),
            ("madvise", ("always", "madvise", "never")),
        )
        for invalid in ("", "3-1", "0,0", "x"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    parse_cpu_list(invalid)
        with self.assertRaises(ValueError):
            parse_bracketed_policy("always madvise never")

    def test_reports_expected_read_only_linux_observations(self):
        with HostFixture() as fixture:
            populate_linux_fixture(fixture)

            observations = LinuxArm64Inspector(
                fixture.filesystem,
                FakeRuntime(),
            ).inspect()

        by_id = {observation.capability_id: observation for observation in observations}
        self.assertEqual(
            tuple(by_id),
            (
                "host.cache",
                "host.cpu-online",
                "host.kernel-interfaces",
                "host.load",
                "host.pmu",
                "host.topology",
            ),
        )
        self.assertEqual(dict(by_id["host.cpu-online"].values)["count"], 4)
        self.assertEqual(dict(by_id["host.topology"].values)["cluster-count"], 2)
        self.assertEqual(dict(by_id["host.cache"].values)["entry-count"], 1)
        self.assertEqual(dict(by_id["host.pmu"].values)["pmu-type"], 5)
        self.assertEqual(by_id["host.load"].status, "available")

    def test_missing_permission_denied_and_malformed_files_are_observations(self):
        with HostFixture() as fixture:
            missing = LinuxArm64Inspector(fixture.filesystem, FakeRuntime()).inspect()
            fixture.write("/sys/devices/system/cpu/online", "not-a-cpu-list\n")
            malformed = LinuxArm64Inspector(fixture.filesystem, FakeRuntime()).inspect()
            denied = LinuxArm64Inspector(
                FaultFilesystem(
                    fixture.filesystem,
                    permission_denied=("/sys/devices/system/cpu/online",),
                ),
                FakeRuntime(),
            ).inspect()

        missing_by_id = {item.capability_id: item for item in missing}
        malformed_by_id = {item.capability_id: item for item in malformed}
        denied_by_id = {item.capability_id: item for item in denied}
        self.assertEqual(missing_by_id["host.cpu-online"].status, "unavailable")
        self.assertEqual(malformed_by_id["host.cpu-online"].status, "unavailable")
        self.assertEqual(denied_by_id["host.cpu-online"].status, "permission-denied")


if __name__ == "__main__":
    unittest.main()
