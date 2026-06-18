import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from arm64_probe.backends.select import select_backend
from arm64_probe.cli.parser import build_parser, get_command_parser
from arm64_probe.cli.render import (
    render_analyze,
    render_doctor,
    render_error,
    render_list,
    render_plan,
    render_restore,
    render_resume,
    render_run,
    render_show,
)
from arm64_probe.diagnostics.doctor import Doctor
from arm64_probe.environment.constants import REPOSITORY_ID, STATE_ROOT
from arm64_probe.environment.journal import JournalStore
from arm64_probe.environment.recovery import EnvironmentRecovery
from arm64_probe.errors import ExitCode, ProbeError
from arm64_probe.execution.runner import Runner
from arm64_probe.planning.planner import Planner
from arm64_probe.planning.request import PlanRequest
from arm64_probe.registry.catalog import Catalog


ROOT = Path(__file__).resolve().parents[2]


def _resolve_platform(platform_id: str) -> str:
    if platform_id != "auto":
        return platform_id
    if platform.system() == "Darwin" and platform.machine() in {"arm64", "aarch64"}:
        return "m4"
    raise ProbeError(
        ExitCode.CAPABILITY,
        "platform",
        "auto platform resolution supports Darwin ARM64 only in Phase 1",
        hint="pass --platform with an explicit registered platform ID",
    )


def _find_registered(catalog: Catalog, item_id: str) -> object:
    collections = (
        ("capability", catalog.capabilities()),
        ("platform", catalog.platforms()),
        ("experiment", catalog.experiments()),
        ("scenario", catalog.scenarios()),
        ("profile", catalog.profiles()),
    )
    matches = tuple(
        (kind, item)
        for kind, items in collections
        for item in items
        if item.id == item_id
    )
    if not matches:
        raise ProbeError(
            ExitCode.CONFIG,
            "configuration",
            f"unknown registered object: {item_id}",
            hint="use `probe list` or a category-specific `probe list` command",
        )
    if len(matches) > 1:
        alternatives = ", ".join(f"{kind}:{item.id}" for kind, item in matches)
        raise ProbeError(
            ExitCode.CONFIG,
            "configuration",
            f"ambiguous registered object: {item_id}",
            context=(("alternatives", alternatives),),
            hint="use a qualified alternative",
        )
    return matches[0][1]


def _plan_request(args) -> PlanRequest:
    overrides = tuple(
        (key, value)
        for key, value in (
            ("samples", args.samples),
            ("working-set", args.working_set),
            ("page-policy", args.page_policy),
        )
        if value is not None
    )
    return PlanRequest(
        platform_id=_resolve_platform(args.platform),
        profile_id=args.profile,
        selections=tuple(args.select),
        cluster=args.cluster,
        core_group=args.core_group,
        cpu=args.cpu,
        src_cpu=args.src_cpu,
        dst_cpu=args.dst_cpu,
        overrides=overrides,
        skip_unavailable=args.skip_unavailable,
    )


def _run_analyze(args) -> tuple:
    """Run the probe analyze command.

    Loads RunResult files, computes per-case MetricStats via StatisticsEngine,
    persists AnalysisSummary atomically via AnalysisStore.

    Returns:
        Tuple of (AnalysisSummary | None, Path | None).
        On error summary is None indicating exit code 16.
    """
    import datetime
    import uuid
    from pathlib import Path as PathCls

    from arm64_probe.analysis.ingestion import ResultIngester
    from arm64_probe.analysis.statistics import StatisticsEngine
    from arm64_probe.analysis.store import AnalysisStore
    from arm64_probe.execution.result_store import ResultStore

    run_paths = tuple(PathCls(p) for p in args.runs)
    output_dir = PathCls(args.output_dir)

    # ResultStore.read(path) reads from an arbitrary path; results_dir is
    # unused for reads, so pass any existing directory to satisfy the ctor.
    store = ResultStore(results_dir=output_dir)
    ingester = ResultIngester(store)
    try:
        results = ingester.ingest(run_paths)
    except (FileNotFoundError, ValueError, KeyError, OSError) as e:
        print(f"analyze error: {e}", file=sys.stderr)
        return None, None

    # Use the first result's summary for top-level metadata.
    summary_dict = dict(results[0].summary)
    plat_id = summary_dict.get("platform_id", "unknown")
    repo_id = summary_dict.get("repository_id", "unknown")
    commit = summary_dict.get("repository_commit", "unknown")
    dirty = bool(summary_dict.get("dirty_tree", False))

    # Group samples by case_id across all run results.
    all_samples_by_case: dict[str, list] = {}
    for r in results:
        for s in r.samples:
            all_samples_by_case.setdefault(s.case_id, []).append(s)

    # Build a lookup: case_id -> scenario_id by scanning all plans.
    scenario_by_case: dict[str, str] = {}
    for r in results:
        for c in r.plan.cases:
            scenario_by_case.setdefault(c.id, c.scenario_id)

    # Compute per-case analysis.
    case_analyses = []
    for case_id in sorted(all_samples_by_case):
        samples = tuple(all_samples_by_case[case_id])
        ca = StatisticsEngine.compute_case_analysis(
            case_id=case_id,
            samples=samples,
            scenario_id=scenario_by_case.get(case_id, "unknown"),
            platform_id=plat_id,
        )
        case_analyses.append(ca)

    now = datetime.datetime.now(datetime.timezone.utc)
    analysis_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]

    from arm64_probe.analysis.models import AnalysisSummary

    analysis = AnalysisSummary(
        analysis_id=analysis_id,
        schema_version=1,
        source_runs=tuple(r.run_id for r in results),
        platform_id=plat_id,
        repository_id=repo_id,
        repository_commit=commit,
        dirty_tree=dirty,
        toolchain=(("python", "3.13.13"),),
        case_analyses=tuple(case_analyses),
        cross_run_comparisons=(),
        anomalies=(),
        generated_at=now.isoformat(),
    )

    analysis_store = AnalysisStore(analysis_dir=output_dir)
    out_path = analysis_store.write_analysis(analysis)
    return analysis, out_path


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(arguments)
    if args.command is None:
        parser.print_help()
        return ExitCode.SUCCESS
    if args.command == "help":
        get_command_parser(parser, args.topic).print_help()
        return ExitCode.SUCCESS

    output = args.output
    try:
        catalog = Catalog.load(ROOT)
        if args.command == "list":
            result = render_list(catalog, args.category, args.output)
        elif args.command == "show":
            result = render_show(_find_registered(catalog, args.id), args.output)
        elif args.command == "plan":
            plan = Planner(catalog).plan(_plan_request(args))
            result = render_plan(plan, args.output)
        elif args.command == "restore":
            journal_path = Path(args.journal)
            transaction_id = journal_path.stem
            store = JournalStore(STATE_ROOT, repository_id=REPOSITORY_ID)
            recovery = EnvironmentRecovery(
                journal_factory=lambda: (STATE_ROOT, store, 0, REPOSITORY_ID)
            )
            final = recovery.restore(
                transaction_id,
                select_backend(),
                allow_mutation=args.allow_mutation,
            )
            result = render_restore(final, args.output)
        elif args.command == "run":
            # Create plan
            plan = Planner(catalog).plan(_plan_request(args))

            # Determine output directory
            output_dir = (
                Path(args.output_dir) if args.output_dir else ROOT / "results" / "runs"
            )
            output_dir.mkdir(parents=True, exist_ok=True)

            # Create runner
            from arm64_probe.execution.adapters import (
                ChasePmuAdapter,
                EvictSlcAdapter,
                ChaseMigrateAdapter,
            )
            from arm64_probe.execution.result_store import ResultStore

            adapters = {
                "chase_pmu": ChasePmuAdapter(),
                "evict_slc": EvictSlcAdapter(),
                "chase_migrate": ChaseMigrateAdapter(),
            }

            result_store = ResultStore(output_dir)

            # Create runner with required dependencies
            runner = Runner(
                coordinator=None,
                result_store=result_store,
                adapters=adapters,
            )

            # Execute run
            run_result = runner.run(
                plan,
                allow_mutation=args.allow_mutation,
            )

            # Render result
            result = render_run(run_result, args.output)
        elif args.command == "resume":
            from arm64_probe.execution.result_store import ResultStore
            from arm64_probe.execution.resume import ResumeService

            prior_path = Path(args.run)

            # Determine output directory
            output_dir = (
                Path(args.output_dir) if args.output_dir else ROOT / "results" / "runs"
            )
            output_dir.mkdir(parents=True, exist_ok=True)

            # Read prior RunResult
            store = ResultStore(output_dir)
            prior = store.read(prior_path)

            # Reconstruct the plan from the prior RunResult
            plan = prior.plan

            # Create resume service and execute
            service = ResumeService(store)
            resumed = service.resume(
                prior,
                plan=plan,
                platform_id=plan.platform_id,
                allow_mutation=args.allow_mutation,
                output_dir=output_dir,
            )

            result = render_resume(resumed, args.output)
        elif args.command == "analyze":
            summary, path = _run_analyze(args)
            if summary is None:
                return ExitCode.RUN_RESULT
            result = render_analyze(summary, path, args.output)
        else:
            platform_id = (
                catalog.get_platform(args.platform).id
                if args.platform is not None
                else None
            )
            report = Doctor(
                select_backend(),
                JournalStore(STATE_ROOT, repository_id=REPOSITORY_ID),
            ).inspect(platform_id)
            result = render_doctor(report, args.output)
        print(result, end="")
        return ExitCode.SUCCESS
    except ProbeError as error:
        rendered = render_error(error, output)
        print(rendered, end="", file=sys.stdout if output == "json" else sys.stderr)
        return error.code
