import re
from collections.abc import Sequence


ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", re.ASCII)
SCENARIO_RE = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*$",
    re.ASCII,
)
CAPABILITY_RE = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)*$",
    re.ASCII,
)


def validate_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise ValueError(f"invalid canonical id: {value!r}")
    return value


def validate_scenario_id(value: str) -> str:
    if not SCENARIO_RE.fullmatch(value):
        raise ValueError(f"invalid canonical scenario id: {value!r}")
    return value


def validate_capability_id(value: str) -> str:
    if not CAPABILITY_RE.fullmatch(value):
        raise ValueError(f"invalid canonical capability id: {value!r}")
    return value


def build_case_id(
    scenario_id: str,
    platform_id: str,
    dimensions: Sequence[str],
) -> str:
    validate_scenario_id(scenario_id)
    validate_id(platform_id)
    if not dimensions:
        raise ValueError("case id requires at least one dimension")
    canonical_dimensions = tuple(validate_id(value) for value in dimensions)
    return f"{scenario_id}@{platform_id}." + ".".join(canonical_dimensions)
