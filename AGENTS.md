# Repository Guidelines

## Project Structure and Boundaries

Probe sources live under `src/<probe>/`; current probes include `chase_pmu`,
`evict_slc`, and `chase_migrate`. Build products belong in ignored
`build/bin/`. Python repository tooling is under `scripts/`, contract tests are
under `tests/`, and design decisions are under `docs/design/`.

GB10 is the authoritative v1.0 measurement platform. Mac validates software
behavior, runs contract tests, and supports offline analysis; Mac measurements
are not GB10 baselines. Versioned `runner/run_pmu*.sh` scripts and tracked
`data/` files are frozen legacy evidence. Do not modify them for new features.

## Build, Test, and Development Commands

- `make help`: list supported repository targets.
- `make show-targets`: show source-to-`build/bin` mappings and platform support.
- `make build`: build probes supported by the current host.
- `make build-linux`: build all probes on Linux; rejects other hosts.
- `make check`: run Python contract tests and Bash syntax checks.
- `make legacy-check`: verify frozen legacy files against their manifest.
- `make clean`: remove only repository build products.

Run `make check` before submitting changes. Mac should also run `make build`;
Linux ARM64 changes should run `make build-linux`. GB10 measurements must record
the exact Git commit or tag, environment state, commands, failures, and
restoration status.

## Coding Style and Testing

Use four-space indentation in C and Python. Follow existing C brace placement,
keep compiler warnings enabled, and use `snake_case` for Python functions and
tests. Prefer the Python standard library for runtime tooling. Name tests
`tests/test_<area>.py` and write behavior-focused `unittest` cases. Add a
failing contract test before changing behavior.

## Results, Commits, and Pull Requests

Keep temporary output in ignored `results/runs/`, reviewed release evidence in
`results/baselines/<version>/`, and publication figures in
`docs/assets/<version>/`. Use focused imperative commit messages. Pull requests
must state scope, verification, whether GB10 evidence is required, and whether
environment restoration was verified.
