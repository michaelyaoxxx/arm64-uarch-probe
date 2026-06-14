import json
import shutil
import tempfile
import unittest
from pathlib import Path

from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.registry.catalog import Catalog


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


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog.load(ROOT)

    def test_loads_expected_catalog(self):
        self.assertEqual(
            tuple(item.id for item in self.catalog.scenarios()),
            EXPECTED_SCENARIOS,
        )
        self.assertEqual(
            tuple(item.id for item in self.catalog.experiments()),
            ("cache-latency", "migration-latency"),
        )
        self.assertEqual(
            tuple(item.id for item in self.catalog.profiles()),
            ("baseline", "smoke"),
        )
        self.assertEqual(
            tuple(item.id for item in self.catalog.platforms()),
            ("gb10", "m4"),
        )

    def test_expands_experiment_and_scenario_selection(self):
        self.assertEqual(
            tuple(item.id for item in self.catalog.expand_selection("cache-latency")),
            EXPECTED_SCENARIOS[:5],
        )
        self.assertEqual(
            tuple(
                item.id
                for item in self.catalog.expand_selection(
                    "migration-latency.cross-cluster"
                )
            ),
            ("migration-latency.cross-cluster",),
        )

    def test_unknown_lookup_is_structured_error(self):
        with self.assertRaises(ProbeError) as error:
            self.catalog.expand_selection("unknown")

        self.assertEqual(error.exception.code, ExitCode.CONFIG)
        self.assertIn("unknown target", error.exception.message)

    def test_rejects_duplicate_experiment_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "configs", root / "configs")
            source = root / "configs" / "experiments" / "cache-latency.json"
            shutil.copy(source, source.with_name("duplicate.json"))

            with self.assertRaises(ProbeError) as error:
                Catalog.load(root)

        self.assertEqual(error.exception.code, ExitCode.CONFIG)
        self.assertIn("duplicate experiment", error.exception.message)

    def test_rejects_unknown_profile_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "configs", root / "configs")
            profile = root / "configs" / "profiles" / "smoke.json"
            payload = json.loads(profile.read_text())
            payload["selections"] = ["unknown"]
            profile.write_text(json.dumps(payload))

            with self.assertRaises(ProbeError) as error:
                Catalog.load(root)

        self.assertEqual(error.exception.code, ExitCode.CONFIG)
        self.assertIn("unknown selection", error.exception.message)


if __name__ == "__main__":
    unittest.main()
