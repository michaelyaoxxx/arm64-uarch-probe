# Repository Guidelines

## Project Structure & Boundaries

The read-only Phase 1 control layer lives in `arm64_probe/`; declarative
platform, experiment, and profile facts live in `configs/`; public contracts
live in `schemas/`. Probe sources remain under `src/<probe>/`, with build
products in ignored `build/bin/`. Tests are split among `tests/unit/`,
`tests/contract/`, and `tests/integration/`. Design decisions live in
`docs/design/`.

See `docs/design/repository-layout.md` for the authoritative frozen,
transitional, and v1.0-owned path boundaries.

GB10 is the authoritative v1.0 measurement platform. Mac validates software
contracts and deterministic plans; Mac measurements are not GB10 baselines.
Versioned `runner/run_pmu*.sh` scripts and tracked `data/` files are frozen
legacy evidence. Do not modify them for new features.

## Build, Test & Development Commands

- `make help`: list supported repository targets.
- `./probe list targets`: discover canonical experiments and scenarios.
- `./probe plan --platform gb10 --profile smoke -o json`: produce a read-only plan.
- `make phase1-check`: run all Python tests and legacy verification.
- `make probe PROBE_ARGS='show gb10 -o json'`: convenience CLI wrapper.
- `make build`: build probes supported by the current host.
- `make check`: run Python contract tests and Bash syntax checks.

Run `make phase1-check`, `make check`, and `make build` before submitting Phase
1 changes. Phase 1 and Phase 2 require no GB10. Do not begin measurements until
Phase 3 Gate 1 receives an explicit ready notice.

## Coding Style & Testing

Use four-space indentation in C and Python. Follow existing C brace placement,
keep compiler warnings enabled, and use `snake_case` for Python functions and
tests. Prefer immutable `dataclass(frozen=True)` records, tuple-based public
models, the Python standard library, and declarative platform facts over
platform-name branches. Name tests `test_<area>.py`, use behavior-focused
`unittest` cases, and add a failing test before changing behavior.

## Commits & Pull Requests

Use focused imperative commit messages, such as `Implement read-only Phase 1
CLI`. Pull requests must state scope, verification commands, whether GB10
evidence is required, and whether environment restoration applies. Never
commit transient `build/` output. Keep reviewed evidence under
`results/baselines/<version>/` and publication figures under
`docs/assets/<version>/`.
