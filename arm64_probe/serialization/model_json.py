from typing import Any

from arm64_probe.analysis.models import (
    AnalysisSummary,
    BaselineManifest,
    CaseAnalysis,
    CrossRunComparison,
    CrossRunMetricDelta,
    FigureManifest,
    ImportedRecord,
    MetricStats,
    ReportManifest,
)
from arm64_probe.domain.models import (
    Capability,
    Case,
    EnvironmentPhase,
    EnvironmentRequirement,
    Experiment,
    NamedCpuSet,
    ParameterSpec,
    Plan,
    Platform,
    Profile,
    ResolvedValue,
    RunResult,
    Sample,
    Scenario,
    ToolchainEvidence,
)
from arm64_probe.environment.models import (
    CapabilityObservation,
    ControllerRequest,
    ControllerState,
    DoctorReport,
    EnvironmentJournal,
    JournalFailure,
)
from arm64_probe.errors import ProbeError


def _mapping(items: tuple[tuple[str, Any], ...]) -> dict[str, Any]:
    return {key: to_data(value) for key, value in sorted(items)}


def to_data(value: object) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [to_data(item) for item in value]
    if isinstance(value, Capability):
        return {"id": value.id, "description": value.description}
    if isinstance(value, NamedCpuSet):
        return {"id": value.id, "cpus": to_data(value.cpus)}
    if isinstance(value, ParameterSpec):
        return {
            "id": value.id,
            "kind": value.kind,
            "choices": to_data(value.choices),
        }
    if isinstance(value, ResolvedValue):
        return {"value": to_data(value.value), "source": value.source}
    if isinstance(value, EnvironmentRequirement):
        return {
            "id": value.id,
            "capability_id": value.capability_id,
            "scope": value.scope,
            "values": _mapping(value.values),
            "mutation": value.mutation,
            "requires_privilege": value.requires_privilege,
        }
    if isinstance(value, Platform):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "description": value.description,
            "measurement_support": value.measurement_support,
            "capabilities": to_data(value.capabilities),
            "clusters": to_data(value.clusters),
            "core_groups": to_data(value.core_groups),
            "representative_cpus": _mapping(value.representative_cpus),
            "defaults": _mapping(value.defaults),
            "environment_defaults": _mapping(value.environment_defaults),
        }
    if isinstance(value, Scenario):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "cpu_mode": value.cpu_mode,
            "required_capabilities": to_data(value.required_capabilities),
            "parameters": to_data(value.parameters),
        }
    if isinstance(value, Experiment):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "scenarios": to_data(value.scenarios),
        }
    if isinstance(value, Profile):
        return {
            "id": value.id,
            "display_name": value.display_name,
            "selections": to_data(value.selections),
            "overrides": _mapping(value.overrides),
            "environment": _mapping(value.environment),
        }
    if isinstance(value, Case):
        return {
            "id": value.id,
            "scenario_id": value.scenario_id,
            "platform_id": value.platform_id,
            "status": value.status,
            "reason": value.reason,
            "cpu": value.cpu,
            "src_cpu": value.src_cpu,
            "dst_cpu": value.dst_cpu,
            "selectors": _mapping(value.selectors),
            "parameters": _mapping(value.parameters),
            "execution_requirements": to_data(value.execution_requirements),
        }
    if isinstance(value, EnvironmentPhase):
        return {
            "id": value.id,
            "case_ids": to_data(value.case_ids),
            "host_requirements": to_data(value.host_requirements),
        }
    if isinstance(value, Plan):
        return {
            "platform_id": value.platform_id,
            "profile_id": value.profile_id,
            "selections": to_data(value.selections),
            "cases": to_data(value.cases),
            "environment_phases": to_data(value.environment_phases),
            "skip_unavailable": value.skip_unavailable,
        }
    if isinstance(value, Sample):
        return {
            "run_id": value.run_id,
            "case_id": value.case_id,
            "sample_index": value.sample_index,
            "status": value.status,
            "metrics": _mapping(value.metrics),
        }
    if isinstance(value, RunResult):
        return {
            "run_id": value.run_id,
            "plan": to_data(value.plan),
            "samples": to_data(value.samples),
            "summary": _mapping(value.summary),
            "environment": _mapping(value.environment),
            "journal_transactions": to_data(value.journal_transactions),
            "schema_version": value.schema_version,
            "prior_run_id": value.prior_run_id,
            "resume_kind": value.resume_kind,
        }
    if isinstance(value, CapabilityObservation):
        return {
            "capability_id": value.capability_id,
            "status": value.status,
            "values": _mapping(value.values),
            "evidence": to_data(value.evidence),
            "hint": value.hint,
            "permits_formal_measurement": value.permits_formal_measurement,
        }
    if isinstance(value, ControllerRequest):
        return {
            "controller_id": value.controller_id,
            "values": _mapping(value.values),
        }
    if isinstance(value, ControllerState):
        return {
            "controller_id": value.controller_id,
            "status": value.status,
            "values": _mapping(value.values),
            "evidence": to_data(value.evidence),
        }
    if isinstance(value, JournalFailure):
        return {
            "stage": value.stage,
            "category": value.category,
            "message": value.message,
        }
    if isinstance(value, EnvironmentJournal):
        return {
            "schema_version": value.schema_version,
            "transaction_id": value.transaction_id,
            "repository_id": value.repository_id,
            "backend_id": value.backend_id,
            "platform_id": value.platform_id,
            "state": value.state,
            "created_at": value.created_at,
            "updated_at": value.updated_at,
            "requested": to_data(value.requested),
            "before": to_data(value.before),
            "applied": to_data(value.applied),
            "active_controller": value.active_controller,
            "effective": to_data(value.effective),
            "after": to_data(value.after),
            "restoration_status": value.restoration_status,
            "failures": to_data(value.failures),
        }
    if isinstance(value, DoctorReport):
        return {
            "backend_id": value.backend_id,
            "platform_id": value.platform_id,
            "observations": to_data(value.observations),
            "journals": to_data(value.journals),
        }
    if isinstance(value, ToolchainEvidence):
        return {
            "python_version": value.python_version,
            "uv_version": value.uv_version,
            "cc": value.cc,
            "host_os": value.host_os,
        }
    if isinstance(value, MetricStats):
        return {
            "metric_name": value.metric_name,
            "unit": value.unit,
            "sample_count": value.sample_count,
            "success_count": value.success_count,
            "error_count": value.error_count,
            "min_value": value.min_value,
            "max_value": value.max_value,
            "median": value.median,
            "mad": value.mad,
            "mean": value.mean,
            "stddev": value.stddev,
        }
    if isinstance(value, CaseAnalysis):
        return {
            "case_id": value.case_id,
            "scenario_id": value.scenario_id,
            "platform_id": value.platform_id,
            "status": value.status,
            "total_samples": value.total_samples,
            "ok_samples": value.ok_samples,
            "error_samples": value.error_samples,
            "metric_stats": _mapping(value.metric_stats),
            "anomalies": to_data(value.anomalies),
            "source_run_ids": to_data(value.source_run_ids),
        }
    if isinstance(value, CrossRunMetricDelta):
        return {
            "metric_name": value.metric_name,
            "unit": value.unit,
            "baseline_value": value.baseline_value,
            "current_value": value.current_value,
            "delta_pct": value.delta_pct,
        }
    if isinstance(value, CrossRunComparison):
        return {
            "case_id": value.case_id,
            "runs_compared": to_data(value.runs_compared),
            "classification": value.classification,
            "metric_deltas": _mapping(value.metric_deltas),
            "note": value.note,
        }
    if isinstance(value, AnalysisSummary):
        return {
            "analysis_id": value.analysis_id,
            "schema_version": value.schema_version,
            "source_runs": to_data(value.source_runs),
            "platform_id": value.platform_id,
            "repository_id": value.repository_id,
            "repository_commit": value.repository_commit,
            "dirty_tree": value.dirty_tree,
            "toolchain": to_data(value.toolchain),
            "case_analyses": to_data(value.case_analyses),
            "cross_run_comparisons": to_data(value.cross_run_comparisons),
            "anomalies": to_data(value.anomalies),
            "generated_at": value.generated_at,
        }
    if isinstance(value, FigureManifest):
        return {
            "figure_id": value.figure_id,
            "path": value.path,
            "caption": value.caption,
            "source_analysis_id": value.source_analysis_id,
            "regeneration_command": value.regeneration_command,
        }
    if isinstance(value, ReportManifest):
        return {
            "report_id": value.report_id,
            "report_path": value.report_path,
            "source_analysis_id": value.source_analysis_id,
            "figure_manifests": to_data(value.figure_manifests),
            "claim_count": value.claim_count,
            "section_count": value.section_count,
            "generated_at": value.generated_at,
            "regeneration_command": value.regeneration_command,
        }
    if isinstance(value, ImportedRecord):
        return {
            "source_path": value.source_path,
            "parser_version": value.parser_version,
            "format": value.format,
            "case_id": value.case_id,
            "platform_id": value.platform_id,
            "metrics": to_data(value.metrics),
            "loss_notes": to_data(value.loss_notes),
        }
    if isinstance(value, BaselineManifest):
        return {
            "baseline_id": value.baseline_id,
            "version": value.version,
            "source_run_ids": to_data(value.source_run_ids),
            "analysis_id": value.analysis_id,
            "report_id": value.report_id,
            "figure_ids": to_data(value.figure_ids),
            "commands": to_data(value.commands),
            "repository_commit": value.repository_commit,
            "dirty_tree": value.dirty_tree,
            "toolchain": to_data(value.toolchain),
            "promoted_at": value.promoted_at,
            "approved_by": value.approved_by,
        }
    if isinstance(value, ProbeError):
        return {
            "code": int(value.code),
            "category": value.category,
            "message": value.message,
            "context": _mapping(value.context),
            "hint": value.hint,
        }
    raise TypeError(f"unsupported public serialization type: {type(value).__name__}")


def _dict_to_metric_stats(data: dict) -> MetricStats:
    return MetricStats(
        metric_name=data["metric_name"],
        unit=data["unit"],
        sample_count=data["sample_count"],
        success_count=data["success_count"],
        error_count=data["error_count"],
        min_value=data.get("min_value"),
        max_value=data.get("max_value"),
        median=data.get("median"),
        mad=data.get("mad"),
        mean=data.get("mean"),
        stddev=data.get("stddev"),
    )


def _dict_to_cross_run_metric_delta(data: dict) -> CrossRunMetricDelta:
    return CrossRunMetricDelta(
        metric_name=data["metric_name"],
        unit=data["unit"],
        baseline_value=data.get("baseline_value"),
        current_value=data.get("current_value"),
        delta_pct=data.get("delta_pct"),
    )


def _dict_to_case_analysis(data: dict) -> CaseAnalysis:
    metric_stats = tuple(
        (k, _dict_to_metric_stats(v))
        for k, v in data.get("metric_stats", {}).items()
    )
    return CaseAnalysis(
        case_id=data["case_id"],
        scenario_id=data["scenario_id"],
        platform_id=data["platform_id"],
        status=data["status"],
        total_samples=data["total_samples"],
        ok_samples=data["ok_samples"],
        error_samples=data["error_samples"],
        metric_stats=metric_stats,
        anomalies=tuple(data.get("anomalies", ())),
        source_run_ids=tuple(data.get("source_run_ids", ())),
    )


def _dict_to_cross_run_comparison(data: dict) -> CrossRunComparison:
    metric_deltas = tuple(
        (k, _dict_to_cross_run_metric_delta(v))
        for k, v in data.get("metric_deltas", {}).items()
    )
    return CrossRunComparison(
        case_id=data["case_id"],
        runs_compared=tuple(data.get("runs_compared", ("", ""))),
        classification=data["classification"],
        metric_deltas=metric_deltas,
        note=data.get("note"),
    )


def _dict_to_analysis_summary(data: dict) -> AnalysisSummary:
    return AnalysisSummary(
        analysis_id=data["analysis_id"],
        schema_version=data["schema_version"],
        source_runs=tuple(data.get("source_runs", ())),
        platform_id=data["platform_id"],
        repository_id=data.get("repository_id", ""),
        repository_commit=data.get("repository_commit", ""),
        dirty_tree=data.get("dirty_tree", False),
        toolchain=tuple(tuple(p) for p in data.get("toolchain", ())),
        case_analyses=tuple(
            _dict_to_case_analysis(ca) for ca in data.get("case_analyses", ())
        ),
        cross_run_comparisons=tuple(
            _dict_to_cross_run_comparison(crc)
            for crc in data.get("cross_run_comparisons", ())
        ),
        anomalies=tuple(data.get("anomalies", ())),
        generated_at=data.get("generated_at", ""),
    )


def _dict_to_baseline_manifest(data: dict) -> BaselineManifest:
    return BaselineManifest(
        baseline_id=data["baseline_id"],
        version=data.get("version", ""),
        source_run_ids=tuple(data.get("source_run_ids", ())),
        analysis_id=data.get("analysis_id", ""),
        report_id=data.get("report_id"),
        figure_ids=tuple(data.get("figure_ids", ())),
        commands=tuple(data.get("commands", ())),
        repository_commit=data.get("repository_commit", ""),
        dirty_tree=data.get("dirty_tree", False),
        toolchain=tuple(tuple(p) for p in data.get("toolchain", ())),
        promoted_at=data.get("promoted_at", ""),
        approved_by=data.get("approved_by"),
    )


def _dict_to_figure_manifest(data: dict) -> FigureManifest:
    return FigureManifest(
        figure_id=data["figure_id"],
        path=data["path"],
        caption=data["caption"],
        source_analysis_id=data["source_analysis_id"],
        regeneration_command=data.get("regeneration_command", ""),
    )


def _dict_to_report_manifest(data: dict) -> ReportManifest:
    return ReportManifest(
        report_id=data["report_id"],
        report_path=data["report_path"],
        source_analysis_id=data["source_analysis_id"],
        figure_manifests=tuple(
            _dict_to_figure_manifest(fm) for fm in data.get("figure_manifests", ())
        ),
        claim_count=data.get("claim_count", 0),
        section_count=data.get("section_count", 0),
        generated_at=data.get("generated_at", ""),
        regeneration_command=data.get("regeneration_command", ""),
    )


def _dict_to_imported_record(data: dict) -> ImportedRecord:
    return ImportedRecord(
        source_path=data["source_path"],
        parser_version=data["parser_version"],
        format=data["format"],
        case_id=data.get("case_id"),
        platform_id=data.get("platform_id"),
        metrics=tuple(tuple(m) for m in data.get("metrics", ())),
        loss_notes=tuple(data.get("loss_notes", ())),
    )
