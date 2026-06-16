"""
Result storage for probe execution results.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from arm64_probe.domain.models import (
    Case,
    EnvironmentPhase,
    EnvironmentRequirement,
    Plan,
    ResolvedValue,
    RunResult,
    Sample,
)
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.serialization.model_json import to_data
from arm64_probe.serialization.json_io import dump_json

MAX_RESULT_BYTES = 1024 * 1024  # 1 MiB


def case_definitions_signature(plan: Plan) -> str:
    """Stable hash of the resolved cases for cross-version compatibility.

    SHA-256 of \"\\n\".join(f\"{c.id}\\t{c.scenario_id}\\t{...sorted(c.parameters...)}\"
    for c in sorted(plan.cases, key=lambda c: c.id)).
    """
    lines = []
    for case in sorted(plan.cases, key=lambda c: c.id):
        params = "\t".join(
            f"{k}={v.value}" for k, v in sorted(case.parameters)
        )
        lines.append(f"{case.id}\t{case.scenario_id}\t{params}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


class ResultStore:
    """
    Store and retrieve probe execution results.

    Results are stored as JSON files under a configurable results directory.
    Each result file is named by its run_id.
    """

    def __init__(self, results_dir: Path):
        """
        Initialize the result store.

        Args:
            results_dir: Directory where result files are stored
        """
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def write_result(self, result: RunResult) -> Path:
        """
        Write a RunResult to disk atomically.

        Uses fsync + os.replace + parent fsync, following the pattern
        from JournalStore._atomic_write.

        Args:
            result: The RunResult to write

        Returns:
            Path to the written result file
        """
        import uuid

        result_file = self.results_dir / f"{result.run_id}.json"
        result_json = dump_json(to_data(result))

        # Atomic write: temp file → fsync → os.replace → parent fsync
        temp_file = self.results_dir / f".{result.run_id}.{uuid.uuid4().hex}.tmp"
        try:
            with open(temp_file, "w") as f:
                f.write(result_json)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, result_file)
            # fsync parent directory to durably record the replacement
            dir_fd = os.open(str(self.results_dir), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except BaseException:
            # Clean up temp file on any failure
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise

        return result_file

    def read_result(self, run_id: str) -> RunResult:
        """
        Read a RunResult from disk.

        Args:
            run_id: The run ID to read

        Returns:
            The RunResult

        Raises:
            FileNotFoundError: If the result file doesn't exist
        """
        result_file = self.results_dir / f"{run_id}.json"
        return self.read(result_file)

    def read(self, path: Path) -> RunResult:
        """
        Read a RunResult from an arbitrary path.

        Args:
            path: Path to the RunResult JSON file

        Returns:
            The RunResult

        Raises:
            ProbeError: With code RUN_RESULT(16) if the file is missing,
                        malformed, too large, or otherwise unreadable.
        """
        if not path.exists():
            raise ProbeError(
                ExitCode.RUN_RESULT,
                "run-result",
                f"result file not found: {path}",
            )

        if path.stat().st_size > MAX_RESULT_BYTES:
            raise ProbeError(
                ExitCode.RUN_RESULT,
                "run-result",
                f"result file exceeds {MAX_RESULT_BYTES} bytes: {path}",
            )

        try:
            with open(path) as f:
                result_dict = json.load(f)
        except json.JSONDecodeError as e:
            raise ProbeError(
                ExitCode.RUN_RESULT,
                "run-result",
                f"invalid JSON in result file: {path}",
                context=(("error", str(e)),),
            ) from e

        result = self._dict_to_run_result(result_dict)

        # Validate schema_version
        if result.schema_version != 2:
            raise ProbeError(
                ExitCode.RUN_RESULT,
                "run-result",
                f"unsupported schema_version={result.schema_version} "
                f"in result file: {path}",
                hint="Re-run from scratch with current probe run",
            )

        return result

    def validate_compatibility(
        self, prior: RunResult, current_plan: Plan
    ) -> None:
        """
        Validate that a prior RunResult is compatible with the current plan.

        Checks schema_version, platform_id, repository_id, repository_commit,
        and case_definitions_signature. Raises ProbeError(16) on mismatch.

        Args:
            prior: The prior RunResult to validate
            current_plan: The current Plan

        Raises:
            ProbeError: With code RUN_RESULT(16) if incompatible
        """
        summary = dict(prior.summary)

        # Schema version check
        if prior.schema_version != 2:
            raise ProbeError(
                ExitCode.RUN_RESULT,
                "run-result",
                f"prior RunResult schema_version={prior.schema_version} "
                f"is not compatible with current schema_version=2",
                hint="Re-run the original `probe run` from scratch",
            )

        # Platform ID check
        prior_platform = summary.get("platform_id")
        if prior_platform != current_plan.platform_id:
            raise ProbeError(
                ExitCode.RUN_RESULT,
                "run-result",
                f"platform mismatch: prior={prior_platform}, "
                f"current={current_plan.platform_id}",
                hint="Resume requires the same platform",
            )

        # Repository ID check
        prior_repo = summary.get("repository_id")
        if prior_repo is not None:
            from arm64_probe.environment.constants import REPOSITORY_ID
            if prior_repo != REPOSITORY_ID:
                raise ProbeError(
                    ExitCode.RUN_RESULT,
                    "run-result",
                    f"repository mismatch: prior={prior_repo}, "
                    f"current={REPOSITORY_ID}",
                    hint="Resume requires the same repository",
                )

        # Case definitions signature check
        prior_sig = summary.get("case_definitions_signature")
        current_sig = case_definitions_signature(current_plan)
        if prior_sig is not None and prior_sig != current_sig:
            raise ProbeError(
                ExitCode.RUN_RESULT,
                "run-result",
                "case definitions have changed since prior run",
                context=(
                    ("prior_signature", prior_sig),
                    ("current_signature", current_sig),
                ),
                hint="Re-run the original `probe run` from scratch",
            )

    def list_results(self) -> list[str]:
        """
        List all available run IDs.

        Returns:
            List of run IDs
        """
        return [f.stem for f in self.results_dir.glob("*.json")]

    def _dict_to_run_result(self, result_dict: dict[str, Any]) -> RunResult:
        """Convert a dict back to a RunResult."""
        # Reconstruct Plan from the nested dict
        plan_dict = result_dict["plan"]
        plan = _dict_to_plan(plan_dict)

        # Reconstruct Samples
        samples = tuple(
            _dict_to_sample(sample_dict)
            for sample_dict in result_dict["samples"]
        )

        # Reconstruct RunResult
        return RunResult(
            run_id=result_dict["run_id"],
            plan=plan,
            samples=samples,
            summary=_to_tuple_of_tuples(result_dict["summary"]),
            environment=_to_tuple_of_tuples(result_dict["environment"]),
            journal_transactions=tuple(result_dict.get("journal_transactions", [])),
            schema_version=result_dict.get("schema_version", 2),
            prior_run_id=result_dict.get("prior_run_id"),
            resume_kind=result_dict.get("resume_kind"),
        )


def _to_tuple_of_tuples(data: Any) -> tuple[tuple[str, Any], ...]:
    """Convert a dict or list of pairs back to a sorted-unique tuple of tuples."""
    if isinstance(data, dict):
        return tuple(sorted(data.items()))
    if isinstance(data, list):
        return tuple(tuple(item) if isinstance(item, list) else item for item in data)
    if isinstance(data, tuple):
        return data
    return ()


def _dict_to_plan(plan_dict: dict[str, Any]) -> Plan:
    """Convert a dict back to a Plan."""
    cases = tuple(_dict_to_case(case_dict) for case_dict in plan_dict["cases"])
    phases = tuple(_dict_to_phase(phase_dict) for phase_dict in plan_dict["environment_phases"])

    return Plan(
        platform_id=plan_dict["platform_id"],
        profile_id=plan_dict["profile_id"],
        selections=tuple(plan_dict["selections"]),
        cases=cases,
        environment_phases=phases,
        skip_unavailable=plan_dict["skip_unavailable"],
    )


def _dict_to_case(case_dict: dict[str, Any]) -> Case:
    """Convert a dict back to a Case."""
    selectors = tuple(
        (key, ResolvedValue(value=value["value"], source=value["source"]))
        for key, value in case_dict["selectors"].items()
    )
    parameters = tuple(
        (key, ResolvedValue(value=value["value"], source=value["source"]))
        for key, value in case_dict["parameters"].items()
    )
    execution_requirements = tuple(
        _dict_to_requirement(req_dict)
        for req_dict in case_dict.get("execution_requirements", [])
    )

    return Case(
        id=case_dict["id"],
        scenario_id=case_dict["scenario_id"],
        platform_id=case_dict["platform_id"],
        status=case_dict["status"],
        reason=case_dict["reason"],
        cpu=case_dict["cpu"],
        src_cpu=case_dict["src_cpu"],
        dst_cpu=case_dict["dst_cpu"],
        selectors=selectors,
        parameters=parameters,
        execution_requirements=execution_requirements,
    )


def _dict_to_phase(phase_dict: dict[str, Any]) -> EnvironmentPhase:
    """Convert a dict back to an EnvironmentPhase."""
    requirements = tuple(
        _dict_to_requirement(req_dict)
        for req_dict in phase_dict.get("host_requirements", [])
    )

    return EnvironmentPhase(
        id=phase_dict["id"],
        case_ids=tuple(phase_dict["case_ids"]),
        host_requirements=requirements,
    )


def _dict_to_requirement(req_dict: dict[str, Any]) -> EnvironmentRequirement:
    """Convert a dict back to an EnvironmentRequirement."""
    values = tuple(sorted(req_dict["values"].items()))

    return EnvironmentRequirement(
        id=req_dict["id"],
        capability_id=req_dict["capability_id"],
        scope=req_dict["scope"],
        values=values,
        mutation=req_dict["mutation"],
        requires_privilege=req_dict["requires_privilege"],
    )


def _dict_to_sample(sample_dict: dict[str, Any]) -> Sample:
    """Convert a dict back to a Sample."""
    metrics = _to_tuple_of_tuples(sample_dict["metrics"])

    return Sample(
        run_id=sample_dict["run_id"],
        case_id=sample_dict["case_id"],
        sample_index=sample_dict["sample_index"],
        status=sample_dict["status"],
        metrics=metrics,
    )
