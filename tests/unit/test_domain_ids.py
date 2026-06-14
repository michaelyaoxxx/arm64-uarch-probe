import unittest

from arm64_probe.domain.ids import (
    build_case_id,
    validate_id,
    validate_scenario_id,
)


class DomainIdTests(unittest.TestCase):
    def test_accepts_canonical_ids(self):
        self.assertEqual(validate_id("cache-latency"), "cache-latency")
        self.assertEqual(
            validate_scenario_id("cache-latency.l2-latency"),
            "cache-latency.l2-latency",
        )

    def test_builds_stable_case_id(self):
        self.assertEqual(
            build_case_id(
                "cache-latency.l2-latency",
                "gb10",
                ("x925", "c0", "warm", "default-page"),
            ),
            "cache-latency.l2-latency@gb10.x925.c0.warm.default-page",
        )

    def test_rejects_noncanonical_ids(self):
        for value in ("", "Cache-Latency", "cache_latency", "cache--latency"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_id(value)

    def test_rejects_noncanonical_scenario_ids(self):
        for value in (
            "cache-latency",
            "cache-latency.",
            ".l2-latency",
            "cache-latency.l2_latency",
            "cache-latency.l2-latency.extra",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_scenario_id(value)

    def test_rejects_noncanonical_case_dimensions(self):
        for dimensions in ((), ("X925",), ("x925", "default_page")):
            with self.subTest(dimensions=dimensions):
                with self.assertRaises(ValueError):
                    build_case_id(
                        "cache-latency.l2-latency",
                        "gb10",
                        dimensions,
                    )


if __name__ == "__main__":
    unittest.main()
