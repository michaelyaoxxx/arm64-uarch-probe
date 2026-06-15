# Repository Contract

## Authority and Collaboration

`michaelyaoxxx/arm64-uarch-probe` is the only authoritative repository.
Mac and GB10 exchange code, configuration, selected results, and documents
through branches, pull requests, commits, and tags. Do not maintain divergent
copies or develop directly on `main`.

## Platform Responsibilities

- Mac: development, unit/contract tests, offline analysis, figures, and docs.
- Linux ARM64: Linux build and backend behavior checks.
- GB10: authoritative hardware measurements and release gates.

Mac measurements validate software behavior only; they are not GB10 baselines.

## Runtime and Development Dependencies

GB10 runtime code may depend on compiled probes, Bash/system utilities, and the
Python standard library. Third-party Python packages are development or
analysis dependencies and must be installed through repository-owned metadata.

## Build and Verification Contract

- `make help`: list accurate supported targets.
- `make show-targets`: show source-to-binary mappings and platform support.
- `make sync`: provision or refresh the local `.venv/` from `uv.lock`.
- `make build`: build probes supported on the current host.
- `make build-linux`: build all Linux probes; reject non-Linux hosts.
- `make check`: run repository policy, legacy integrity, Makefile contract, and
  shell-syntax checks.
- `make phase1-check` and `make phase2-check`: run the full Python test
  discovery and the legacy manifest verification.
- `make doctor`: thin wrapper around `./probe doctor` for host inspection.

All Python invocations under this Makefile go through `uv run --no-sync`.
The repository is pinned to CPython 3.13.13 via `.python-version` and
`pyproject.toml`; do not invoke the system `python3` directly. See
`AGENTS.md` for the full toolchain description.

## Repository Layout

`docs/design/repository-layout.md` is the authoritative ownership map for
frozen historical evidence, transitional paths, and v1.0-owned paths. Do not
move frozen or transitional paths outside its reviewed migration rules.

## Legacy Evidence

Current versioned runner scripts and tracked `data/` files are frozen historical
evidence. The current versioned experiment runners are `runner/run_pmu*.sh`.
Verify them with `make legacy-check`. Do not change them for v1.0 features.
Later migration requires an explicit compatibility plan.

## Result Retention

`results/runs/` and recovery state are temporary and ignored. Commit only
reviewed release evidence under `results/baselines/<version>/` and publication
figures under `docs/assets/<version>/`.

## GB10 Handoff

Every GB10 run records the exact Git commit or tag. GB10 result branches include
the selected profile/scenarios, environment state, commands, failures, and
restoration status. Release-candidate runs use immutable RC tags.

## Host Mutation Safety

The production Linux state root is fixed at `/var/lib/arm64-uarch-probe`. The
host-wide `MutationLock` is the only public mutation surface; `probe restore`
is the only public mutating CLI command and requires both `--allow-mutation`
and the caller's privilege. The CLI never invokes `sudo` and never accepts a
public `--state-root` override. Recoverable environment transactions persist
journals before any host write, restore in reverse order, restore a recorded
`active_controller` first, and convert `SIGINT`/`SIGTERM` into automatic
restoration. Unhandleable process termination leaves a durable journal for
explicit recovery via `probe restore`.

## Platform Responsibilities

- Mac: development, unit/contract/integration tests, offline analysis, and docs.
  Mac measurements are not GB10 baselines.
- Linux ARM64: Linux build, host backend behavior checks, and integration tests
  using temporary Linux sysfs/procfs fixture trees.
- GB10: authoritative hardware measurements and release gates.

## Phase Boundaries

Phase 1 and Phase 2 require no GB10. Phase 3 begins the unified measurement
runner; remind the user to prepare GB10 access when Phase 3 starts. The
public announcement of Gate 1 readiness is gated on the unified runner,
the transaction/recovery flow, and a minimal smoke workflow all passing.
