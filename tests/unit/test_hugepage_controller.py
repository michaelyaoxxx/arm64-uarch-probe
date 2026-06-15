import unittest

from arm64_probe.backends.linux_arm64.hugepage import HugepageController
from arm64_probe.environment.models import ControllerRequest
from arm64_probe.errors import ExitCode, ProbeError
from tests.support.host_fixture import HostFixture


GLOBAL_PATH = "/sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages"
NUMA_PATH = (
    "/sys/devices/system/node/node0/hugepages/"
    "hugepages-2048kB/nr_hugepages"
)


class RecordingFilesystem:
    def __init__(self, delegate, unwritable=(), shortfall=None):
        self.delegate = delegate
        self.unwritable = set(unwritable)
        self.shortfall = shortfall
        self.writes = []

    def exists(self, path):
        return self.delegate.exists(path)

    def read_text(self, path):
        return self.delegate.read_text(path)

    def write_text(self, path, value):
        self.writes.append((path, value))
        effective = f"{self.shortfall}\n" if self.shortfall is not None else value
        self.delegate.write_text(path, effective)

    def glob(self, pattern):
        return self.delegate.glob(pattern)

    def is_writable(self, path):
        return path not in self.unwritable and self.delegate.is_writable(path)


def populate_hugepages(fixture, count=4):
    fixture.write(GLOBAL_PATH, f"{count}\n")
    fixture.write(NUMA_PATH, "2\n")


class HugepageControllerTests(unittest.TestCase):
    def test_inspects_global_pool_and_reports_numa_evidence(self):
        with HostFixture() as fixture:
            populate_hugepages(fixture)

            state = HugepageController(fixture.filesystem).inspect()

        self.assertEqual(state.status, "available")
        self.assertEqual(dict(state.values), {"2048.count": 4})
        self.assertTrue(any(NUMA_PATH in item for item in state.evidence))

    def test_rejects_invalid_unavailable_and_unwritable_requests_before_write(self):
        with HostFixture() as fixture:
            populate_hugepages(fixture)
            host = RecordingFilesystem(fixture.filesystem, unwritable=(GLOBAL_PATH,))
            controller = HugepageController(host)
            invalid = (
                ControllerRequest("other", (("count", 8), ("size-kb", 2048))),
                ControllerRequest("linux.hugepage", (("count", 8),)),
                ControllerRequest(
                    "linux.hugepage",
                    (("count", -1), ("size-kb", 2048)),
                ),
                ControllerRequest(
                    "linux.hugepage",
                    (("count", 8), ("size-kb", 0)),
                ),
                ControllerRequest(
                    "linux.hugepage",
                    (("count", 8), ("extra", 1), ("size-kb", 2048)),
                ),
                ControllerRequest(
                    "linux.hugepage",
                    (("count", 8), ("size-kb", 1048576)),
                ),
            )
            for request in invalid:
                with self.subTest(request=request):
                    with self.assertRaises(ProbeError) as error:
                        controller.validate_request(request)
                    self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)
            with self.assertRaises(ProbeError) as error:
                controller.validate_request(
                    ControllerRequest(
                        "linux.hugepage",
                        (("count", 8), ("size-kb", 2048)),
                    )
                )
            self.assertEqual(error.exception.code, ExitCode.MUTATION_AUTHORIZATION)
            self.assertEqual(host.writes, [])

    def test_applies_verifies_and_restores_only_global_pool(self):
        with HostFixture() as fixture:
            populate_hugepages(fixture)
            host = RecordingFilesystem(fixture.filesystem)
            controller = HugepageController(host)
            before = controller.inspect()
            request = ControllerRequest(
                "linux.hugepage",
                (("count", 8), ("size-kb", 2048)),
            )

            controller.apply(request)
            self.assertEqual(controller.verify(request).status, "available")
            controller.restore(before)
            self.assertEqual(controller.verify_restored(before).values, before.values)

            self.assertEqual(
                host.writes,
                [(GLOBAL_PATH, "8\n"), (GLOBAL_PATH, "4\n")],
            )
            self.assertFalse(any("/node" in path for path, _ in host.writes))

    def test_allocation_shortfall_is_a_verification_failure(self):
        with HostFixture() as fixture:
            populate_hugepages(fixture)
            host = RecordingFilesystem(fixture.filesystem, shortfall=6)
            controller = HugepageController(host)
            request = ControllerRequest(
                "linux.hugepage",
                (("count", 8), ("size-kb", 2048)),
            )

            controller.apply(request)
            with self.assertRaises(ProbeError) as error:
                controller.verify(request)

            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)


if __name__ == "__main__":
    unittest.main()
