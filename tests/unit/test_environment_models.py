import dataclasses
import unittest

from arm64_probe.environment.models import (
    CapabilityObservation,
    ControllerRequest,
    ControllerState,
    DoctorReport,
    EnvironmentJournal,
    JournalFailure,
)
from arm64_probe.serialization.model_json import to_data


def build_environment_models():
    request = ControllerRequest(
        "linux.cpufreq",
        (("governor", "performance"),),
    )
    state = ControllerState(
        "linux.cpufreq",
        "available",
        (("governor", "powersave"),),
        ("policy0",),
    )
    observation = CapabilityObservation(
        "linux.cpufreq",
        "available",
        (("policy-count", 1),),
        ("policy0",),
        None,
        True,
    )
    failure = JournalFailure("apply", "environment-apply", "write failed")
    journal = EnvironmentJournal(
        schema_version=1,
        transaction_id="transaction-1",
        repository_id="github.com/michaelyaoxxx/arm64-uarch-probe",
        backend_id="linux-arm64",
        platform_id="gb10",
        state="applying",
        created_at="2026-06-15T00:00:00Z",
        updated_at="2026-06-15T00:00:01Z",
        requested=(request,),
        before=(state,),
        applied=("linux.cpufreq",),
        active_controller=None,
        effective=(),
        after=(),
        restoration_status="not-started",
        failures=(failure,),
    )
    report = DoctorReport("linux-arm64", "gb10", (observation,), (journal,))
    return request, state, observation, failure, journal, report


class EnvironmentModelTests(unittest.TestCase):
    def test_models_are_frozen_and_serialize_with_public_keys(self):
        request, _, observation, _, journal, _ = build_environment_models()

        with self.assertRaises(dataclasses.FrozenInstanceError):
            journal.state = "restored"
        self.assertEqual(to_data(request)["controller_id"], "linux.cpufreq")
        self.assertEqual(to_data(observation)["status"], "available")
        self.assertEqual(to_data(journal)["applied"], ["linux.cpufreq"])

    def test_models_reject_invalid_status_and_journal_identity(self):
        with self.assertRaises(ValueError):
            CapabilityObservation("arm64", "unknown", (), (), None, False)
        with self.assertRaises(ValueError):
            ControllerState("linux.cpufreq", "unknown", (), ())

        request, state, _, _, journal, _ = build_environment_models()
        with self.assertRaises(ValueError):
            dataclasses.replace(journal, schema_version=2)
        with self.assertRaises(ValueError):
            dataclasses.replace(journal, state="unknown")
        with self.assertRaises(ValueError):
            dataclasses.replace(journal, applied=("linux.hugepage",))
        with self.assertRaises(ValueError):
            dataclasses.replace(
                journal,
                applied=(),
                active_controller="linux.hugepage",
            )
        with self.assertRaises(ValueError):
            dataclasses.replace(
                journal,
                active_controller="linux.cpufreq",
            )
        with self.assertRaises(ValueError):
            dataclasses.replace(journal, before=(state, state))
        with self.assertRaises(ValueError):
            dataclasses.replace(journal, requested=(request, request))

    def test_doctor_report_rejects_duplicate_public_identities(self):
        _, _, observation, _, journal, report = build_environment_models()

        with self.assertRaises(ValueError):
            dataclasses.replace(report, observations=(observation, observation))
        with self.assertRaises(ValueError):
            dataclasses.replace(report, journals=(journal, journal))

    def test_mapping_like_values_must_be_sorted_and_unique(self):
        with self.assertRaises(ValueError):
            ControllerRequest("linux.cpufreq", (("z", 1), ("a", 2)))
        with self.assertRaises(ValueError):
            ControllerRequest("linux.cpufreq", (("a", 1), ("a", 2)))


if __name__ == "__main__":
    unittest.main()
