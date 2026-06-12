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
- `make build`: build probes supported on the current host.
- `make build-linux`: build all Linux probes; reject non-Linux hosts.
- `make check`: run repository policy, legacy integrity, Makefile contract, and
  shell-syntax checks.

## Legacy Evidence

Current versioned runner scripts and tracked data files are frozen historical
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
