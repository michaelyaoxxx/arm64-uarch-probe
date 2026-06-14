import unittest
from dataclasses import replace
from pathlib import Path

from arm64_probe.platforms.configured import ConfiguredPlatformAdapter
from arm64_probe.registry.validation import load_platform


ROOT = Path(__file__).resolve().parents[2]


class PlatformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = ConfiguredPlatformAdapter()
        cls.gb10 = load_platform(ROOT / "configs" / "platforms" / "gb10.json")
        cls.m4 = load_platform(ROOT / "configs" / "platforms" / "m4.json")

    def test_shared_platform_contract(self):
        for platform in (self.gb10, self.m4):
            with self.subTest(platform=platform.id):
                for cpu_set in (*platform.clusters, *platform.core_groups):
                    self.assertEqual(cpu_set.cpus, tuple(sorted(set(cpu_set.cpus))))
                first = self.adapter.resolve_single(platform, None, None, None)
                second = self.adapter.resolve_single(platform, None, None, None)
                self.assertEqual(first, second)

    def test_measurement_support_is_explicit(self):
        self.assertEqual(self.gb10.measurement_support, "supported")
        self.assertEqual(self.m4.measurement_support, "contract-only")
        self.assertIn("cpu-binding", self.gb10.capabilities)
        self.assertNotIn("cpu-binding", self.m4.capabilities)

    def test_semantic_and_explicit_single_cpu_resolution(self):
        self.assertEqual(
            self.adapter.resolve_single(self.gb10, "c0", "x925", None),
            (5, "platform-selector:x925"),
        )
        self.assertEqual(
            self.adapter.resolve_single(self.gb10, "c0", "x925", 7),
            (7, "cli"),
        )

    def test_declared_representative_cpus_drive_semantic_resolution(self):
        representatives = dict(self.gb10.representative_cpus)
        representatives["c0.x925"] = 7
        representatives["c1.x925"] = 17
        platform = replace(
            self.gb10,
            representative_cpus=tuple(sorted(representatives.items())),
        )

        self.assertEqual(
            self.adapter.resolve_single(platform, "c0", "x925", None),
            (7, "platform-selector:x925"),
        )
        self.assertEqual(
            self.adapter.resolve_pair(
                platform, "pair-same-core", "c0", "x925", None, None
            ),
            (7, 7, "platform-selector:x925"),
        )
        self.assertEqual(
            self.adapter.resolve_pair(
                platform, "pair-cross-cluster", "c0", "x925", None, None
            ),
            (7, 17, "platform-selector:x925"),
        )

    def test_pair_resolution_is_deterministic(self):
        self.assertEqual(
            self.adapter.resolve_pair(
                self.gb10, "pair-same-core", "c0", "x925", None, None
            ),
            (5, 5, "platform-selector:x925"),
        )
        self.assertEqual(
            self.adapter.resolve_pair(
                self.gb10, "pair-same-cluster", "c0", "x925", None, None
            ),
            (5, 6, "platform-selector:x925"),
        )
        self.assertEqual(
            self.adapter.resolve_pair(
                self.gb10, "pair-cross-cluster", "c0", "x925", None, None
            ),
            (5, 15, "platform-selector:x925"),
        )

    def test_explicit_pair_override_wins(self):
        self.assertEqual(
            self.adapter.resolve_pair(
                self.gb10, "pair-cross-cluster", "c0", "x925", 6, 16
            ),
            (6, 16, "platform-selector:x925"),
        )

    def test_pair_modes_match_cluster_semantics_on_every_platform(self):
        for platform in (self.gb10, self.m4):
            clusters = {
                item.id: set(item.cpus)
                for item in platform.clusters
            }
            same = self.adapter.resolve_pair(
                platform, "pair-same-cluster", None, None, None, None
            )
            cross = self.adapter.resolve_pair(
                platform, "pair-cross-cluster", None, None, None, None
            )
            with self.subTest(platform=platform.id, mode="same"):
                self.assertTrue(
                    any({same[0], same[1]}.issubset(cpus) for cpus in clusters.values())
                )
            with self.subTest(platform=platform.id, mode="cross"):
                self.assertFalse(
                    any({cross[0], cross[1]}.issubset(cpus) for cpus in clusters.values())
                )

    def test_same_cluster_honors_core_group_without_crossing_clusters(self):
        src, dst, _ = self.adapter.resolve_pair(
            self.m4,
            "pair-same-cluster",
            None,
            "performance",
            None,
            None,
        )
        self.assertIn(src, {0, 2})
        self.assertIsNone(dst)


if __name__ == "__main__":
    unittest.main()
