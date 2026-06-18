import argparse


OUTPUT_CHOICES = ("table", "json")
COMMANDS = ("list", "show", "plan", "doctor", "restore", "run", "resume", "analyze")


def _add_output_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-o",
        "--output",
        choices=OUTPUT_CHOICES,
        default="table",
        help="select human-readable table or machine-readable JSON output",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="probe",
        description="Discover and plan arm64-uarch-probe experiments.",
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command")

    help_parser = subparsers.add_parser(
        "help",
        help="show help for one command",
        allow_abbrev=False,
    )
    help_parser.add_argument("topic", choices=COMMANDS)

    list_parser = subparsers.add_parser(
        "list",
        help="list registered objects",
        allow_abbrev=False,
    )
    list_parser.add_argument(
        "category",
        nargs="?",
        choices=("targets", "profiles", "platforms", "capabilities"),
        default="targets",
    )
    _add_output_option(list_parser)

    show_parser = subparsers.add_parser(
        "show",
        help="show one registered object",
        allow_abbrev=False,
    )
    show_parser.add_argument("id", help="registered object ID")
    _add_output_option(show_parser)

    plan_parser = subparsers.add_parser(
        "plan",
        help="build a side-effect-free execution plan",
        allow_abbrev=False,
    )
    plan_parser.add_argument(
        "--platform",
        default="auto",
        help="platform ID; auto supports Darwin ARM64 only in Phase 1",
    )
    plan_parser.add_argument("--profile", help="profile ID")
    plan_parser.add_argument(
        "--select",
        action="append",
        default=[],
        help="experiment or scenario ID; repeat to combine selections",
    )
    plan_parser.add_argument("--cluster", help="semantic cluster ID")
    plan_parser.add_argument("--core-group", help="semantic core-group ID")
    plan_parser.add_argument("--cpu", type=int, help="explicit single-case CPU")
    plan_parser.add_argument("--src-cpu", type=int, help="explicit migration source CPU")
    plan_parser.add_argument(
        "--dst-cpu",
        type=int,
        help="explicit migration destination CPU",
    )
    plan_parser.add_argument("--samples", type=int, help="sample-count override")
    plan_parser.add_argument("--working-set", help="working-set size override")
    plan_parser.add_argument(
        "--page-policy",
        choices=("default", "hugepage"),
        help="page-policy override",
    )
    plan_parser.add_argument(
        "--skip-unavailable",
        action="store_true",
        help="record that unavailable cases should be skipped at execution time",
    )
    _add_output_option(plan_parser)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="inspect the live host without changing it",
        allow_abbrev=False,
    )
    doctor_parser.add_argument(
        "--platform",
        help="optional registered platform context label",
    )
    _add_output_option(doctor_parser)

    restore_parser = subparsers.add_parser(
        "restore",
        help="replay a managed environment journal to restore host state",
        allow_abbrev=False,
    )
    restore_parser.add_argument(
        "--journal",
        required=True,
        help="path to a managed journal under STATE_ROOT/journals/",
    )
    restore_parser.add_argument(
        "--allow-mutation",
        action="store_true",
        help="acknowledge that this command will mutate host state",
    )
    _add_output_option(restore_parser)

    run_parser = subparsers.add_parser(
        "run",
        help="execute a measurement plan and collect results",
        description="Execute a measurement plan, collect results, and store them atomically.",
        allow_abbrev=False,
    )
    run_parser.add_argument(
        "--platform",
        default="auto",
        help="platform ID; auto supports Darwin ARM64 only in Phase 1",
    )
    run_parser.add_argument("--profile", help="profile ID")
    run_parser.add_argument(
        "--select",
        action="append",
        default=[],
        help="experiment or scenario ID; repeat to combine selections",
    )
    run_parser.add_argument("--cluster", help="semantic cluster ID")
    run_parser.add_argument("--core-group", help="semantic core-group ID")
    run_parser.add_argument("--cpu", type=int, help="explicit single-case CPU")
    run_parser.add_argument("--src-cpu", type=int, help="explicit migration source CPU")
    run_parser.add_argument(
        "--dst-cpu",
        type=int,
        help="explicit migration destination CPU",
    )
    run_parser.add_argument("--samples", type=int, help="sample-count override")
    run_parser.add_argument("--working-set", help="working-set size override")
    run_parser.add_argument(
        "--page-policy",
        choices=("default", "hugepage"),
        help="page-policy override",
    )
    run_parser.add_argument(
        "--skip-unavailable",
        action="store_true",
        help="record that unavailable cases should be skipped at execution time",
    )
    run_parser.add_argument(
        "--allow-mutation",
        action="store_true",
        help="acknowledge that this command will mutate host state",
    )
    run_parser.add_argument(
        "--output-dir",
        help="directory to write run results (default: results/runs/)",
    )
    _add_output_option(run_parser)

    resume_parser = subparsers.add_parser(
        "resume",
        help="resume a prior run, re-executing only failed cases",
        description="Read a prior RunResult, and re-execute only failed or missing cases.",
        allow_abbrev=False,
    )
    resume_parser.add_argument(
        "--run",
        required=True,
        help="path to a prior RunResult JSON file",
    )
    resume_parser.add_argument(
        "--output-dir",
        help="directory to write run results (default: results/runs/)",
    )
    resume_parser.add_argument(
        "--allow-mutation",
        action="store_true",
        help="acknowledge that this command will mutate host state",
    )
    _add_output_option(resume_parser)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="analyze run results and produce analysis summary",
        description="Load RunResult files, compute per-case statistics, and persist an AnalysisSummary.",
        allow_abbrev=False,
    )
    analyze_parser.add_argument(
        "--run",
        required=True,
        action="append",
        dest="runs",
        metavar="PATH",
        help="RunResult JSON file (repeatable)",
    )
    analyze_parser.add_argument(
        "--baseline",
        default=None,
        metavar="PATH",
        help="prior analysis for cross-run comparison (Phase 5)",
    )
    analyze_parser.add_argument(
        "--output-dir",
        default="results/analysis/",
        metavar="DIR",
        help="output directory for analysis artifacts",
    )
    _add_output_option(analyze_parser)

    return parser


def get_command_parser(
    parser: argparse.ArgumentParser,
    command: str,
) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[command]
    raise ValueError(f"parser has no subcommands: {command}")
