import unittest

from arm64_probe.backends.base import HostBackend, MutationController
from arm64_probe.backends.select import backend_id_for_host
from arm64_probe.errors import ExitCode, ProbeError


class BackendSelectionTests(unittest.TestCase):
    def test_backend_protocols_expose_required_operations(self):
        for operation in ("inspect", "controllers"):
            self.assertTrue(hasattr(HostBackend, operation))
        for operation in (
            "inspect",
            "validate_request",
            "apply",
            "verify",
            "restore",
            "verify_restored",
        ):
            self.assertTrue(hasattr(MutationController, operation))

    def test_selects_only_supported_os_architecture_pairs(self):
        cases = (
            ("Linux", "aarch64", "linux-arm64"),
            ("Linux", "arm64", "linux-arm64"),
            ("Darwin", "arm64", "darwin-arm64"),
            ("Darwin", "aarch64", "darwin-arm64"),
        )
        for system, machine, expected in cases:
            with self.subTest(system=system, machine=machine):
                self.assertEqual(backend_id_for_host(system, machine), expected)

    def test_rejects_unsupported_host_as_inspection_error(self):
        for system, machine in (("Linux", "x86_64"), ("Windows", "arm64")):
            with self.subTest(system=system, machine=machine):
                with self.assertRaises(ProbeError) as error:
                    backend_id_for_host(system, machine)
                self.assertEqual(error.exception.code, ExitCode.HOST_INSPECTION)


if __name__ == "__main__":
    unittest.main()
