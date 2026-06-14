import json
import tempfile
import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.registry.validation import load_capabilities, load_platform


ROOT = Path(__file__).resolve().parents[2]


def valid_platform_payload() -> dict[str, object]:
    return {
        "id": "test-platform",
        "display_name": "Test Platform",
        "description": "Contract fixture",
        "measurement_support": "contract-only",
        "capabilities": ["arm64"],
        "clusters": [{"id": "c0", "cpus": [0, 1]}],
        "core_groups": [{"id": "performance", "cpus": [0, 1]}],
        "representative_cpus": {"c0.performance": 0},
        "defaults": {"samples": 1, "page-policy": "default"},
    }


class RegistryValidationTests(unittest.TestCase):
    def write_payload(self, payload: dict[str, object]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "payload.json"
        path.write_text(json.dumps(payload))
        return path

    def test_loads_capabilities_and_platforms(self):
        capabilities = load_capabilities(ROOT / "configs" / "capabilities.json")
        gb10 = load_platform(ROOT / "configs" / "platforms" / "gb10.json")

        self.assertEqual(capabilities[0].id, "arm64")
        self.assertEqual(gb10.id, "gb10")
        self.assertIsInstance(gb10.capabilities, tuple)

    def test_rejects_unknown_fields(self):
        path = ROOT / "tests" / "fixtures" / "platforms" / "invalid-extra-field.json"

        with self.assertRaises(ProbeError) as error:
            load_platform(path)

        self.assertEqual(error.exception.code, ExitCode.CONFIG)
        self.assertIn("unknown field", error.exception.message)

    def test_rejects_duplicate_capabilities(self):
        path = self.write_payload(
            {
                "capabilities": [
                    {"id": "arm64", "description": "first"},
                    {"id": "arm64", "description": "second"},
                ]
            }
        )

        with self.assertRaises(ProbeError) as error:
            load_capabilities(path)

        self.assertEqual(error.exception.code, ExitCode.CONFIG)
        self.assertIn("duplicate", error.exception.message)

    def test_rejects_invalid_cpu_sets(self):
        cases = (
            [{"id": "c0", "cpus": [-1]}],
            [{"id": "c0", "cpus": [0]}, {"id": "c1", "cpus": [0]}],
            [{"id": "c0", "cpus": [1, 0]}],
        )
        for clusters in cases:
            with self.subTest(clusters=clusters):
                payload = valid_platform_payload()
                payload["clusters"] = clusters
                with self.assertRaises(ProbeError):
                    load_platform(self.write_payload(payload))

    def test_rejects_representative_cpu_outside_intersection(self):
        payload = valid_platform_payload()
        payload["representative_cpus"] = {"c0.performance": 9}

        with self.assertRaises(ProbeError) as error:
            load_platform(self.write_payload(payload))

        self.assertEqual(error.exception.code, ExitCode.CONFIG)
        self.assertIn("representative", error.exception.message)

    def test_rejects_unknown_measurement_support(self):
        payload = valid_platform_payload()
        payload["measurement_support"] = "maybe"

        with self.assertRaises(ProbeError) as error:
            load_platform(self.write_payload(payload))

        self.assertEqual(error.exception.code, ExitCode.CONFIG)


if __name__ == "__main__":
    unittest.main()
