import unittest

from arm64_probe.backends.linux_arm64.cpu_frequency import CpuFrequencyController
from arm64_probe.environment.models import ControllerRequest
from arm64_probe.errors import ExitCode, ProbeError
from tests.support.host_fixture import HostFixture


class RecordingFilesystem:
    def __init__(self, delegate, unwritable=(), fail_on_write=()):
        self.delegate = delegate
        self.unwritable = set(unwritable)
        self.fail_on_write = set(fail_on_write)
        self.writes = []

    def exists(self, path):
        return self.delegate.exists(path)

    def read_text(self, path):
        return self.delegate.read_text(path)

    def write_text(self, path, value):
        self.writes.append((path, value))
        if path in self.fail_on_write:
            raise OSError(f"write failed: {path}")
        self.delegate.write_text(path, value)

    def glob(self, pattern):
        return self.delegate.glob(pattern)

    def is_writable(self, path):
        return path not in self.unwritable and self.delegate.is_writable(path)


def populate_policy(
    fixture,
    policy_id,
    related_cpus,
    governor="powersave",
    minimum=1000,
    maximum=3000,
):
    base = f"/sys/devices/system/cpu/cpufreq/{policy_id}"
    fixture.write(f"{base}/related_cpus", f"{related_cpus}\n")
    fixture.write(f"{base}/scaling_governor", f"{governor}\n")
    fixture.write(f"{base}/scaling_available_governors", "performance powersave\n")
    fixture.write(f"{base}/scaling_min_freq", f"{minimum}\n")
    fixture.write(f"{base}/scaling_max_freq", f"{maximum}\n")
    return base


class CpuFrequencyControllerTests(unittest.TestCase):
    def test_inspects_policy_domains_as_flat_deterministic_state(self):
        with HostFixture() as fixture:
            populate_policy(fixture, "policy4", "4-5")
            populate_policy(fixture, "policy0", "0-3")

            state = CpuFrequencyController(fixture.filesystem).inspect()

        self.assertEqual(state.controller_id, "linux.cpufreq")
        self.assertEqual(state.status, "available")
        values = dict(state.values)
        self.assertEqual(values["policy0.related-cpus"], "0,1,2,3")
        self.assertEqual(values["policy0.governor"], "powersave")
        self.assertEqual(values["policy0.min-khz"], 1000)
        self.assertEqual(values["policy0.max-khz"], 3000)
        self.assertEqual(tuple(values), tuple(sorted(values)))

    def test_rejects_invalid_requests_missing_state_and_unwritable_files(self):
        with HostFixture() as fixture:
            base = populate_policy(fixture, "policy0", "0-3")
            host = RecordingFilesystem(
                fixture.filesystem,
                unwritable=(f"{base}/scaling_governor",),
            )
            controller = CpuFrequencyController(host)
            invalid = (
                ControllerRequest("linux.cpufreq", (("unknown", 1),)),
                ControllerRequest("linux.cpufreq", (("governor", "unknown"),)),
                ControllerRequest("linux.cpufreq", (("min-khz", 0),)),
                ControllerRequest(
                    "linux.cpufreq",
                    (("max-khz", 1000), ("min-khz", 2000)),
                ),
                ControllerRequest("other", (("governor", "performance"),)),
            )
            for request in invalid:
                with self.subTest(request=request):
                    with self.assertRaises(ProbeError) as error:
                        controller.validate_request(request)
                    self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)
            with self.assertRaises(ProbeError) as error:
                controller.validate_request(
                    ControllerRequest(
                        "linux.cpufreq",
                        (("governor", "performance"),),
                    )
                )
            self.assertEqual(error.exception.code, ExitCode.MUTATION_AUTHORIZATION)
            self.assertEqual(host.writes, [])

            fixture.path(f"{base}/related_cpus").unlink()
            self.assertNotEqual(controller.inspect().status, "available")
            with self.assertRaises(ProbeError):
                controller.validate_request(
                    ControllerRequest("linux.cpufreq", (("min-khz", 500),))
                )
            self.assertEqual(host.writes, [])

    def test_apply_verify_restore_and_verify_restored_use_safe_order(self):
        with HostFixture() as fixture:
            policy0 = populate_policy(fixture, "policy0", "0-3")
            policy4 = populate_policy(fixture, "policy4", "4-5")
            host = RecordingFilesystem(fixture.filesystem)
            controller = CpuFrequencyController(host)
            before = controller.inspect()
            request = ControllerRequest(
                "linux.cpufreq",
                (
                    ("governor", "performance"),
                    ("max-khz", 800),
                    ("min-khz", 500),
                ),
            )

            controller.apply(request)
            effective = controller.verify(request)

            self.assertEqual(effective.status, "available")
            expected_apply = []
            for base in (policy0, policy4):
                expected_apply.extend(
                    (
                        (f"{base}/scaling_governor", "performance\n"),
                        (f"{base}/scaling_min_freq", "500\n"),
                        (f"{base}/scaling_max_freq", "800\n"),
                    )
                )
            self.assertEqual(host.writes, expected_apply)

            host.writes.clear()
            controller.restore(before)
            restored = controller.verify_restored(before)

            self.assertEqual(restored.values, before.values)
            expected_restore = []
            for base in (policy0, policy4):
                expected_restore.extend(
                    (
                        (f"{base}/scaling_max_freq", "3000\n"),
                        (f"{base}/scaling_min_freq", "1000\n"),
                        (f"{base}/scaling_governor", "powersave\n"),
                    )
                )
            self.assertEqual(host.writes, expected_restore)

    def test_apply_uses_max_then_min_when_target_max_covers_current_min(self):
        with HostFixture() as fixture:
            base = populate_policy(fixture, "policy0", "0-3")
            host = RecordingFilesystem(fixture.filesystem)
            controller = CpuFrequencyController(host)

            controller.apply(
                ControllerRequest(
                    "linux.cpufreq",
                    (("max-khz", 2500), ("min-khz", 1200)),
                )
            )

            self.assertEqual(
                host.writes,
                [
                    (f"{base}/scaling_max_freq", "2500\n"),
                    (f"{base}/scaling_min_freq", "1200\n"),
                ],
            )

    def test_verification_mismatch_and_partial_write_failure_are_structured(self):
        with HostFixture() as fixture:
            base = populate_policy(fixture, "policy0", "0-3")
            request = ControllerRequest(
                "linux.cpufreq",
                (("governor", "performance"),),
            )
            failing_host = RecordingFilesystem(
                fixture.filesystem,
                fail_on_write=(f"{base}/scaling_governor",),
            )
            with self.assertRaises(ProbeError) as error:
                CpuFrequencyController(failing_host).apply(request)
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)
            self.assertEqual(len(failing_host.writes), 1)

            controller = CpuFrequencyController(fixture.filesystem)
            with self.assertRaises(ProbeError) as error:
                controller.verify(request)
            self.assertEqual(error.exception.code, ExitCode.ENVIRONMENT_APPLY)


if __name__ == "__main__":
    unittest.main()
