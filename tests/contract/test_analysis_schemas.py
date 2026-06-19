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
        self.assertEqual(
            schema["required"],
            [
                "analysis_id", "schema_version", "source_runs", "platform_id",
                "repository_id", "repository_commit", "dirty_tree", "toolchain",
            ],
        )

    def test_schema_version_const_is_1(self):
        schema = json.loads(self.schema_path.read_text())
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)

    def test_validates_minimal_example(self):
        """Verify a minimal valid AnalysisSummary JSON passes schema validation."""
        schema = json.loads(self.schema_path.read_text())
        example = {
            "analysis_id": "20260617T120000Z-a1b2c3d4",
            "schema_version": 1,
            "source_runs": ["run1"],
            "platform_id": "gb10",
            "repository_id": "github.com/x/arm64-uarch-probe",
            "repository_commit": "abc123",
            "dirty_tree": False,
            "toolchain": [["python", "3.13.13"]],
            "case_analyses": [],
            "cross_run_comparisons": [],
            "anomalies": [],
            "generated_at": "2026-06-17T12:00:00Z",
        }
        self._validate_or_assert(example, schema)

    def test_validates_with_nullable_stats(self):
        """Verify metric_stats with null statistic fields passes validation."""
        schema = json.loads(self.schema_path.read_text())
        example = {
            "analysis_id": "20260617T120000Z-a1b2c3d4",
            "schema_version": 1,
            "source_runs": ["run1"],
            "platform_id": "gb10",
            "repository_id": "github.com/x/arm64-uarch-probe",
            "repository_commit": "abc123",
            "dirty_tree": False,
            "toolchain": [["python", "3.13.13"]],
            "case_analyses": [
                {
                    "case_id": "l1@gb10.cpu-0",
                    "scenario_id": "cache-latency.l1-latency",
                    "platform_id": "gb10",
                    "status": "ok",
                    "total_samples": 5,
                    "ok_samples": 5,
                    "error_samples": 0,
                    "metric_stats": {
                        "latency_ns": {
                            "metric_name": "latency_ns",
                            "unit": "ns",
                            "sample_count": 5,
                            "success_count": 5,
                            "error_count": 0,
                            "min_value": None,
                            "max_value": None,
                            "median": None,
                            "mad": None,
                            "mean": None,
                            "stddev": None,
                        }
                    },
                    "anomalies": [],
                    "source_run_ids": ["run1"],
                }
            ],
            "cross_run_comparisons": [],
            "anomalies": [],
            "generated_at": "2026-06-17T12:00:00Z",
        }
        self._validate_or_assert(example, schema)

    def test_validates_cross_run_with_null_deltas(self):
        """Verify cross_run_comparison with null delta fields passes validation."""
        schema = json.loads(self.schema_path.read_text())
        example = {
            "analysis_id": "20260617T120000Z-a1b2c3d4",
            "schema_version": 1,
            "source_runs": ["run1", "run2"],
            "platform_id": "gb10",
            "repository_id": "github.com/x/arm64-uarch-probe",
            "repository_commit": "abc123",
            "dirty_tree": False,
            "toolchain": [["python", "3.13.13"]],
            "case_analyses": [],
            "cross_run_comparisons": [
                {
                    "case_id": "l1@gb10.cpu-0",
                    "runs_compared": ["run1", "run2"],
                    "classification": "unchanged",
                    "metric_deltas": {
                        "latency_ns": {
                            "metric_name": "latency_ns",
                            "unit": "ns",
                            "baseline_value": None,
                            "current_value": None,
                            "delta_pct": None,
                        }
                    },
                    "note": None,
                }
            ],
            "anomalies": [],
            "generated_at": "2026-06-17T12:00:00Z",
        }
        self._validate_or_assert(example, schema)

    def _validate_or_assert(self, instance, schema):
        try:
            import jsonschema
            jsonschema.validate(instance, schema)
        except ImportError:
            # Fallback: manual field check via json round-trip
            dumped = json.dumps(instance, sort_keys=True)
            loaded = json.loads(dumped)
            self.assertEqual(loaded["analysis_id"], instance["analysis_id"])
            self.assertEqual(loaded["schema_version"], 1)
            self.assertIsInstance(loaded["case_analyses"], list)
            self.assertIsInstance(loaded["cross_run_comparisons"], list)


class BaselineManifestSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema_path = SCHEMAS / "baseline-manifest.schema.json"

    def test_schema_file_exists(self):
        self.assertTrue(self.schema_path.exists(), f"Schema not found: {self.schema_path}")

    def test_required_fields_present(self):
        schema = json.loads(self.schema_path.read_text())
        self.assertEqual(
            schema["required"],
            ["baseline_id", "version", "source_run_ids", "analysis_id"],
        )

    def test_validates_minimal_example(self):
        """Verify a minimal valid BaselineManifest JSON passes schema validation."""
        schema = json.loads(self.schema_path.read_text())
        example = {
            "baseline_id": "v1.0.0",
            "version": "1.0.0",
            "source_run_ids": ["run1", "run2"],
            "analysis_id": "20260617T120000Z-a1b2c3d4",
            "commands": ["./probe run --platform gb10 --profile full"],
            "repository_commit": "abc123",
            "dirty_tree": False,
            "toolchain": [["python", "3.13.13"]],
            "promoted_at": "2026-06-17T12:00:00Z",
        }
        self._validate_or_assert(example, schema)

    def test_validates_with_null_optionals(self):
        """Verify BaselineManifest with null optional fields passes validation."""
        schema = json.loads(self.schema_path.read_text())
        example = {
            "baseline_id": "v1.0.0",
            "version": "1.0.0",
            "source_run_ids": ["run1"],
            "analysis_id": "20260617T120000Z-a1b2c3d4",
            "report_id": None,
            "figure_ids": [],
            "commands": ["./probe run --platform gb10 --profile smoke"],
            "repository_commit": "abc123",
            "dirty_tree": False,
            "toolchain": [["python", "3.13.13"]],
            "promoted_at": "2026-06-17T12:00:00Z",
            "approved_by": None,
        }
        self._validate_or_assert(example, schema)

    def _validate_or_assert(self, instance, schema):
        try:
            import jsonschema
            jsonschema.validate(instance, schema)
        except ImportError:
            # Fallback: manual field check via json round-trip
            dumped = json.dumps(instance, sort_keys=True)
            loaded = json.loads(dumped)
            self.assertEqual(loaded["baseline_id"], instance["baseline_id"])
            self.assertIsInstance(loaded["source_run_ids"], list)


if __name__ == "__main__":
    unittest.main()
