import dataclasses
import unittest

from arm64_probe.diagnostics.doctor import Doctor
from arm64_probe.environment.models import CapabilityObservation
from arm64_probe.errors import ExitCode, ProbeError
from tests.unit.test_environment_models import build_environment_models


class FakeBackend:
    id = "linux-arm64"

    def __init__(self, observations=(), error=None):
        self.observations = observations
        self.error = error

    def inspect(self):
        if self.error is not None:
            raise self.error
        return self.observations

    def controllers(self):
        return ()


class FakeJournalReader:
    def __init__(self, journals=()):
        self.journals = journals

    def unfinished(self):
        return self.journals


class DoctorTests(unittest.TestCase):
    def test_builds_sorted_report_with_unfinished_and_failed_journals(self):
        observations = (
            CapabilityObservation("linux.hugepage", "unsupported", (), (), None, False),
            CapabilityObservation("host.load", "available", (), (), None, True),
        )
        journal = build_environment_models()[4]
        failed = dataclasses.replace(
            journal,
            transaction_id="transaction-0",
            state="restore-failed",
        )

        report = Doctor(
            FakeBackend(observations),
            FakeJournalReader((journal, failed)),
        ).inspect(platform_id="gb10")

        self.assertEqual(report.backend_id, "linux-arm64")
        self.assertEqual(report.platform_id, "gb10")
        self.assertEqual(
            tuple(item.capability_id for item in report.observations),
            ("host.load", "linux.hugepage"),
        )
        self.assertEqual(
            tuple(item.transaction_id for item in report.journals),
            ("transaction-0", "transaction-1"),
        )

    def test_expected_unsupported_observation_is_a_successful_report(self):
        observation = CapabilityObservation(
            "linux.cpufreq",
            "unsupported",
            (),
            (),
            None,
            False,
        )

        report = Doctor(FakeBackend((observation,)), FakeJournalReader()).inspect(None)

        self.assertEqual(report.observations, (observation,))

    def test_backend_inspection_exception_becomes_exit_code_10(self):
        failures = (
            RuntimeError("inspection failed"),
            ProbeError(ExitCode.CONFIG, "configuration", "internal failure"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                with self.assertRaises(ProbeError) as error:
                    Doctor(
                        FakeBackend(error=failure),
                        FakeJournalReader(),
                    ).inspect(None)

                self.assertEqual(error.exception.code, ExitCode.HOST_INSPECTION)
                self.assertNotIn(str(failure), error.exception.message)


if __name__ == "__main__":
    unittest.main()
