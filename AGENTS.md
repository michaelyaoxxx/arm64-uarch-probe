# Repository Guidelines

## Project Structure & Boundaries

The read-only Phase 1 control layer lives in `arm64_probe/`; declarative
platform, experiment, and profile facts live in `configs/`; public contracts
live in `schemas/`. Probe sources remain under `src/<probe>/`, with build
products in ignored `build/bin/`. Tests are split among `tests/unit/`,
`tests/contract/`, and `tests/integration/`. Design decisions live in
`docs/design/`.

Phase 2 added the read-only host backend, the read-only `probe doctor` flow,
the recoverable environment transaction coordinator, the durable managed
journal, the host-wide mutation lock, the signal-aware transaction scope,
and the public `probe restore` recovery command.

Phase 3 added normalized probe adapters (`ProbeAdapter` protocol with
`ChasePmuAdapter`, `EvictSlcAdapter`, `ChaseMigrateAdapter`), the unified
`Runner` that groups cases by environment phase and executes through
`EnvironmentCoordinator`, the atomic `RunResult` persistence layer
(`ResultStore` with schema v2), the `ResumeService` for re-executing
failed cases, and two new public commands: `probe run` and `probe resume`.

See `docs/superpowers/specs/2026-06-15-phase3-probes-runner-design.md` for
the detailed design, `docs/superpowers/plans/2026-06-15-phase3-probes-runner.md`
for the implementation plan, and `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md`
for the AC1–AC9 acceptance criteria.

See `docs/design/repository-layout.md` for the authoritative frozen,
transitional, and v1.0-owned path boundaries.

GB10 is the authoritative v1.0 measurement platform. Mac validates software
contracts and deterministic plans; Mac measurements are not GB10 baselines.
Versioned `runner/run_pmu*.sh` scripts and tracked `data/` files are frozen
legacy evidence. Do not modify them for new features.

## Python Toolchain

The repository is pinned to **CPython 3.13.13** and managed by `uv`.
`.python-version`, `pyproject.toml`, and `uv.lock` together fix the
interpreter, the workspace metadata, and the dependency resolution. Every
Python invocation in this repository goes through `uv run --no-sync` (the
`--no-sync` flag keeps the Makefile targets from racing a `uv lock`
during CI). After a fresh checkout run `make sync` to provision
`.venv/`. Do not invoke the system `python3`, Homebrew CPython, or the
Anaconda interpreter directly — `uv run` is the single source of truth,
and the contract tests in `tests/test_makefile_contract.py` enforce that
the Makefile targets and the legacy `python3` literals stay aligned.

## Build, Test & Development Commands

- `make help`: list supported repository targets.
- `make sync`: provision or refresh the local `.venv/` from `uv.lock`.
- `make clean-venv`: remove `.venv/` (re-run `make sync` to rebuild).
- `./probe list targets`: discover canonical experiments and scenarios.
- `./probe plan --platform gb10 --profile smoke -o json`: produce a read-only plan.
- `./probe doctor -o json`: read-only host inspection.
- `./probe run --platform gb10 --profile smoke --allow-mutation`: execute probes.
- `./probe resume --run <path-to-run-result>`: re-execute failed cases.
- `./probe restore --journal <path> --allow-mutation`: replay a managed journal.
- `make phase1-check`, `make phase2-check`, and `make phase3-check`: run all
  Python tests and legacy verification through the uv-managed interpreter.
- `make smoke`: run the minimal smoke workflow (plan + run).
- `make doctor PROBE_ARGS='-o json'`: thin wrapper around `probe doctor`.
- `make probe PROBE_ARGS='show gb10 -o json'`: convenience CLI wrapper.
- `make build`: build probes supported by the current host.
- `make check`: run Python contract tests and Bash syntax checks.

Run `make phase2-check`, `make check`, and `make build` before submitting
Phase 2 changes. Phase 1 and Phase 2 require no GB10. Do not begin
measurements until Phase 3 Gate 1 receives an explicit ready notice.

## Environment Mutation Safety

Public mutation requires both `--allow-mutation` and the caller's privilege.
The CLI never invokes `sudo`. The production Linux state root is fixed at
`/var/lib/arm64-uarch-probe`; only internal tests may inject a temporary root.
Recoverable transactions persist the journal before any host write, restore
controllers in reverse order, restore a recorded `active_controller` first,
and convert `SIGINT`/`SIGTERM` into automatic restoration. Unhandleable
process termination leaves a durable journal that the user can replay with
`probe restore`.

## Coding Style & Testing

Use four-space indentation in C and Python. Follow existing C brace placement,
keep compiler warnings enabled, and use `snake_case` for Python functions and
tests. Prefer immutable `dataclass(frozen=True)` records, tuple-based public
models, the Python standard library, and declarative platform facts over
platform-name branches. Name tests `test_<area>.py`, use behavior-focused
`unittest` cases, and add a failing test before changing behavior.

## Commits & Pull Requests

Use focused imperative commit messages, such as `Add recoverable environment
transaction coordinator`. Pull requests must state scope, verification
commands, whether GB10 evidence is required, and whether environment
restoration applies. Never commit transient `build/` output. Keep reviewed
evidence under `results/baselines/<version>/` and publication figures under
`docs/assets/<version>/`.
