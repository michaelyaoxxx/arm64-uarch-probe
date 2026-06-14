import json
import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog
from arm64_probe.serialization.model_json import to_data


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_REQUIRED = {
    "capability.schema.json": ("description", "id"),
    "platform.schema.json": (
        "capabilities",
        "clusters",
        "core_groups",
        "defaults",
        "description",
        "display_name",
        "id",
        "measurement_support",
        "representative_cpus",
    ),
    "experiment.schema.json": ("display_name", "id", "scenarios"),
    "profile.schema.json": (
        "display_name",
        "environment",
        "id",
        "overrides",
        "selections",
    ),
    "case.schema.json": (
        "cpu",
        "dst_cpu",
        "id",
        "parameters",
        "platform_id",
        "reason",
        "scenario_id",
        "selectors",
        "src_cpu",
        "status",
    ),
    "plan.schema.json": (
        "cases",
        "environment_phases",
        "platform_id",
        "profile_id",
        "selections",
        "skip_unavailable",
    ),
    "manifest.schema.json": (
        "git_commit",
        "platform_id",
        "resolved_parameters",
        "run_id",
        "toolchain",
    ),
    "environment.schema.json": (
        "after",
        "before",
        "effective",
        "requested",
        "restoration_status",
    ),
    "sample.schema.json": (
        "case_id",
        "metrics",
        "run_id",
        "sample_index",
        "status",
    ),
    "run-result.schema.json": (
        "environment",
        "plan",
        "run_id",
        "samples",
        "summary",
    ),
    "error.schema.json": ("category", "code", "context", "hint", "message"),
}


class PublicSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load(ROOT)
        cls.plan = Planner(cls.catalog).plan(
            PlanRequest(platform_id="gb10", profile_id="smoke")
        )

    def test_schema_documents_are_strict_and_stable(self):
        for filename, required in SCHEMA_REQUIRED.items():
            with self.subTest(filename=filename):
                path = ROOT / "schemas" / filename
                payload = json.loads(path.read_text())
                self.assertEqual(
                    payload["$schema"],
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(
                    payload["$id"],
                    f"https://arm64-uarch-probe.dev/schemas/{filename}",
                )
                self.assertEqual(payload["type"], "object")
                self.assertFalse(payload["additionalProperties"])
                self.assertEqual(tuple(payload["required"]), required)
                self.assertTrue(set(required).issubset(payload["properties"]))

    def test_current_model_keys_match_public_schemas(self):
        models = {
            "capability.schema.json": self.catalog.capabilities()[0],
            "platform.schema.json": self.catalog.platforms()[0],
            "experiment.schema.json": self.catalog.experiments()[0],
            "profile.schema.json": self.catalog.profiles()[0],
            "case.schema.json": self.plan.cases[0],
            "plan.schema.json": self.plan,
        }
        for filename, model in models.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    set(to_data(model)),
                    set(SCHEMA_REQUIRED[filename]),
                )

    def test_structured_error_keys_match_public_schema(self):
        error = ProbeError(
            ExitCode.PLANNING,
            "planning",
            "invalid selection",
            (("target", "unknown"),),
            "use `probe list targets`",
        )

        self.assertEqual(
            set(to_data(error)),
            set(SCHEMA_REQUIRED["error.schema.json"]),
        )


if __name__ == "__main__":
    unittest.main()
