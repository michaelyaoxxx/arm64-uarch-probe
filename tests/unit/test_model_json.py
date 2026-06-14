import unittest

from arm64_probe.serialization.model_json import to_data
from tests.unit.test_domain_models import build_models


class ModelJsonTests(unittest.TestCase):
    def test_plan_serialization_preserves_resolved_sources(self):
        plan = build_models()[-1]

        data = to_data(plan)

        self.assertEqual(data["platform_id"], "gb10")
        self.assertEqual(data["cases"][0]["parameters"]["samples"]["value"], 7)
        self.assertEqual(
            data["cases"][0]["parameters"]["samples"]["source"],
            "platform-default",
        )
        self.assertEqual(
            data["cases"][0]["selectors"]["cpu"]["source"],
            "platform-selector:x925",
        )
        self.assertNotIn("timestamp", data)
        self.assertNotIn("run_id", data)

    def test_mapping_like_tuples_serialize_in_sorted_order(self):
        plan = build_models()[-1]

        case_data = to_data(plan)["cases"][0]

        self.assertEqual(list(case_data["parameters"]), ["samples"])
        self.assertEqual(list(case_data["selectors"]), ["cpu"])

    def test_unknown_type_is_rejected(self):
        with self.assertRaises(TypeError):
            to_data(object())


if __name__ == "__main__":
    unittest.main()
