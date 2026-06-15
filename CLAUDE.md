# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

`arm64-uarch-probe` is a reproducible microarchitecture research baseline for the NVIDIA GB10 ARM64 SoC (A725 + X925 cores). Mac and Linux ARM64 environments validate engineering behavior; **GB10 is the only authoritative measurement platform** and is first required at Phase 3 Gate 1.

Phase 2 is now complete on the `codex/phase2-backends-environment-design` branch. The control layer has an immutable domain model, declarative registries, public JSON schemas, deterministic planning, a read-only `probe doctor` flow, capability-driven Linux controllers (cpufreq, hugepage, THP), a recoverable environment transaction coordinator with a host-wide mutation lock, a durable managed journal, signal-aware restoration, and an explicit `probe restore` recovery command. **No probe is executed in Phase 1/2.**

When picking up Phase 3, read the active handoff in `docs/superpowers/handoffs/` for current scope and Task ordering.

## Common Commands

```sh
make help                            # list all targets
make phase2-check                    # Python tests + legacy manifest verification (Phase 2 gate)
make phase1-check                    # equivalent to phase2-check today
make check                           # Python contract tests + bash syntax checks
make build                           # build probes supported on the current host
make build-linux                     # force all Linux probes; rejects non-Linux
make show-targets                    # source→binary mapping with platform support
make doctor PROBE_ARGS='-o json'     # thin wrapper around `./probe doctor`
make clean                           # remove build/ (safety-checked)

./probe --help                       # CLI help
./probe help restore                 # restore subcommand help
./probe list targets                 # discover experiments/scenarios
./probe list platforms               # registered platforms
./probe show <id> -o json            # inspect a single registered object
./probe plan --platform gb10 --profile smoke -o json
./probe doctor -o json               # read-only host inspection
./probe restore --journal <path> --allow-mutation   # replay a managed journal
make probe PROBE_ARGS='show gb10 -o json'    # convenience wrapper
python3 -m arm64_probe help plan     # module entry point (debugging)
```

To run a single test file or test case:

```sh
python3 -m unittest tests.unit.test_domain_models -v
python3 -m unittest tests.unit.test_planner_selection.PlannerSelectionTests.test_expand_experiment -v
python3 -m unittest tests.contract.test_phase2_acceptance -v
```

## Repository Layout

| Path | Purpose |
|---|---|
| `arm64_probe/cli/` | argparse wiring + renderers (`main.py`, `parser.py`, `render.py`) |
| `arm64_probe/domain/` | Frozen `dataclass` domain models + ID validators |
| `arm64_probe/registry/` | `Catalog` (loads + validates `configs/`) and per-file JSON validators |
| `arm64_probe/planning/` | `Planner`, `PlanRequest`, semantic CPU selection orchestration |
| `arm64_probe/platforms/` | `ConfiguredPlatformResolver` — turns semantic selectors into concrete CPUs |
| `arm64_probe/backends/` | `HostBackend` protocol; `linux_arm64/` (read-only inspector + cpufreq/hugepage/THP controllers) and `darwin_arm64/` (synthetic, contract-only) |
| `arm64_probe/environment/` | `MutationLock` (host-wide fcntl), `JournalStore` (atomic persistent journals), `EnvironmentJournal`/`ControllerRequest`/`ControllerState` models, `CommonSignalScope`, `EnvironmentCoordinator` (recoverable transactions), `EnvironmentRecovery` (managed journal replay), `requests_from_requirements` |
| `arm64_probe/diagnostics/` | `Doctor` — read-only host inspection report |
| `arm64_probe/serialization/` | `load_json` / `dump_json` + dataclass↔dict adapter |
| `configs/` | Declarative platform (`platforms/*.json`), experiment (`experiments/*.json`), profile (`profiles/*.json`), capability facts |
| `schemas/` | Public JSON schemas (capability, case, plan, run-result, sample, environment, …) |
| `src/<probe>/` | C single-measurement probes (`chase_pmu_v2.7.3.c`, `evict_slc_v1.2.c`, `chase_migrate_v1.0.c`) — build outputs go to ignored `build/bin/` |
| `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/fixtures/`, `tests/support/` | Test-suite ownership boundaries. `host_fixture.py` builds a temp `PathHostFilesystem`; `fake_controllers.py` provides `FakeController`/`FakeBackend`. |
| `runner/run_pmu*.sh`, `data/` | **Frozen** legacy evidence. `make legacy-check` enforces integrity via `legacy/manifest.json`. Do not modify for new features. |
| `docs/design/` | `repository-contract.md`, `repository-layout.md`, `cli-contract.md` — authoritative contracts |
| `docs/superpowers/specs/`, `docs/superpowers/plans/`, `docs/superpowers/handoffs/` | Phase design specs, implementation plans, and active handoffs (read in that order when picking up a phase) |

## Architecture

### Layered design (Phase 2 surface)

```
CLI (arm64_probe/cli/)         arg parser + renderers
    │
    ├── Catalog (arm64_probe/registry/)        validates & loads configs/*.json
    │
    ├── Planner (arm64_probe/planning/)        deterministic, side-effect-free Plan
    │       └── ConfiguredPlatformResolver     semantic → concrete CPU
    │
    ├── Doctor (arm64_probe/diagnostics/)      read-only host report
    │       └── HostBackend (backends/)        capability-driven
    │              ├── linux_arm64             inspector + cpufreq/hugepage/THP controllers
    │              └── darwin_arm64            contract-only, supports smoke contract
    │
    └── EnvironmentCoordinator / EnvironmentRecovery / probe restore
            ├── MutationLock (host-wide fcntl)
            ├── JournalStore (atomic, owner-checked)
            ├── CommonSignalScope (main-thread SIGINT/SIGTERM only)
            └── ControllerRequest → CONTROLLER_ORDER ordering
```

### Domain invariants

- **All domain models are `@dataclass(frozen=True)`** with sorted-unique `JsonScalar` mappings. Mutation is impossible; "updating" means producing a new instance. Tuples are used for public models.
- **IDs are kebab-case** validated by `arm64_probe.domain.ids`: simple `id`, dot-separated `scenario_id`, capability id may be dotted.
- **Case IDs** are `build_case_id(scenario, platform, dimensions)` → `<scenario>@<platform>.<dim>.<dim>...`.
- **Capabilities are the universal currency**: `Platform.capabilities`, `Scenario.required_capabilities`, and `EnvironmentRequirement.capability_id` must all reference the canonical set in `configs/capabilities.json`. **No platform-name branches** (gb10/m4/…) appear in planning, controllers, or coordinator logic.
- **CPU modes** in scenarios: `single`, `pair-same-core`, `pair-same-cluster`, `pair-cross-cluster`.
- **Parameter kinds**: `integer` (positive int, no bool), `size` (`<N>KiB|MiB|GiB`), `string` (with optional `choices`).

### Planning flow

1. `Catalog.load(root)` validates `configs/` cross-references (every platform/scenario/profile/experiment reference must resolve).
2. `Planner.plan(PlanRequest)` resolves `--platform`/`--profile`/`--select`/`--cluster`/`--core-group`/`--cpu`/`--src-cpu`/`--dst-cpu`/parameter overrides into a `Plan` of `Case` objects.
3. Each `Case` carries `execution_requirements` (cpu-affinity, page-policy); the parent `Plan` carries `environment_phases` — host-scoped `EnvironmentRequirement` groupings with the `mutation` flag.
4. Scenarios expand to deduplicated scenario IDs; profile selections + CLI `--select` form a deterministic union.

### Environment transaction model

- `EnvironmentRequirement` is `host`-scoped (host-wide mutation) or `case`-scoped (per-case, not yet mutating).
- `requests_from_requirements` orders requests by `CONTROLLER_ORDER` (`linux.cpufreq`, `linux.hugepage`, `linux.transparent-hugepage`) in `arm64_probe/environment/constants.py`.
- `JournalStore` (root `/var/lib/arm64-uarch-probe/journals/`) writes `<32-hex-txid>.json` atomically via `O_NOFOLLOW | O_EXCL` + `fsync` + `os.replace` + directory fsync. State transitions are enforced via `TRANSITIONS`. A `restored` journal is immutable.
- `MutationLock` (host-wide `fcntl.flock` on `/var/lib/arm64-uarch-probe/mutation.lock`) gates any mutating command across checkouts; requires `os.geteuid() == 0` and validates the root, lock file, and opened fd are owned by the required uid and not symlinks. Always pair with a custom `_LockContext` — Python 3.14's frozen `ProbeError` cannot survive a `@contextmanager` re-throw that sets `__traceback__`.
- `MutationController` Protocol: `inspect → validate_request → apply → verify → restore → verify_restored`. Restore is reverse of apply; `active_controller` is restored first even after a mid-apply crash.
- `EnvironmentCoordinator.execute(backend, platform_id, requests, work, allow_mutation)`:
  - `requests=()` runs `work` without acquiring the lock and returns a `restored` journal with `restoration_status="not-applicable"`.
  - Otherwise: acquire lock, rediscover unfinished journals, inspect+validate+preflight, create journal, run each controller (`set active → apply → mark applied → verify`), run `work` inside `CommonSignalScope`, restore in reverse (`active_controller` first, then completed controllers), persist final journal, release lock.
  - `apply` failure → exit code `12` (restoration succeeded), original failure recorded. `restore` failure → exit code `13`, persisted as `restore-failed`. Lock contention or unfinished journal → `14`. Missing `--allow-mutation` → `11` (before lock).
- `EnvironmentRecovery.restore(transaction_id, backend, allow_mutation)`:
  - Lexical/symlink-safe managed-path preflight, then lock, reread, authoritative validation, restore in reverse, persist `restored`. Cross-checkout recovery uses `repository_id` not path. Backend mismatch, repository mismatch, symlink swap, journal change while waiting, controller unavailability, and unsafe paths are all rejected before host writes. Already-restored journal is a successful no-op.
- **Public mutation surface requires `--allow-mutation` AND caller privilege; CLI never invokes `sudo`.**

### CLI surface

Entry points: `./probe` and `python3 -m arm64_probe` (identical). Commands: `list`, `show`, `plan`, `help`, `doctor`, `restore`. `restore` accepts `--journal <path> --allow-mutation` and **does not** add target settings, `--state-root`, automatic `sudo`, or interactive prompts. Only `-h`/`--help` and `-o`/`--output` are short options.

### Exit codes (authoritative: `arm64_probe/errors.py`)

`0` success · `2` usage · `3` config · `4` capability · `5` planning · `10` host inspection · `11` mutation auth · `12` apply failure (restoration succeeded) · `13` restore failure · `14` active lock / unfinished journal.

## Authoritative Contracts (always read first)

- `docs/design/repository-contract.md` — collaboration, result retention, GB10 handoff, host mutation safety
- `docs/design/repository-layout.md` — frozen vs transitional vs v1.0 path ownership
- `docs/design/cli-contract.md` — entry points, command surface, exit codes, side-effect boundary
- `docs/superpowers/specs/2026-06-14-phase2-backends-environment-design.md` — Phase 2 design
- `docs/superpowers/plans/2026-06-14-phase2-backends-environment.md` — Phase 2 implementation plan (Tasks 1–13)
- `docs/superpowers/handoffs/<date>-<phase>-<topic>.md` — active handoff for the next batch of work

## Coding Style & Testing

- Four-space indentation in C and Python; follow existing C brace placement; keep compiler warnings enabled (`-Wall -Wextra`).
- Python: `snake_case` functions and tests; immutable `dataclass(frozen=True)` records; tuple-based public models; Python standard library only; **declarative platform facts over platform-name branches**; tests named `test_<area>.py`.
- Use `unittest` (not pytest). Add a failing test before changing behavior (TDD).
- Run `make phase2-check`, `make check`, `make build`, and `git diff --check` before submitting changes.
- For unit tests needing a host filesystem, use `tests/support/host_fixture.py` (`HostFixture` builds a temp `PathHostFilesystem` and refuses symlink/path-escape writes). For transactions/recovery, use `tests/support/fake_controllers.py` (`FakeController`, `FakeBackend(controllers=..., backend_id=...)`). Never touch the real host in unit tests.
- **Python 3.14 gotcha**: a `with lock:` block that catches and re-raises a `ProbeError` cannot survive — `contextlib.contextmanager.__exit__` calls `gen.throw(value)` which sets `__traceback__` on the frozen `ProbeError` and raises `FrozenInstanceError`. Use a custom context-manager class (see `_LockContext` in `coordinator.py` / `recovery.py`) that delegates `__exit__` directly to the lock's `__exit__` instead of using a generator.

## Commits, Branches, and PRs

- Imperative, focused commit messages (e.g. `Add recoverable environment transaction coordinator`).
- Branch is `codex/phase2-backends-environment-design`; do not develop on `main`.
- Each phase Task lands as a **separate** commit; do not squash them.
- Do not modify frozen legacy paths (`runner/run_pmu*.sh`, `data/`, transitional `analysis/`, `baseline/`, `runner/cache_info_*.sh`) or historical `build/` output.
- PRs must state scope, verification commands, GB10 evidence requirement, and environment restoration status (see `.github/pull_request_template.md`).
- Reviewed evidence lives under `results/baselines/<version>/`; publication figures under `docs/assets/<version>/`. `results/runs/` is git-ignored.
- Do not merge to `main`, push, or open a PR without an explicit user request.

## Phase Boundaries (don't cross)

- Phase 1 and Phase 2 require **no GB10**; do not execute C probes or modify the real Mac/GB10 environment.
- Do not modify CPU online state, NUMA hugepage pools, PMU permissions, system load, frozen legacy runners, historical `data/`, or transitional paths.
- Public mutation requires both `--allow-mutation` and caller privilege; the CLI never calls `sudo`.
- `STATE_ROOT = /var/lib/arm64-uarch-probe` is fixed; only internal tests may inject a temporary root.
- No new public `environment-apply` command, no public `--state-root` override.
- Planner, controller, coordinator logic stays **capability-driven** — no `if platform == "gb10"` branches.
- At Phase 3 start, remind the user to prepare GB10 access. Only declare `GB10 Gate 1 is ready to run` when the unified runner, transaction/recovery flow, and minimal smoke workflow are all complete and the user is preparing GB10.
