import platform
import sys
from collections.abc import Sequence
from pathlib import Path

from arm64_probe.backends.select import select_backend
from arm64_probe.cli.parser import build_parser, get_command_parser
from arm64_probe.cli.render import (
    render_doctor,
    render_error,
    render_list,
    render_plan,
    render_show,
)
from arm64_probe.diagnostics.doctor import Doctor
from arm64_probe.environment.constants import REPOSITORY_ID, STATE_ROOT
from arm64_probe.environment.journal import JournalStore
from arm64_probe.errors import ExitCode, ProbeError
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
