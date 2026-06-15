import unittest

from arm64_probe.backends.linux_arm64.transparent_hugepage import (
    TransparentHugepageController,
)
from arm64_probe.environment.models import ControllerRequest
from arm64_probe.errors import ExitCode, ProbeError
from tests.support.host_fixture import HostFixture


THP_PATH = "/sys/kernel/mm/transparent_hugepage/enabled"


class KernelPolicyFilesystem:
    def __init__(self, delegate, unwritable=False, ignore_writes=False):
        self.delegate = delegate
        self.unwritable = unwritable
        self.ignore_writes = ignore_writes
        self.writes = []

    def exists(self, path):
        return self.delegate.exists(path)

    def read_text(self, path):
        return self.delegate.read_text(path)

    def write_text(self, path, value):
        self.writes.append((path, value))
        if self.ignore_writes:
            return
        selected = value.strip()
        choices = ("always", "madvise", "never")
        rendered = " ".join(
            f"[{choice}]" if choice == selected else choice for choice in choices
        )
        self.delegate.write_text(path, f"{rendered}\n")

    def glob(self, pattern):
        return self.delegate.glob(pattern)

    def is_writable(self, path):
        return not self.unwritable and self.delegate.is_writable(path)


class TransparentHugepageControllerTests(unittest.TestCase):
    def test_inspects_selected_policy_and_available_choices(self):
        with HostFixture() as fixture:
            fixture.write(THP_PATH, "always [madvise] never\n")

            state = TransparentHugepageController(fixture.filesystem).inspect()

        self.assertEqual(state.status, "available")
        self.assertEqual(
            dict(state.values),
            {"available-policies": "always,madvise,never", "policy": "madvise"},
        )

    def test_rejects_invalid_unavailable_and_unwritable_policy(self):
        with HostFixture() as fixture:
            fixture.write(THP_PATH, "always [madvise] never\n")
            host = KernelPolicyFilesystem(fixture.filesystem, unwritable=True)
            controller = TransparentHugepageController(host)
            invalid = (
                ControllerRequest("other", (("policy", "never"),)),
                ControllerRequest("linux.transparent-hugepage", (("unknown", "never"),)),
                ControllerRequest("linux.transparent-hugepage", (("policy", "unknown"),)),
            )
            for request in invalid:
                with self.subTest(request=request):
                    with self.assertRaises(ProbeError) as error:
                        controller.validate_request(request)
                    self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)
            with self.assertRaises(ProbeError) as error:
                controller.validate_request(
                    ControllerRequest(
                        "linux.transparent-hugepage",
                        (("policy", "never"),),
                    )
                )
            self.assertEqual(error.exception.code, ExitCode.MUTATION_AUTHORIZATION)
            self.assertEqual(host.writes, [])

            fixture.write(THP_PATH, "malformed\n")
            self.assertNotEqual(controller.inspect().status, "available")

    def test_applies_verifies_restores_and_detects_ignored_write(self):
        with HostFixture() as fixture:
            fixture.write(THP_PATH, "always [madvise] never\n")
            host = KernelPolicyFilesystem(fixture.filesystem)
            controller = TransparentHugepageController(host)
            before = controller.inspect()
            request = ControllerRequest(
                "linux.transparent-hugepage",
                (("policy", "never"),),
            )

            controller.apply(request)
            self.assertEqual(dict(controller.verify(request).values)["policy"], "never")
            controller.restore(before)
            self.assertEqual(controller.verify_restored(before).values, before.values)
            self.assertEqual(
                host.writes,
                [(THP_PATH, "never\n"), (THP_PATH, "madvise\n")],
            )

            ignored = TransparentHugepageController(
                KernelPolicyFilesystem(fixture.filesystem, ignore_writes=True)
            )
            ignored.apply(request)
            with self.assertRaises(ProbeError) as error:
                ignored.verify(request)
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)


if __name__ == "__main__":
    unittest.main()
