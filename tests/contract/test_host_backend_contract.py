import unittest
from pathlib import Path

from arm64_probe.backends.darwin_arm64.backend import DarwinArm64Backend
from arm64_probe.backends.linux_arm64.backend import LinuxArm64Backend
from arm64_probe.backends.select import select_backend
from arm64_probe.environment.constants import OBSERVATION_STATUSES
from tests.support.host_fixture import HostFixture


ROOT = Path(__file__).resolve().parents[2]


class FakeRuntime:
    def load_average(self):
        return (0.25, 0.5, 0.75)


class HostBackendContractTests(unittest.TestCase):
    def test_backends_return_sorted_observations_and_unique_controllers(self):
        with HostFixture() as fixture:
            backends = (
                LinuxArm64Backend(fixture.filesystem, FakeRuntime()),
                DarwinArm64Backend(FakeRuntime(), "Darwin", "arm64"),
            )
            for backend in backends:
                with self.subTest(backend=backend.id):
                    observations = backend.inspect()
                    self.assertEqual(
                        tuple(item.capability_id for item in observations),
                        tuple(sorted(item.capability_id for item in observations)),
                    )
                    self.assertTrue(
                        all(item.status in OBSERVATION_STATUSES for item in observations)
                    )
                    controllers = backend.controllers()
                    self.assertEqual(
                        len({controller.id for controller in controllers}),
                        len(controllers),
                    )

    def test_darwin_explicitly_reports_unsupported_mutation_boundary(self):
        backend = DarwinArm64Backend(FakeRuntime(), "Darwin", "arm64")

        observations = {item.capability_id: item for item in backend.inspect()}

        self.assertEqual(backend.controllers(), ())
        for capability_id in (
            "cpu-binding",
            "linux.cpufreq",
            "linux.hugepage",
            "linux.transparent-hugepage",
            "pmu.armv9",
        ):
            self.assertEqual(observations[capability_id].status, "unsupported")
        self.assertEqual(observations["host.os"].status, "available")
        self.assertEqual(observations["host.load"].status, "available")

    def test_backend_selection_constructs_only_supported_backends(self):
        with HostFixture() as fixture:
            linux = select_backend(
                system="Linux",
                machine="aarch64",
                filesystem=fixture.filesystem,
                runtime=FakeRuntime(),
            )
            darwin = select_backend(
                system="Darwin",
                machine="arm64",
                runtime=FakeRuntime(),
            )

        self.assertEqual(linux.id, "linux-arm64")
        self.assertEqual(darwin.id, "darwin-arm64")

    def test_backend_modules_do_not_import_experiments_or_gb10_policy(self):
        source = "\n".join(
            path.read_text()
            for path in sorted((ROOT / "arm64_probe" / "backends").rglob("*.py"))
        ).lower()

        self.assertNotIn("arm64_probe.experiments", source)
        self.assertNotIn("gb10", source)

    def test_linux_registers_inspectable_cpu_frequency_controller(self):
        with HostFixture() as fixture:
            base = "/sys/devices/system/cpu/cpufreq/policy0"
            fixture.write(f"{base}/related_cpus", "0-3\n")
            fixture.write(f"{base}/scaling_governor", "powersave\n")
            fixture.write(
                f"{base}/scaling_available_governors",
                "performance powersave\n",
            )
            fixture.write(f"{base}/scaling_min_freq", "1000\n")
            fixture.write(f"{base}/scaling_max_freq", "3000\n")
            backend = LinuxArm64Backend(fixture.filesystem, FakeRuntime())

            controllers = backend.controllers()
            observations = {item.capability_id: item for item in backend.inspect()}

        self.assertEqual(tuple(item.id for item in controllers), ("linux.cpufreq",))
        self.assertEqual(observations["linux.cpufreq"].status, "available")

    def test_linux_registers_all_inspectable_controllers_in_fixed_order(self):
        with HostFixture() as fixture:
            base = "/sys/devices/system/cpu/cpufreq/policy0"
            fixture.write(f"{base}/related_cpus", "0-3\n")
            fixture.write(f"{base}/scaling_governor", "powersave\n")
            fixture.write(
                f"{base}/scaling_available_governors",
                "performance powersave\n",
            )
            fixture.write(f"{base}/scaling_min_freq", "1000\n")
            fixture.write(f"{base}/scaling_max_freq", "3000\n")
            fixture.write(
                "/sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages",
                "4\n",
            )
            fixture.write(
                "/sys/kernel/mm/transparent_hugepage/enabled",
                "always [madvise] never\n",
            )
            backend = LinuxArm64Backend(fixture.filesystem, FakeRuntime())

            controllers = backend.controllers()
            observations = {item.capability_id: item for item in backend.inspect()}

        self.assertEqual(
            tuple(item.id for item in controllers),
            (
                "linux.cpufreq",
                "linux.hugepage",
                "linux.transparent-hugepage",
            ),
        )
        self.assertEqual(observations["linux.hugepage"].status, "available")
        self.assertEqual(
            observations["linux.transparent-hugepage"].status,
            "available",
        )


if __name__ == "__main__":
    unittest.main()
