# Phase 4 Delivery Contract and Handoff

> **Status:** Phase 3 is accepted and merged into `main`. This is the
> authoritative Phase 4 acceptance and quality-control contract. Implementation
> agents must first write a detailed design and implementation plan against this
> contract; final acceptance returns to the architect agent.

## 0. Quick Phase 3 Acceptance

Fast local verification on 2026-06-17:

- `main` HEAD: `78652df Add Phase 4 architect brief`
- `make phase3-check`: 365 tests OK, 7 skipped, legacy manifest verified 17
  files, Phase 3 acceptance tests OK
- Phase 3 evidence matrix exists:
  `docs/superpowers/handoffs/2026-06-17-phase3-ac-evidence-matrix.md`
- Caution: `results/gate1-20260616/` and `results/gate1-20260617/` are
  untracked local evidence directories. Do not commit them accidentally.

## 1. Objective and Scope

Phase 4 turns structured run results into reproducible analysis artifacts,
reports, figures, and methodology documents:

- `probe analyze` consumes schema-valid `RunResult` artifacts;
- `probe report` consumes analysis artifacts and emits Markdown reports;
- historical logs can be imported only through tested adapters;
- figures are generated reproducibly under `docs/assets/v1.0/`;
- candidate GB10 baseline evidence may be promoted under
  `results/baselines/v1.0/` only through a reviewed action;
- methodology documents connect probe code, measurement principles, limits, and
  conclusions;
- Chips and Cheese comparison records agreement, difference, methodological
  mismatch, and uncovered areas;
- X925/A725 deep-dive roadmap covers ROB, decode/dispatch width, execution
  resources, load/store behavior, branch prediction, cache/TLB, and SLC/hash
  questions.

Phase 4 does **not** freeze `v1.0.0`, does not publish final release claims,
and does not add new public mutation entry points. Final RC/tag and complete
release freeze belong to Phase 5.

## 2. Locked Architecture Decisions

- GB10 remains the only authoritative measurement platform; Mac is for
  development, offline analysis, figures, and docs.
- `probe analyze` and `probe report` are read-only with respect to host state:
  no coordinator, lock, journal, `sudo`, or host mutation.
- All analysis consumes structured `RunResult` or explicitly imported legacy
  records; no ad hoc parsing inside report generation.
- Reviewed evidence lives under `results/baselines/<version>/`; temporary runs
  stay under ignored `results/runs/`.
- Publication figures live under `docs/assets/<version>/` and must identify
  their structured input plus regeneration command.
- Existing frozen paths remain frozen: `runner/`, `data/`, `analysis/`,
  `baseline/`, and `runner/cache_info_*`.
- Default implementation uses Python standard library. Any plotting/statistics
  dependency requires explicit design justification, lockfile update, and
  contract tests.

## 3. Required Public Behavior

Required CLI forms:

```sh
probe analyze --run <run-result.json> [--run <run-result.json> ...] \
  [--baseline <analysis-or-baseline.json>] --output-dir <dir> [-o table|json]

probe report --analysis <analysis-summary.json> --output-dir <dir> \
  [--format markdown] [-o table|json]
```

Long options only, except existing `-h` and `-o`. Preserve exit codes `0`,
`2`-`5`, and `10`-`16`. Use `16` for run-result, analysis-artifact, baseline,
or report persistence/compatibility failures. Add no new exit code unless the
Phase 4 design proves it necessary and updates `arm64_probe/errors.py`,
`docs/design/cli-contract.md`, and contract tests together.

Outputs must be deterministic:

- analysis summary JSON;
- normalized CSV or JSON tables for metrics;
- figure files with stable names;
- Markdown report with traceable claims;
- manifest listing inputs, commands, commit, dirty-tree state, toolchain, and
  generated artifacts.

## 4. Phase 4 Acceptance Criteria

Every criterion requires automated evidence unless explicitly marked GB10 or
source-review.

### AC1: Analysis Artifact Contract

- Define immutable analysis models and strict public schemas.
- Analysis JSON round-trips deterministically and rejects duplicate keys,
  unknown fields, incompatible schema versions, missing inputs, and mixed
  repository/platform identities unless explicitly allowed.
- All generated artifacts include provenance linking back to exact `RunResult`
  IDs and source paths.

### AC2: RunResult Ingestion and Legacy Import

- `probe analyze` accepts one or more schema v2 `RunResult` files.
- Historical text logs import through tested adapters into the same internal
  analysis protocol; imported records carry source path, parser version, and
  loss/assumption notes.
- No report or figure code reads legacy text directly.

### AC3: Statistics and Anomaly Rules

- Analysis computes deterministic summary statistics per case/metric:
  sample count, success/error count, min/max, median, MAD or IQR, mean,
  standard deviation, and selected units (`ns`, cycles, bytes, ratios).
- Outlier and variance flags are explicit, tested, and documented.
- Cross-run comparison classifies unchanged, improved, regressed, missing, and
  incompatible cases without hiding failed samples.

### AC4: Figure Generation

- Figures are regenerated from analysis artifacts only, never from raw logs.
- Each figure has a stable filename, caption metadata, source analysis ID, and
  regeneration command.
- Figure generation is deterministic enough for tests to validate manifest,
  labels, series, units, and input coverage. Pixel-perfect image equality is
  not required unless the implementation deliberately chooses it.

### AC5: Report Generation

- `probe report` emits a deterministic Markdown report plus manifest.
- Each claim links to an analysis artifact, figure, table, or cited source.
- Reports clearly separate measured results, inferred conclusions, hypotheses,
  methodology limits, and unresolved questions.
- Empty, partial, failed, or incompatible analyses produce structured errors or
  explicit warning sections; they never silently disappear.

### AC6: Methodology and Source Traceability

- Methodology docs explain how cache latency, DRAM latency, migration latency,
  page policy, warm/cold behavior, PMU counters, and units are derived from the
  probe code and result schema.
- Chips and Cheese comparison uses a reviewed source note and labels each item
  as agreement, difference, methodological mismatch, or uncovered.
- Any external factual claim has a citation or is marked as inference.

### AC7: Candidate Baseline Promotion

- Candidate GB10 results can be promoted to `results/baselines/v1.0/` only with
  a manifest, source run IDs, commands, commit/tag, toolchain, environment
  evidence, analysis summary, report, and regeneration instructions.
- Promotion rejects dirty-tree or schema-incompatible inputs unless the user
  explicitly approves a documented exception.
- Phase 4 may create candidate baselines; final release freeze remains Phase 5.

### AC8: X925/A725 Deep-Dive Roadmap

- Add a roadmap document under `docs/roadmap/` covering at minimum ROB
  capacity, decode/dispatch width, execution resources, load/store behavior,
  branch prediction, cache/TLB behavior, SLC/hash behavior, PMU mapping, and
  experiment feasibility.
- Each roadmap item states current evidence, missing measurement, proposed
  probe or method, risk, and priority.
- No deep-dive implementation is required in Phase 4 unless separately scoped.

### AC9: Compatibility and Repository Boundaries

- Phase 1-3 tests remain green.
- Existing `probe run`, `probe resume`, environment recovery, and frozen legacy
  contracts do not regress.
- Makefile adds only thin wrappers such as `phase4-check`, `analyze`, or
  `report`; it contains no analysis matrix or plotting logic.
- No GB10 measurement claim is made from Mac data.

## 5. Quality-Control Strategy

### Test Pyramid

- **Unit:** analysis models, statistics, anomaly classification, import
  adapters, figure/table manifests, report section generation.
- **Contract:** CLI forms, exit codes, schemas, deterministic serialization,
  repository path policy, source traceability, Makefile thin wrappers.
- **Integration:** end-to-end RunResult fixture -> analyze -> figures/tables ->
  report -> manifest validation.
- **GB10/host evidence:** only for candidate baseline promotion or Gate 2; all
  parsing/report failures must reproduce on local fixtures first.

### Per-Task Gate

Before each focused commit:

```sh
uv run --no-sync python -m unittest <focused-modules> -v
make check
make legacy-check
git diff --check
git status --short
```

Each commit owns one behavior and its tests. Do not combine ingestion,
statistics, figures, reports, methodology, and baseline promotion in one
commit.

### Phase Completion Gate

Before final architect review:

```sh
make phase4-check
make phase3-check
make check
make legacy-check
make build
make smoke
./probe help analyze
./probe help report
git diff --check
git status --short
git diff --name-status main...HEAD
```

Implementation agents must provide an AC1-AC9 evidence matrix with criterion,
proving test/command, result, and artifact path. Narrative alone does not close
any criterion.

## 6. Recommended Work Order

First produce and obtain user approval for:

1. `docs/superpowers/specs/2026-06-17-phase4-analysis-report-design.md`
2. `docs/superpowers/plans/2026-06-17-phase4-analysis-report.md`

Then implement in this dependency order:

1. Analysis public models, schemas, and deterministic artifact store.
2. RunResult ingestion and legacy import adapters.
3. Statistics, units, anomaly, and comparison engine.
4. `probe analyze` CLI and analysis manifests.
5. Figure/table generation and reproducibility manifests.
6. `probe report` CLI and Markdown report generation.
7. Methodology docs, Chips and Cheese comparison, and X925/A725 deep-dive
   roadmap.
8. Candidate baseline promotion workflow, Phase 4 acceptance tests, and docs.

Parallel work is allowed only after public schemas are frozen and only on
disjoint files. One integration owner must control CLI, schemas, manifests, and
final acceptance.

## 7. Final Review Package

Return to the architect agent only when the branch contains:

- approved Phase 4 design and implementation plan;
- focused commits with tests;
- AC1-AC9 evidence matrix;
- clean Phase 4 completion-gate output;
- generated report/figure examples from fixture data;
- any candidate GB10 baseline evidence clearly separated from final release
  evidence;
- no accidental commits of unreviewed `results/gate1-*` or ignored run output.

The architect will review scope, traceability, statistical safety, repository
diff, and evidence. The user decides merge and push timing.
