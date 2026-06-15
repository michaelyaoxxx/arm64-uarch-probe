# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

`arm64-uarch-probe` is a reproducible microarchitecture research baseline for the NVIDIA GB10 ARM64 SoC (A725 + X925 cores). Mac and Linux ARM64 environments validate engineering behavior; **GB10 is the only authoritative measurement platform** and is first required at Phase 3 Gate 1.

Phase 1 (current focus on the `codex/phase2-backends-environment-design` branch): read-only control layer with immutable domain models, declarative registries, public JSON schemas, deterministic planning, `probe doctor` (host inspection), and a recoverable environment transaction model. **No probe is executed in Phase 1/2.**

Current branch is mid-Phase 2: a recoverable environment transaction coordinator, explicit `probe restore` command, and Phase 2 acceptance closure are still being implemented. See `docs/superpowers/handoffs/2026-06-15-phase2-remaining-work.md` for the active handoff and Task 11/12/13 ordering.

## Common Commands

```sh
make help                            # list all targets
make phase1-check                    # Python tests + legacy manifest verification
make check                           # Python contract tests + bash syntax checks
make build                           # build probes supported on the current host
make build-linux                     # force all Linux probes; rejects non-Linux
make show-targets                    # source→binary mapping with platform support
make clean                           # remove build/ (safety-checked)

./probe --help                       # CLI help
./probe list targets                 # discover experiments/scenarios
./probe list platforms               # registered platforms
./probe show <id> -o json            # inspect a single registered object
./probe plan --platform gb10 --profile smoke -o json
./probe doctor -o json               # read-only host inspection
make probe PROBE_ARGS='show gb10 -o json'    # convenience wrapper
python3 -m arm64_probe help plan     # module entry point (debugging)
```

To run a single test file or test case:

```sh
python3 -m unittest tests.unit.test_domain_models -v
python3 -m unittest tests.unit.test_planner_selection.PlannerSelectionTests.test_expand_experiment -v
```

## Repository Layout

| Path | Purpose |
|---|---|
| `arm64_probe/` | Platform-independent Python control layer (CLI, planning, domain, registry, backends, environment, diagnostics) |
| `arm64_probe/cli/` | argparse wiring + renderers (`main.py`, `parser.py`, `render.py`) |
| `arm64_probe/domain/` | Frozen `dataclass` domain models + ID validators |
| `arm64_probe/registry/` | `Catalog` (loads + validates `configs/`) and per-file JSON validators |
| `arm64_probe/planning/` | `Planner`, `PlanRequest`, semantic CPU selection orchestration |
| `arm64_probe/platforms/` | `ConfiguredPlatformResolver` — turns semantic selectors into concrete CPUs |
| `arm64_probe/backends/` | `HostBackend` protocol; `linux_arm64/` (read-only inspector + cpufreq/hugepage/THP controllers) and `darwin_arm64/` (synthetic, contract-only) |
| `arm64_probe/environment/` | `MutationLock` (host-wide fcntl), `JournalStore` (atomic persistent journals), `EnvironmentJournal`/`EnvironmentPhase` models, `requests_from_requirements` |
| `arm64_probe/diagnostics/` | `Doctor` — read-only host inspection report |
| `arm64_probe/serialization/` | `load_json` / `dump_json` + dataclass↔dict adapter |
| `configs/` | Declarative platform (`platforms/*.json`), experiment (`experiments/*.json`), profile (`profiles/*.json`), capability facts |
| `schemas/` | Public JSON schemas (capability, case, plan, run-result, sample, environment, …) |
| `src/<probe>/` | C single-measurement probes (`chase_pmu_v2.7.3.c`, `evict_slc_v1.2.c`, `chase_migrate_v1.0.c`) — build outputs go to ignored `build/bin/` |
| `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/fixtures/`, `tests/support/` | Test-suite ownership boundaries (see `docs/design/repository-layout.md`) |
| `runner/run_pmu*.sh`, `data/` | **Frozen** legacy evidence. `make legacy-check` enforces integrity via `legacy/manifest.json`. Do not modify for new features. |
| `docs/design/` | `repository-contract.md`, `repository-layout.md`, `cli-contract.md` — authoritative contracts |
| `docs/superpowers/specs/`, `docs/superpowers/plans/`, `docs/superpowers/handoffs/` | Phase design specs, implementation plans, and active handoffs (read in that order when picking up a phase) |

## Architecture

### Layered design (read-only Phase 1 surface)

```
CLI (arm64_probe/cli/)         arg parser + renderers
    │
    ├── Catalog (arm64_probe/registry/)        validates & loads configs/*.json
    │       └── uses arm64_probe/registry/validation.py per-file loaders
    │
    ├── Planner (arm64_probe/planning/)        deterministic, side-effect-free Plan
    │       └── ConfiguredPlatformResolver     semantic → concrete CPU
    │       └── domain/models.py               Capability/Platform/Scenario/Case/Plan
    │
    ├── Doctor (arm64_probe/diagnostics/)      read-only host report
    │       └── HostBackend (backends/)        capability-driven
    │              ├── linux_arm64             inspector + cpufreq/hugepage/THP controllers
    │              └── darwin_arm64            contract-only, supports smoke contract
    │
    └── JournalStore / MutationLock            env recovery infrastructure
            └── EnvironmentJournal            persistent, atomic, owner-checked
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
3. Each `Case` carries `execution_requirements` (cpu-affinity, page-policy) and the parent `Plan` carries `environment_phases` — host-scoped `EnvironmentRequirement` groupings with the `mutation` flag.
4. Scenarios expand to deduplicated scenario IDs; profile selections + CLI `--select` form a deterministic union.

### Environment transaction model (Phase 2)

- `EnvironmentRequirement` is `host`-scoped (host-wide mutation) or `case`-scoped (per-case, not yet mutating).
- `requests_from_requirements` orders requests by `CONTROLLER_ORDER` (`linux.cpufreq`, `linux.hugepage`, `linux.transparent-hugepage`) in `arm64_probe/environment/constants.py`.
- `JournalStore` (root `/var/lib/arm64-uarch-probe/journals/`) writes `<32-hex-txid>.json` atomically via `O_NOFOLLOW | O_EXCL` + `fsync` + `os.replace` + directory fsync. State transitions are enforced via `TRANSITIONS`. A `restored` journal is immutable.
- `MutationLock` (host-wide `fcntl.flock` on `/var/lib/arm64-uarch-probe/mutation.lock`) gates any mutating command across checkouts; requires `os.geteuid() == 0` and validates the root, lock file, and opened fd are owned by the required uid and not symlinks.
- `MutationController` Protocol: `inspect → validate_request → apply → verify → restore → verify_restored`. Restore is reverse of apply; `active_controller` is restored first even after a mid-apply crash.
- **Public mutation surface requires `--allow-mutation` AND caller privilege; CLI never invokes `sudo`.**

### CLI surface (Phase 1; Phase 2 adds `restore`)

Entry points: `./probe` and `python3 -m arm64_probe` (identical). Commands: `list`, `show`, `plan`, `help`, `doctor`. `restore` (Task 12) accepts `--journal <path> --allow-mutation` and **does not** add target settings, `--state-root`, automatic `sudo`, or interactive prompts. Only `-h`/`--help` and `-o`/`--output` are short options.

### Exit codes (authoritative: `arm64_probe/errors.py`)

`0` success · `2` usage · `3` config · `4` capability · `5` planning · `10` host inspection · `11` mutation auth · `12` apply failure (restoration succeeded) · `13` restore failure · `14` active lock / unfinished journal.

## Authoritative Contracts (always read first)

- `docs/design/repository-contract.md` — collaboration, result retention, GB10 handoff
- `docs/design/repository-layout.md` — frozen vs transitional vs v1.0 path ownership
- `docs/design/cli-contract.md` — entry points, command surface, exit codes, side-effect boundary
- `docs/superpowers/specs/2026-06-14-phase2-backends-environment-design.md` — Phase 2 design
- `docs/superpowers/plans/2026-06-14-phase2-backends-environment.md` — Phase 2 implementation plan (Tasks 1–13)
- `docs/superpowers/handoffs/2026-06-15-phase2-remaining-work.md` — active handoff for Tasks 11/12/13

## Coding Style & Testing

- Four-space indentation in C and Python; follow existing C brace placement; keep compiler warnings enabled (`-Wall -Wextra`).
- Python: `snake_case` functions and tests; immutable `dataclass(frozen=True)` records; tuple-based public models; Python standard library only; **declarative platform facts over platform-name branches**; tests named `test_<area>.py`.
- Use `unittest` (not pytest). Add a failing test before changing behavior (TDD).
- Run `make check`, `make phase1-check`, `make build`, and `git diff --check` before submitting changes.
- For unit tests needing a host filesystem, use `tests/support/host_fixture.py` (`HostFixture` builds a temp `PathHostFilesystem` and refuses symlink/path-escape writes). Inject it into controllers/inspectors — never touch the real host in unit tests.

## Commits, Branches, and PRs

- Imperative, focused commit messages (e.g. `Add recoverable environment transaction coordinator`).
- Branch is `codex/phase2-backends-environment-design`; do not develop on `main`.
- Each Task 11/12/13 lands as a **separate** commit; do not squash them.
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
- After Phase 2 lands, only declare `GB10 Gate 1 is ready to run` when the unified runner, transaction/recovery flow, and minimal smoke workflow are all complete and the user is preparing GB10.
