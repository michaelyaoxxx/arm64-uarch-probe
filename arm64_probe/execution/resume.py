"""
Resume service for re-executing failed and missing probe cases.

Reads a prior RunResult, validates compatibility, diffs sample state,
and re-runs only error cases. Ok cases are carried over; skipped cases
are dropped.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from arm64_probe.domain.models import Case, Plan, RunResult, Sample
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.execution.result_store import ResultStore

if TYPE_CHECKING:
    from arm64_probe.execution.runner import Runner


class ResumeService:
    """Re-executes failed cases from a prior RunResult.

    The service validates compatibility between the prior result and
    the current plan, then diffs the prior samples to determine which
    cases to carry over, re-execute, or drop.
    """

    def __init__(self, store: ResultStore, runner: "Runner | None" = None):
        """
        Args:
            store: RunResultStore for writing new results.
            runner: Runner for re-executing cases.  None in unit tests.
        """
        self._store = store
        self._runner = runner

    def resume(
        self,
        prior: RunResult,
        *,
        plan: Plan,
        platform_id: str,
        allow_mutation: bool = False,
        output_dir: Path,
    ) -> RunResult:
        """
        Resume execution from a prior RunResult.

        Algorithm:
        1. Validate compatibility (schema, platform, case definitions).
        2. For each case in the current Plan:
           - If prior sample was "ok", carry it over (preserve original run_id).
           - If prior sample was "error", re-execute (or add error sample if no runner).
           - If prior sample was "skipped", drop it.
           - If case is missing from prior, re-execute (or add error sample).
        3. Write the new RunResult.
        4. Return the new RunResult.

        Args:
            prior: The prior RunResult.
            plan: The current Plan.
            platform_id: Platform identifier.
            allow_mutation: Whether host mutations are authorized.
            output_dir: Directory for writing the new RunResult.

        Returns:
            A new RunResult with resume metadata.

        Raises:
            ProbeError: With code RUN_RESULT(16) if compatibility check fails.
        """
        # 1. Validate compatibility
        self._store.validate_compatibility(prior, plan)

        # 2. Build a map from prior samples: case_id -> sample
        prior_samples: dict[str, Sample] = {}
        for s in prior.samples:
            prior_samples[s.case_id] = s

        # 3. Diff and build new samples
        new_samples: list[Sample] = []
        has_errors = False
        has_missing = False
        skipped_case_ids: list[str] = []

        for case in plan.cases:
            prior_sample = prior_samples.get(case.id)

            if prior_sample is None:
                # Case is missing in prior → re-execute
                has_missing = True
                if self._runner is not None:
                    re_run = self._runner._execute_case(prior.run_id, case)
                    new_samples.append(re_run)
                else:
                    new_samples.append(Sample(
                        run_id=prior.run_id,
                        case_id=case.id,
                        sample_index=0,
                        status="error",
                        metrics=(("error", "no runner; case not re-executed"),),
                    ))
            elif prior_sample.status == "ok":
                # Carry over unchanged
                new_samples.append(prior_sample)
            elif prior_sample.status == "error":
                # Re-execute
                has_errors = True
                if self._runner is not None:
                    re_run = self._runner._execute_case(prior.run_id, case)
                    new_samples.append(re_run)
                else:
                    new_samples.append(Sample(
                        run_id=prior.run_id,
                        case_id=case.id,
                        sample_index=0,
                        status="error",
                        metrics=(("error", "no runner; case not re-executed"),),
                    ))
            elif prior_sample.status == "skipped":
                # Drop — neither carry nor re-execute
                skipped_case_ids.append(case.id)

        # 4. Determine resume_kind
        errors_remaining = any(
            s.status == "error" for s in new_samples
        )
        if has_errors or has_missing or errors_remaining:
            resume_kind = "failed" if has_errors else "missing"
        else:
            resume_kind = "no-op"

        # 5. Build the new RunResult
        run_id = self._generate_run_id()

        summary_pairs = [
            ("platform_id", platform_id),
            ("prior_run_id", prior.run_id),
            ("resume_kind", resume_kind),
            ("total_cases", len(plan.cases)),
            ("carried_ok", sum(1 for s in new_samples
                              if s.run_id == prior.run_id and s.status == "ok")),
            ("re_executed", sum(1 for s in new_samples
                               if s.run_id != prior.run_id or s.status == "error")),
        ]
        if skipped_case_ids:
            summary_pairs.append(("skipped_cases", ",".join(skipped_case_ids)))

        result = RunResult(
            run_id=run_id,
            plan=plan,
            samples=tuple(new_samples),
            summary=tuple(summary_pairs),
            environment=(),
            schema_version=2,
            prior_run_id=prior.run_id,
            resume_kind=resume_kind,
        )

        # 6. Persist
        self._store.write_result(result)

        return result

    @staticmethod
    def _generate_run_id() -> str:
        """Generate a unique run ID for the resumed run."""
        import uuid
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uuid_part = uuid.uuid4().hex[:8]
        return f"{timestamp}-{uuid_part}"
