import json
import subprocess
import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode
from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog
from arm64_probe.serialization.json_io import dump_json
from arm64_probe.serialization.model_json import to_data


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SCENARIOS = (
    "cache-latency.l1-latency",
    "cache-latency.l2-latency",
    "cache-latency.l3-latency",
    "cache-latency.slc-latency",
    "cache-latency.dram-latency",
    "migration-latency.same-core",
    "migration-latency.same-cluster",
    "migration-latency.cross-cluster",
)


class Phase1AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT)
        cls.planner = Planner(cls.catalog)

    def test_public_schema_and_registry_inventory_loads(self):
        schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
        registries = (
            ROOT / "configs" / "capabilities.json",
            *sorted((ROOT / "configs" / "platforms").glob("*.json")),
            *sorted((ROOT / "configs" / "experiments").glob("*.json")),
            *sorted((ROOT / "configs" / "profiles").glob("*.json")),
        )

        self.assertEqual(len(schemas), 11)
        self.assertEqual(len(registries), 7)
        for path in (*schemas, *registries):
            with self.subTest(path=path):
                self.assertIsInstance(json.loads(path.read_text()), dict)

    def test_canonical_scenarios_and_shared_platform_contract_are_stable(self):
        self.assertEqual(
            tuple(item.id for item in self.catalog.scenarios()),
            EXPECTED_SCENARIOS,
        )
        for platform in self.catalog.platforms():
            with self.subTest(platform=platform.id):
                self.assertTrue(platform.clusters)
                self.assertTrue(platform.core_groups)
                self.assertTrue(platform.representative_cpus)
                self.assertIn(platform.measurement_support, {"supported", "contract-only"})

    def test_representative_plans_are_byte_deterministic(self):
        requests = (
            PlanRequest(platform_id="m4", profile_id="smoke"),
            PlanRequest(
                platform_id="gb10",
                selections=(
                    "cache-latency.l2-latency",
                    "migration-latency.cross-cluster",
                ),
            ),
        )
        for request in requests:
            with self.subTest(request=request):
                first = dump_json(to_data(self.planner.plan(request)))
                second = dump_json(to_data(self.planner.plan(request)))
                self.assertEqual(first, second)

    def test_cli_contract_documents_stable_exit_codes(self):
        contract = (ROOT / "docs" / "design" / "cli-contract.md").read_text()

        for exit_code in ExitCode:
            with self.subTest(exit_code=exit_code):
                self.assertIn(f"| `{int(exit_code)}` |", contract)
        self.assertIn("| `10+` |", contract)

    def test_frozen_and_transitional_paths_are_unchanged(self):
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "main",
                "--",
                "runner",
                "data",
                "analysis",
                "baseline",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
