import argparse


OUTPUT_CHOICES = ("table", "json")
COMMANDS = ("list", "show", "plan")


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
    return parser


def get_command_parser(
    parser: argparse.ArgumentParser,
    command: str,
) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[command]
    raise ValueError(f"parser has no subcommands: {command}")
