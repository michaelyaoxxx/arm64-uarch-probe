"""Contract tests for analysis-summary and baseline-manifest schemas."""
import json
import unittest
from pathlib import Path


SCHEMAS = Path(__file__).resolve().parents[2] / "schemas"


class AnalysisSummarySchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema_path = SCHEMAS / "analysis-summary.schema.json"

    def test_schema_file_exists(self):
        self.assertTrue(self.schema_path.exists(), f"Schema not found: {self.schema_path}")

    def test_schema_is_valid_json(self):
        schema = json.loads(self.schema_path.read_text())
        self.assertEqual(schema["$schema"],
                         "https://json-schema.org/draft/2020-12/schema")

    def test_required_fields_present(self):
        schema = json.loads(self.schema_path.read_text())
        required = schema["required"]
        for field in ("analysis_id", "schema_version", "source_runs",
                       "platform_id", "repository_commit"):
            self.assertIn(field, required)

    def test_schema_version_const_is_1(self):
        schema = json.loads(self.schema_path.read_text())
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)


class BaselineManifestSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema_path = SCHEMAS / "baseline-manifest.schema.json"

    def test_schema_file_exists(self):
        self.assertTrue(self.schema_path.exists(), f"Schema not found: {self.schema_path}")

    def test_required_fields_present(self):
        schema = json.loads(self.schema_path.read_text())
        required = schema["required"]
        for field in ("baseline_id", "version", "source_run_ids", "analysis_id",
                       "commands", "repository_commit"):
            self.assertIn(field, required)


if __name__ == "__main__":
    unittest.main()
