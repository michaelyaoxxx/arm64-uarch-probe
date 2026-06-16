"""Tests for ResumeService and RunResult resume-related fields."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arm64_probe.domain.models import (
    Case,
    Plan,
    ResolvedValue,
    RunResult,
    Sample,
)
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.execution.result_store import ResultStore, case_definitions_signature


class RunResultResumeFieldsTests(unittest.TestCase):
    """Test that RunResult supports resume-related fields (Task 16 completion)."""

    def _minimal_plan(self) -> Plan:
        """Create a minimal Plan for testing."""
        case = Case(
            id="test-case-1",
            scenario_id="test-scenario",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("samples", ResolvedValue(7, "platform-default")),
            ),
        )
        return Plan(
            platform_id="test-platform",
            profile_id=None,
            selections=("test-scenario",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

    def test_run_result_has_schema_version_default_2(self):
        """RunResult schema_version should default to 2."""
        plan = self._minimal_plan()
        sample = Sample(
            run_id="run-1",
            case_id="test-case-1",
            sample_index=0,
            status="ok",
            metrics=(("latency_ns", 4.5),),
        )
        result = RunResult(
            run_id="run-1",
            plan=plan,
            samples=(sample,),
            summary=(("total_cases", 1),),
            environment=(),
        )
        self.assertEqual(result.schema_version, 2)

    def test_run_result_has_prior_run_id_default_none(self):
        """RunResult prior_run_id should default to None."""
        plan = self._minimal_plan()
        result = RunResult(
            run_id="run-1",
            plan=plan,
            samples=(),
            summary=(),
            environment=(),
        )
        self.assertIsNone(result.prior_run_id)

    def test_run_result_has_resume_kind_default_none(self):
        """RunResult resume_kind should default to None."""
        plan = self._minimal_plan()
        result = RunResult(
            run_id="run-1",
            plan=plan,
            samples=(),
            summary=(),
            environment=(),
        )
        self.assertIsNone(result.resume_kind)

    def test_run_result_accepts_explicit_resume_fields(self):
        """RunResult should accept prior_run_id and resume_kind explicitly."""
        plan = self._minimal_plan()
        result = RunResult(
            run_id="run-2",
            plan=plan,
            samples=(),
            summary=(),
            environment=(),
            prior_run_id="run-1",
            resume_kind="failed",
        )
        self.assertEqual(result.prior_run_id, "run-1")
        self.assertEqual(result.resume_kind, "failed")


class CaseDefinitionsSignatureTests(unittest.TestCase):
    """Test case_definitions_signature stability and sensitivity."""

    def _minimal_plan(self) -> Plan:
        case = Case(
            id="test-case-1",
            scenario_id="test-scenario",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("samples", ResolvedValue(7, "platform-default")),
            ),
        )
        return Plan(
            platform_id="test-platform",
            profile_id=None,
            selections=("test-scenario",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

    def test_signature_is_stable_for_same_plan(self):
        """Same plan should produce identical signatures."""
        plan1 = self._minimal_plan()
        plan2 = self._minimal_plan()
        self.assertEqual(
            case_definitions_signature(plan1),
            case_definitions_signature(plan2),
        )

    def test_signature_changes_with_different_case_id(self):
        """Signature must change when a case ID changes."""
        plan1 = self._minimal_plan()
        case = Case(
            id="different-case",
            scenario_id="test-scenario",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("samples", ResolvedValue(7, "platform-default")),
            ),
        )
        plan2 = Plan(
            platform_id="test-platform",
            profile_id=None,
            selections=("test-scenario",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )
        self.assertNotEqual(
            case_definitions_signature(plan1),
            case_definitions_signature(plan2),
        )

    def test_signature_is_64_hex_chars(self):
        """Signature should be a 64-character hex string (SHA-256)."""
        plan = self._minimal_plan()
        sig = case_definitions_signature(plan)
        self.assertEqual(len(sig), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in sig))


class ValidateCompatibilityTests(unittest.TestCase):
    """Test ResultStore.validate_compatibility for resume guard."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.store = ResultStore(self.results_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _sample_plan(self) -> Plan:
        case = Case(
            id="test-case-1",
            scenario_id="test-scenario",
            platform_id="test-platform",
            status="ready",
            reason=None,
            cpu=0,
            src_cpu=None,
            dst_cpu=None,
            selectors=(),
            parameters=(
                ("samples", ResolvedValue(7, "platform-default")),
            ),
        )
        return Plan(
            platform_id="test-platform",
            profile_id=None,
            selections=("test-scenario",),
            cases=(case,),
            environment_phases=(),
            skip_unavailable=False,
        )

    def _sample_result(self, run_id="run-1", schema_version=2,
                       platform_id="test-platform") -> RunResult:
        plan = self._sample_plan()
        return RunResult(
            run_id=run_id,
            plan=plan,
            samples=(),
            summary=(
                ("platform_id", platform_id),
                ("repository_id", "test-repo"),
                ("repository_commit", "a" * 40),
                ("case_definitions_signature", case_definitions_signature(plan)),
            ),
            environment=(),
            schema_version=schema_version,
        )

    def test_validate_compatibility_succeeds_on_match(self):
        """validate_compatibility should not raise when all fields match."""
        plan = self._sample_plan()
        prior = self._sample_result()
        with patch("arm64_probe.environment.constants.REPOSITORY_ID", "test-repo"):
            self.store.validate_compatibility(prior, plan)

    def test_validate_compatibility_rejects_schema_version_mismatch(self):
        """Exit 16 when prior schema_version differs."""
        plan = self._sample_plan()
        prior = self._sample_result(schema_version=1)
        with self.assertRaises(ProbeError) as ctx:
            self.store.validate_compatibility(prior, plan)
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)

    def test_validate_compatibility_rejects_platform_id_mismatch(self):
        """Exit 16 when prior platform_id differs from plan."""
        plan = self._sample_plan()
        prior = self._sample_result(platform_id="other-platform")
        with self.assertRaises(ProbeError) as ctx:
            self.store.validate_compatibility(prior, plan)
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)

    def test_validate_compatibility_rejects_case_definitions_signature_mismatch(self):
        """Exit 16 when case_definitions_signature differs."""
        plan = self._sample_plan()
        prior = self._sample_result()
        # Tamper with the signature in summary
        prior_dict = {
            "run_id": prior.run_id,
            "plan": prior.plan,
            "samples": prior.samples,
            "summary": tuple(
                (k, v) for k, v in prior.summary
                if k != "case_definitions_signature"
            ) + (("case_definitions_signature", "b" * 64),),
            "environment": prior.environment,
            "schema_version": prior.schema_version,
        }
        tampered = RunResult(**prior_dict)
        with patch("arm64_probe.environment.constants.REPOSITORY_ID", "test-repo"):
            with self.assertRaises(ProbeError) as ctx:
                self.store.validate_compatibility(tampered, plan)
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)

    def test_validate_compatibility_rejects_repository_id_mismatch(self):
        """Exit 16 when repository_id differs."""
        plan = self._sample_plan()
        prior = self._sample_result()
        prior_dict = {
            "run_id": prior.run_id,
            "plan": prior.plan,
            "samples": prior.samples,
            "summary": tuple(
                (k, v) for k, v in prior.summary
                if k != "repository_id"
            ) + (("repository_id", "different-repo"),),
            "environment": prior.environment,
            "schema_version": prior.schema_version,
        }
        tampered = RunResult(**prior_dict)
        with self.assertRaises(ProbeError) as ctx:
            self.store.validate_compatibility(tampered, plan)
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)


class ResumeServiceTests(unittest.TestCase):
    """Test ResumeService diff logic and idempotency."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.results_dir = Path(self.temp_dir) / "results"
        self.store = ResultStore(self.results_dir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _plan_with_cases(self, case_ids: list[str]) -> Plan:
        """Create a Plan with the given case IDs."""
        cases = tuple(
            Case(
                id=cid,
                scenario_id="test-scenario",
                platform_id="test-platform",
                status="ready",
                reason=None,
                cpu=0,
                src_cpu=None,
                dst_cpu=None,
                selectors=(),
                parameters=(("samples", ResolvedValue(7, "platform-default")),),
            )
            for cid in case_ids
        )
        return Plan(
            platform_id="test-platform",
            profile_id=None,
            selections=("test-scenario",),
            cases=cases,
            environment_phases=(),
            skip_unavailable=False,
        )

    def _sample(self, run_id: str, case_id: str, index: int,
                status: str = "ok") -> Sample:
        return Sample(
            run_id=run_id,
            case_id=case_id,
            sample_index=index,
            status=status,
            metrics=(("latency_ns", 4.5),),
        )

    def test_resume_carries_over_ok_cases(self):
        """ok cases should be carried over unchanged in resume."""
        from arm64_probe.execution.resume import ResumeService

        plan = self._plan_with_cases(["case-1", "case-2"])
        prior = RunResult(
            run_id="prior-run",
            plan=plan,
            samples=(
                self._sample("prior-run", "case-1", 0, "ok"),
                self._sample("prior-run", "case-2", 0, "ok"),
            ),
            summary=(
                ("platform_id", "test-platform"),
                ("repository_id", "test-repo"),
                ("case_definitions_signature", case_definitions_signature(plan)),
            ),
            environment=(),
            schema_version=2,
        )

        service = ResumeService(self.store, runner=None)
        with patch("arm64_probe.environment.constants.REPOSITORY_ID", "test-repo"):
            new_result = service.resume(
                prior, plan=plan,
                platform_id="test-platform",
                allow_mutation=False,
                output_dir=self.results_dir,
            )

        self.assertEqual(len(new_result.samples), 2)
        self.assertEqual(new_result.samples[0].run_id, "prior-run")  # preserved
        self.assertEqual(new_result.samples[1].run_id, "prior-run")  # preserved
        self.assertEqual(new_result.prior_run_id, "prior-run")
        self.assertEqual(new_result.resume_kind, "no-op")

    def test_resume_reruns_error_cases(self):
        """error cases should be re-executed in resume."""
        from arm64_probe.execution.resume import ResumeService

        plan = self._plan_with_cases(["case-1", "case-2"])
        prior = RunResult(
            run_id="prior-run",
            plan=plan,
            samples=(
                self._sample("prior-run", "case-1", 0, "ok"),
                self._sample("prior-run", "case-2", 0, "error"),
            ),
            summary=(
                ("platform_id", "test-platform"),
                ("repository_id", "test-repo"),
                ("case_definitions_signature", case_definitions_signature(plan)),
            ),
            environment=(),
            schema_version=2,
        )

        service = ResumeService(self.store, runner=None)
        with patch("arm64_probe.environment.constants.REPOSITORY_ID", "test-repo"):
            new_result = service.resume(
                prior, plan=plan,
                platform_id="test-platform",
                allow_mutation=False,
                output_dir=self.results_dir,
            )

        # case-1 carried, case-2 has error sample (runner=None skips execution)
        self.assertGreaterEqual(len(new_result.samples), 1)
        carried_ids = {s.case_id for s in new_result.samples if s.run_id == "prior-run"}
        self.assertIn("case-1", carried_ids)
        self.assertEqual(new_result.prior_run_id, "prior-run")
        self.assertIn(new_result.resume_kind, ("failed", "missing"))

    def test_resume_drops_skipped_cases(self):
        """skipped cases should be dropped (not carried, not re-executed)."""
        from arm64_probe.execution.resume import ResumeService

        plan = self._plan_with_cases(["case-1", "case-2"])
        prior = RunResult(
            run_id="prior-run",
            plan=plan,
            samples=(
                self._sample("prior-run", "case-1", 0, "ok"),
                self._sample("prior-run", "case-2", 0, "skipped"),
            ),
            summary=(
                ("platform_id", "test-platform"),
                ("repository_id", "test-repo"),
                ("case_definitions_signature", case_definitions_signature(plan)),
            ),
            environment=(),
            schema_version=2,
        )

        service = ResumeService(self.store, runner=None)
        with patch("arm64_probe.environment.constants.REPOSITORY_ID", "test-repo"):
            new_result = service.resume(
                prior, plan=plan,
                platform_id="test-platform",
                allow_mutation=False,
                output_dir=self.results_dir,
            )

        # Only case-1 should be present; case-2 (skipped) dropped
        case_ids_in_result = {s.case_id for s in new_result.samples}
        self.assertIn("case-1", case_ids_in_result)
        self.assertNotIn("case-2", case_ids_in_result)

    def test_resume_rejects_schema_version_mismatch(self):
        """Resume should reject schema_version=1 prior before any re-execution."""
        from arm64_probe.execution.resume import ResumeService

        plan = self._plan_with_cases(["case-1"])
        prior = RunResult(
            run_id="prior-run",
            plan=plan,
            samples=(self._sample("prior-run", "case-1", 0, "ok"),),
            summary=(("platform_id", "test-platform"),),
            environment=(),
            schema_version=1,
        )

        service = ResumeService(self.store, runner=None)
        with self.assertRaises(ProbeError) as ctx:
            service.resume(
                prior, plan=plan,
                platform_id="test-platform",
                allow_mutation=False,
                output_dir=self.results_dir,
            )
        self.assertEqual(ctx.exception.code, ExitCode.RUN_RESULT)

    def test_resume_is_idempotent_on_fully_successful_prior(self):
        """Repeated resume on fully ok result should produce no-op."""
        from arm64_probe.execution.resume import ResumeService

        plan = self._plan_with_cases(["case-1"])
        prior = RunResult(
            run_id="prior-run",
            plan=plan,
            samples=(self._sample("prior-run", "case-1", 0, "ok"),),
            summary=(
                ("platform_id", "test-platform"),
                ("repository_id", "test-repo"),
                ("case_definitions_signature", case_definitions_signature(plan)),
            ),
            environment=(),
            schema_version=2,
        )

        service = ResumeService(self.store, runner=None)
        with patch("arm64_probe.environment.constants.REPOSITORY_ID", "test-repo"):
            result1 = service.resume(
                prior, plan=plan,
                platform_id="test-platform",
                allow_mutation=False,
                output_dir=self.results_dir,
            )
            self.assertEqual(result1.resume_kind, "no-op")

            # Second resume on the same result should also be no-op
            result2 = service.resume(
                result1, plan=plan,
                platform_id="test-platform",
                allow_mutation=False,
                output_dir=self.results_dir,
            )
            self.assertEqual(result2.resume_kind, "no-op")


if __name__ == "__main__":
    unittest.main()
