"""
Main execution runner for probes.

Drives the planner's Plan through one EnvironmentCoordinator.execute
invocation per environment phase, accumulating Sample records into a RunResult.
"""
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
import uuid

from arm64_probe.domain.models import Case, Plan, Sample
from arm64_probe.environment.constants import REPOSITORY_ID
from arm64_probe.environment.coordinator import EnvironmentCoordinator
from arm64_probe.environment.models import ControllerRequest
from arm64_probe.execution.adapters.base import ProbeAdapter, ProbeError
from arm64_probe.execution.result_store import ResultStore, case_definitions_signature


class CommandExecutor(Protocol):
    """Protocol for command execution (allows mocking in tests)."""

    def execute(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        """
        Execute a command and return (returncode, stdout, stderr).

        Args:
            command: Command and arguments
            cwd: Working directory
            timeout: Timeout in seconds

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        ...


class SubprocessExecutor:
    """Default command executor using subprocess."""

    def execute(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout: int | None = None,
    ) -> tuple[int, str, str]:
        """Execute command using subprocess."""
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)


class Runner:
    """
    Execute probe cases according to a Plan.

    The runner:
    1. Groups cases by environment phase
    2. For each phase, applies environment changes via EnvironmentCoordinator
    3. Executes each case's probe via the appropriate adapter
    4. Collects samples and builds a RunResult with full provenance
    """

    _DEFAULT_CASE_TIMEOUT_SECONDS = 60

    def __init__(
        self,
        coordinator: EnvironmentCoordinator,
        result_store: ResultStore,
        adapters: dict[str, ProbeAdapter],
        command_executor: CommandExecutor | None = None,
        bin_dir: Path | None = None,
        case_timeout_seconds: int = _DEFAULT_CASE_TIMEOUT_SECONDS,
    ):
        """
        Initialize the runner.

        Args:
            coordinator: Environment coordinator for applying/restoring state
            result_store: Store for persisting results
            adapters: Map of probe_name -> ProbeAdapter
            command_executor: Executor for running probe commands (default: subprocess)
            bin_dir: Directory containing probe binaries (default: build/bin)
            case_timeout_seconds: Per-case timeout in seconds (default: 60)
        """
        self.coordinator = coordinator
        self.result_store = result_store
        self.adapters = adapters
        self.command_executor = command_executor or SubprocessExecutor()
        self.bin_dir = bin_dir or Path("build/bin")
        self._case_timeout = case_timeout_seconds

    def run(self, plan: Plan, allow_mutation: bool = False):
        """
        Execute all cases in the plan.

        Args:
            plan: The Plan to execute
            allow_mutation: Whether to allow environment mutations

        Returns:
            The completed RunResult with full provenance
        """
        from arm64_probe.domain.models import RunResult

        run_id = self._generate_run_id()
        samples = []

        # Group cases by environment phase
        phase_cases = self._group_by_phase(plan)

        # Execute each phase
        journal_tx_ids: list[str] = []
        for phase, cases in phase_cases.items():
            phase_samples = self._execute_phase(
                run_id, plan, phase, cases, allow_mutation
            )
            samples.extend(phase_samples)

        # Build the provenance summary
        summary_pairs = self._build_summary(plan, samples, phase_cases)

        # Build the RunResult
        result = RunResult(
            run_id=run_id,
            plan=plan,
            samples=tuple(samples),
            summary=tuple(summary_pairs),
            environment=tuple(self._extract_environment_info()),
            journal_transactions=tuple(journal_tx_ids),
        )

        # Store the result
        self.result_store.write_result(result)

        return result

    def _build_summary(
        self,
        plan: Plan,
        samples: list[Sample],
        phase_cases: dict[str, list[Case]],
    ) -> list[tuple[str, object]]:
        """Build the provenance-rich summary for the RunResult."""
        total = len(samples)
        ok_count = sum(1 for s in samples if s.status == "ok")
        error_count = sum(1 for s in samples if s.status == "error")
        skipped_count = sum(1 for s in samples if s.status == "skipped")

        pairs: list[tuple[str, object]] = [
            ("phase_count", len(phase_cases)),
            ("total_samples", total),
            ("ok_samples", ok_count),
            ("error_samples", error_count),
            ("skipped_samples", skipped_count),
            ("platform_id", plan.platform_id),
            ("case_definitions_signature", case_definitions_signature(plan)),
            ("repository_id", REPOSITORY_ID),
            ("repository_commit", self._detect_repository_commit()),
            ("dirty_tree", self._detect_dirty_tree()),
        ]
        return pairs

    @staticmethod
    def _detect_repository_commit() -> str:
        """Detect the current git HEAD commit."""
        try:
            result = subprocess.run(
                ("git", "rev-parse", "HEAD"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def _detect_dirty_tree() -> bool:
        """Detect whether the working tree has uncommitted changes."""
        try:
            result = subprocess.run(
                ("git", "diff-index", "--quiet", "HEAD", "--"),
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode != 0
        except Exception:
            return True  # Assume dirty if we can't check

    def _generate_run_id(self) -> str:
        """Generate a unique run ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        uuid_part = uuid.uuid4().hex[:8]
        return f"{timestamp}-{uuid_part}"

    def _group_by_phase(self, plan: Plan) -> dict[str, list[Case]]:
        """Group cases by their environment phase ID."""
        phase_map = {}

        # If there are no environment phases, treat all cases as a single default phase
        if not plan.environment_phases:
            phase_map["default"] = list(plan.cases)
            return phase_map

        for case in plan.cases:
            # Find which phase this case belongs to
            for phase in plan.environment_phases:
                if case.id in phase.case_ids:
                    phase_id = phase.id
                    if phase_id not in phase_map:
                        phase_map[phase_id] = []
                    phase_map[phase_id].append(case)
                    break

        return phase_map

    def _execute_phase(
        self,
        run_id: str,
        plan: Plan,
        phase_id: str,
        cases: list[Case],
        allow_mutation: bool,
    ) -> list[Sample]:
        """Execute all cases in a single phase."""
        samples = []

        # Handle default phase (no environment changes)
        if phase_id == "default":
            for case in cases:
                sample = self._execute_case(run_id, case)
                samples.append(sample)
            return samples

        # Find the phase definition
        phase = None
        for p in plan.environment_phases:
            if p.id == phase_id:
                phase = p
                break

        if phase is None:
            raise ValueError(f"Phase not found: {phase_id}")

        # Build controller requests for this phase
        requests = self._build_requests_for_phase(phase)

        # When there are no host-scoped requirements, skip the coordinator
        # and execute cases directly — no mutation lock or journal needed.
        if not requests:
            for case in cases:
                sample = self._execute_case(run_id, case)
                samples.append(sample)
            return samples

        # Define the work function that executes cases
        def work():
            for case in cases:
                sample = self._execute_case(run_id, case)
                samples.append(sample)

        # Execute through coordinator
        try:
            self.coordinator.execute(
                platform_id=plan.platform_id,
                requests=requests,
                work=work,
                allow_mutation=allow_mutation,
            )
        except Exception as e:
            # If coordinator fails, record error samples for remaining cases
            for case in cases:
                if not any(s.case_id == case.id for s in samples):
                    error_sample = Sample(
                        run_id=run_id,
                        case_id=case.id,
                        sample_index=0,
                        status="error",
                        metrics=(("error", str(e)),),
                    )
                    samples.append(error_sample)

        return samples

    def _build_requests_for_phase(self, phase) -> tuple[ControllerRequest, ...]:
        """Build controller requests from phase host requirements."""
        requests = []
        for req in phase.host_requirements:
            if req.scope == "host":
                request = ControllerRequest(
                    controller_id=req.capability_id,
                    values=req.values,
                )
                requests.append(request)
        return tuple(requests)

    def _execute_case(self, run_id: str, case: Case) -> Sample:
        """Execute a single case and return a Sample."""
        # Skip cases that are not ready to execute
        if case.status != "ready":
            return Sample(
                run_id=run_id,
                case_id=case.id,
                sample_index=0,
                status="skipped",
                metrics=(("reason", case.status),),
            )

        try:
            # Determine which probe to use based on scenario
            probe_name = self._get_probe_for_scenario(case.scenario_id)
            adapter = self.adapters.get(probe_name)

            if adapter is None:
                return Sample(
                    run_id=run_id,
                    case_id=case.id,
                    sample_index=0,
                    status="error",
                    metrics=(("error", f"No adapter for probe: {probe_name}"),),
                )

            # Build probe arguments from case parameters
            argv = self._build_probe_argv(adapter, case)

            # Execute the probe with configured timeout
            probe_path = self.bin_dir / probe_name
            returncode, stdout, stderr = self.command_executor.execute(
                [str(probe_path)] + argv,
                timeout=self._case_timeout,
            )

            # Check for execution errors
            if returncode != 0:
                return Sample(
                    run_id=run_id,
                    case_id=case.id,
                    sample_index=0,
                    status="error",
                    metrics=(
                        ("error", f"Probe exited with code {returncode}"),
                        ("stderr", stderr),
                    ),
                )

            # Parse the output
            result = adapter.parse_output(stdout, stderr)

            if isinstance(result, ProbeError):
                return Sample(
                    run_id=run_id,
                    case_id=case.id,
                    sample_index=0,
                    status="error",
                    metrics=(
                        ("error", result.message),
                        ("stderr", stderr),
                    ),
                )

            # Build metrics from ProbeOutput
            metrics = [
                ("latency_ns", result.latency_ns),
                ("accesses", result.accesses),
                ("elapsed_ns", result.elapsed_ns),
            ]

            if result.sink_address:
                metrics.append(("sink_address", result.sink_address))

            # Add additional metrics
            for key, value in result.additional_metrics.items():
                metrics.append((key, value))

            return Sample(
                run_id=run_id,
                case_id=case.id,
                sample_index=0,
                status="ok",
                metrics=tuple(metrics),
            )

        except Exception as e:
            return Sample(
                run_id=run_id,
                case_id=case.id,
                sample_index=0,
                status="error",
                metrics=(("error", str(e)),),
            )

    def _get_probe_for_scenario(self, scenario_id: str) -> str:
        """Determine which probe to use for a scenario.

        First checks the adapter registry by scenario_id, then falls
        back to probe-name matching for backward compatibility.
        """
        # Direct lookup: adapter keyed by scenario_id
        if scenario_id in self.adapters:
            return scenario_id

        # Fallback: adapter keyed by probe name (legacy)
        for probe_name, adapter in self.adapters.items():
            if hasattr(adapter, 'scenario_id') and adapter.scenario_id == scenario_id:
                return probe_name

        # Broad fallback: scenario prefix matching
        if "cache-latency" in scenario_id:
            return "chase_pmu"
        elif "migration-latency" in scenario_id:
            return "chase_migrate"
        else:
            # Try evict_slc for setup scenarios
            if "evict" in scenario_id:
                return "evict_slc"
            raise ValueError(f"Unknown scenario: {scenario_id}")

    def _build_probe_argv(self, adapter: ProbeAdapter, case: Case) -> list[str]:
        """Build probe command-line arguments from case parameters."""
        # Extract parameters from case
        # case.parameters is tuple of (name, ResolvedValue) pairs
        params = {name: rv.value for name, rv in case.parameters}

        # Common parameters
        working_set = params.get("working-set", "1MB")
        # Parse working set size (e.g., "1MB" -> 1024 KB)
        if working_set.endswith("MB"):
            working_set_kb = int(working_set[:-2]) * 1024
        elif working_set.endswith("KB"):
            working_set_kb = int(working_set[:-2])
        else:
            working_set_kb = 1024  # Default

        page_policy = params.get("page-policy", "default")
        hugepage = page_policy == "hugepage"

        # Build adapter-specific arguments
        if adapter.probe_name == "chase_migrate":
            # chase_migrate needs src_cpu and dst_cpu
            src_cpu = case.src_cpu if case.src_cpu is not None else case.cpu
            dst_cpu = case.dst_cpu if case.dst_cpu is not None else case.cpu

            return adapter.build_argv(
                cpu=case.cpu or 0,
                working_set_kb=working_set_kb,
                src_cpu=src_cpu,
                dst_cpu=dst_cpu,
                hugepage=hugepage,
            )
        else:
            # Other probes use standard arguments
            return adapter.build_argv(
                cpu=case.cpu or 0,
                working_set_kb=working_set_kb,
                hugepage=hugepage,
            )

    def _extract_environment_info(self) -> list[tuple[str, str]]:
        """Extract environment information from the last coordinator journal."""
        # For now, return basic info
        # In a full implementation, this would read from the coordinator's journal
        return [
            ("platform", "unknown"),
            ("timestamp", datetime.now(timezone.utc).isoformat()),
        ]
