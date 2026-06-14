import argparse
import sys
from collections.abc import Sequence

from arm64_probe.errors import ExitCode, ProbeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="probe",
        description="Discover and plan arm64-uarch-probe experiments.",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list", help="list registered objects")
    subparsers.add_parser("show", help="show one registered object")
    subparsers.add_parser("plan", help="build a side-effect-free execution plan")
    return parser


def render_error(error: ProbeError) -> str:
    lines = [f"error: {error.message}"]
    lines.extend(f"{key}: {value}" for key, value in error.context)
    if error.hint:
        lines.append(f"hint: {error.hint}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return ExitCode.SUCCESS

    error = ProbeError(
        ExitCode.PLANNING,
        "planning",
        f"{args.command} is not connected yet",
        hint="use `probe --help` to inspect the Phase 1 interface",
    )
    print(render_error(error), file=sys.stderr)
    return error.code
