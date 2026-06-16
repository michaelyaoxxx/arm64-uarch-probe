# Phase 3 Delivery Contract and Handoff

> **Status:** Phase 2 is accepted and merged into `main`. This document is the
> authoritative Phase 3 acceptance and quality-control contract. Other agents
> may write the detailed design/plan, implement, and test against it. Final
> acceptance returns to the architect agent.

## 1. Objective and Scope

Phase 3 delivers normalized probes and a unified transactional runner:

- normalized named arguments and machine-readable probe output;
- `probe run` for individual scenarios, arbitrary combinations, profiles, and
  exact case IDs;
- structured `Sample` and `RunResult` persistence;
- environment-phase execution through the existing
  `EnvironmentCoordinator`;
- `probe resume` for missing/failed cases;
- a minimal smoke workflow and one controlled GB10 Gate 1 run.

`probe analyze`, `probe report`, figures, methodology conclusions, and full
v1.0 baseline measurements belong to Phase 4 or later.

## 2. Locked Architecture Decisions

1. **Transaction boundary:** one transaction per environment phase, not per
   case. Cases sharing identical host requirements run under one transaction;
   restoration occurs before the next phase.
2. **Resume source:** `probe resume` reads a prior structured `RunResult`.
   Environment journals remain exclusively for environment recovery.
3. **Execution boundary:** a platform-independent runner invokes injectable
   probe/process adapters. It contains no GB10/M4 branches, sysfs paths, or
   experiment-specific parsing.
4. **Legacy boundary:** frozen `runner/run_pmu*.sh`, `data/`, `analysis/`,
   `baseline/`, and `runner/cache_info_*` remain unchanged. New adapters may
   preserve their behavior but must not call frozen runners as the new public
   control surface.
5. **Mutation boundary:** `probe run` is the only new public mutation entry
   point and must use the existing coordinator, lock, journal, restoration, and
   `--allow-mutation` contract. No automatic `sudo`.
6. **Result boundary:** local runs write under ignored `results/runs/`.
   Promotion into `results/baselines/<version>/` is a separate reviewed action.

## 3. Required Public Behavior

The detailed plan must preserve these forms:

```sh
probe run cache-latency/l1-latency
probe run cache-latency/l2-latency cache-latency/dram-latency
probe run migration-latency/cross-cluster
probe run cache-latency
probe run --profile smoke
probe run --case <stable-case-id>
probe resume --run <run-result-path>
```

Existing selectors and overrides accepted by `probe plan` must have identical
meaning under `probe run`. `run` adds only execution concerns such as
`--output-dir` and `--allow-mutation`. Do not invent short options without a
strong conventional precedent.

Preserve existing exit codes `0`, `2`-`5`, and `10`-`14`. Before implementation,
the detailed design must freeze and contract-test:

- `15`: probe launch, timeout, signal, nonzero exit, or invalid probe output;
- `16`: run-result read, validation, compatibility, or persistence failure.

An invocation with any failed case writes its partial `RunResult` and returns
`15`, unless an environment restore failure requires the higher-priority `13`.

## 4. Phase 3 Acceptance Criteria

Every criterion requires automated evidence unless explicitly marked GB10.

### AC1: Normalized Probe Contract

- All three probes build on their supported hosts and expose normalized named
  arguments.
- Machine-readable output is strict, deterministic, versioned, and parses into
  `Sample`; malformed, partial, timeout, signal, and nonzero-exit output become
  structured failures.
- Existing probe measurement semantics are preserved and documented by
  characterization tests before normalization.

### AC2: Selection and Composition

- Individual scenario, parent experiment, arbitrary combination, profile, and
  exact case execution work end to end.
- Selection is deterministic and deduplicated by stable case ID.
- `probe run` executes exactly the cases and parameters shown by the
  corresponding `probe plan`.

### AC3: Transactional Execution

- Cases are grouped by deterministic environment phase.
- Each mutating phase runs through `EnvironmentCoordinator.execute`.
- Missing `--allow-mutation` returns `11` before host writes.
- Apply/work failure restores the host and returns `12`; restore failure returns
  `13`; active lock or unfinished journal returns `14`.
- Success, failure, signal interruption, and probe timeout all leave finalized
  journals and restored fixture state.

### AC4: Structured Results and Provenance

- Every attempted case produces immutable `Sample` records; every invocation
  produces one schema-valid `RunResult`, including partial failure.
- Results record run/case IDs, selected parameters, sample index/status,
  metrics, failure details, timestamps, platform/backend identity, repository
  commit, dirty-tree status, toolchain/compiler evidence, and command intent.
- Writes are atomic; an interrupted write never replaces the last valid result.
- JSON output is deterministic and passes public schema contract tests.

### AC5: Resume and Exact Rerun

- `probe resume --run <path>` executes only missing/failed cases and preserves
  successful samples.
- Resume rejects incompatible schema, platform, case definition, or execution
  contract changes with a structured error before execution.
- Exact case rerun reproduces the recorded case selection and parameter values;
  it creates a new run identity and links to the source run.
- Repeated resume is idempotent once all cases are successful.

### AC6: Stable CLI and Makefile

- `probe help run`, `probe help resume`, table/JSON output, structured errors,
  and exit codes are contract-tested.
- Makefile adds thin `smoke` and `phase3-check` wrappers only; it contains no
  scenario matrix, platform branch, parsing, mutation, or result logic.
- Every Python invocation remains routed through pinned `uv run --no-sync`.

### AC7: Compatibility and Boundaries

- Existing Phase 1/2 public contracts and tests remain green.
- No platform-name branch appears in planner, runner, executor, coordinator, or
  probe adapters.
- Frozen/transitional paths and historical evidence remain unchanged.
- Mac produces software-validation evidence only, never a GB10 or M4
  measurement claim.

### AC8: Minimal Smoke Workflow

- From a clean Mac checkout, `make sync`, `make build`, `make phase3-check`, and
  fixture-backed `make smoke` complete without host mutation and produce a
  schema-valid `RunResult`.
- Linux ARM64 validation builds all probes and exercises normalized probe
  invocation, failure parsing, transactional fixture execution, restoration,
  resume, and exact rerun before GB10 is requested.
- Smoke is intentionally small and bounded; it is not the v1.0 baseline.

### AC9: GB10 Gate 1

Gate 1 runs once only after AC1-AC8 pass and the architect explicitly announces:

```text
GB10 Gate 1 is ready to run
```

From a clean GB10 checkout, record:

1. commit and clean-tree evidence;
2. `make sync`, pinned Python/uv/compiler/toolchain evidence;
3. `make build`, `make phase3-check`, and `probe doctor -o json`;
4. `probe plan --platform gb10 --profile smoke -o json`;
5. authorized `probe run --platform gb10 --profile smoke --allow-mutation`;
6. schema-valid result, finalized journal, and verified environment restoration;
7. retain the already-passing AC5 fixture evidence; do not manufacture a
   failure or add resume/rerun invocations on GB10 merely for Gate 1.

Any Gate 1 failure is fixed and revalidated first on Mac/fixture or Linux ARM64
where possible. Do not expand Gate 1 into broad exploratory measurement.

## 5. Quality-Control Strategy

### Test Pyramid

- **Unit:** argument normalization, output parsing, process outcomes, result
  assembly/storage, resume diffing, phase grouping.
- **Contract:** CLI examples, schemas, exit codes, plan/run equivalence,
  capability-driven boundaries, frozen paths, uv/Makefile rules.
- **Integration:** fake process executor + fake backend + real coordinator;
  exhaustive failure/signal/timeout restoration; result persistence and resume.
- **Host validation:** Linux ARM64 compile/invocation checks, then GB10 Gate 1.

All behavior changes use TDD. Fault-injection tests are mandatory at each
external boundary: process start, output parse, sample persistence, journal
transition, work callback, restoration, and resume persistence.

### Per-Task Gate

Before each focused commit:

```sh
uv run --no-sync python -m unittest <focused-modules> -v
make check
make legacy-check
git diff --check
git status --short
```

Each commit owns one coherent behavior and its tests. Do not combine probe
normalization, runner orchestration, resume, and acceptance closure in one
commit.

### Phase Completion Gate

Before final architect review:

```sh
make phase3-check
make check
make legacy-check
make build
make smoke
./probe --help
./probe help run
./probe help resume
git diff --check
git status --short
git diff --name-status main...HEAD
```

The implementation agents must provide an AC1-AC9 evidence matrix containing
the criterion, proving test/command, result, and artifact path. No criterion
may be closed by narrative assertion alone.

## 6. Recommended Work Order and Ownership

Other agents should first write and obtain user approval for:

1. `docs/superpowers/specs/2026-06-15-phase3-probes-runner-design.md`
2. `docs/superpowers/plans/2026-06-15-phase3-probes-runner.md`

Then implement in this dependency order:

1. Characterization tests and normalized probe/process adapter contract.
2. `Sample`/`RunResult` construction, schema, provenance, and atomic storage.
3. Unified runner with plan equivalence and environment-phase transactions.
4. `probe run` CLI and composition/profile/exact-case contracts.
5. `probe resume` and exact-rerun contracts.
6. Mac/Linux fixture smoke, Phase 3 acceptance tests, docs, and Gate 1 runbook.

Parallel work is allowed only on disjoint files after public types are frozen.
One integration owner must control shared CLI, runner, schemas, and final
acceptance changes. Agents must not silently change this contract; disagreements
are returned to the user before implementation.

## 7. Final Review Package

Return to the architect agent only when the branch contains:

- approved design and detailed implementation plan;
- focused commits with tests;
- AC1-AC9 evidence matrix;
- clean Phase 3 completion-gate output;
- no unexpected frozen/transitional changes;
- Gate 1 runbook, and GB10 evidence only if Gate 1 was explicitly authorized.

The architect will review contracts, failure safety, repository diff, and
evidence. The user decides merge and push timing.
