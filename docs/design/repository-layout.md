# Repository Layout

## Frozen Historical Evidence

- `runner/run_pmu*.sh`: pre-v1.0 experiment runners.
- `data/`: pre-v1.0 raw measurement evidence.

Keep these paths at their historical locations. Do not add v1.0 features or
new files under them. `legacy/manifest.json` and `make legacy-check` protect
their inventory, provenance, and content. Moving them requires a separately
reviewed compatibility migration.

## Transitional Paths

- `analysis/` and `baseline/`: remain unchanged until Phase 4 imports their
  evidence into the structured result protocol.
- `runner/cache_info_*.sh` and `runner/cache_info_model.py`: remain unchanged
  until Phase 2 or Phase 3 assigns them to a backend, platform description, or
  compatibility adapter.

Do not expand transitional paths with new v1.0 architecture.

## v1.0-Owned Paths

- `src/`: C single-measurement probes.
- `arm64_probe/`: future platform-independent Python control layer.
- `configs/`: future reviewed platform, experiment, and profile definitions.
- `tests/unit/`, `tests/contract/`, `tests/fixtures/`, `tests/integration/`:
  future test-suite ownership boundaries.
- `results/`: temporary runs and reviewed release evidence.
- `docs/design/`, `docs/methodology/`, `docs/references/`, `docs/results/`,
  `docs/roadmap/`, and `docs/assets/`: v1.0 documentation and publication
  boundaries.

Skeleton README files describe ownership only. They do not define Phase 1
Python APIs, package markers, configuration encodings, or schemas.

## Migration Rules

Use `git mv` where practical. Preserve history and traceability. A migration
must update references, compatibility behavior, tests, and documentation in one
reviewed change. Frozen or transitional paths move only in the phase named
above or under a separately approved compatibility plan.

See `legacy/README.md` for integrity semantics and `results/README.md` for
result-retention policy.
