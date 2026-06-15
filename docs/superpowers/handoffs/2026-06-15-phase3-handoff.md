# Phase 3 Handoff — From Phase 2 Implementer to Phase 3 Architect

> **From:** the agent that implemented Phase 2 + the toolchain pin on
> `codex/phase2-backends-environment-design`, then merged it into
> `main` at the user's direction.
>
> **To:** the original handoff agent that will now author the
> Phase 3 acceptance contract, quality controls, and detailed
> implementation plan.
>
> **Scope of this handoff:** the Phase 3 architect is expected to
> define the **acceptance criteria and quality controls** for
> Phase 3. The current implementer is expected to **write the
> detailed task-by-task plan, code, and tests** against those
> criteria. The user is expected to **review and merge Phase 3
> the same way Phase 2 was reviewed and merged**, and to
> **arrange GB10 access** before Gate 1 fires.

This document is the only thing you need to read to pick up where
we stopped. It is intentionally long: every section is
information a returning agent has historically had to re-derive
from commit messages, plan files, or the in-repo handoff docs.
Read it once, then keep the linked files open while you author
the Phase 3 contract.

## 1. Where we are right now (the only numbers you must memorize)

| Item | Value | Source of truth |
|---|---|---|
| Branch | `main` (topic branch `codex/phase2-backends-environment-design` retained, not deleted) | `git status`, `git branch -a` |
| `main` HEAD | `f852ad8` — "Merge branch 'codex/phase2-backends-environment-design' into main" | `git log --oneline main -1` |
| `main` ahead of `origin/main` | **20 commits** (19 topic-branch commits + 1 merge commit) | `git status` |
| Working tree | clean (`nothing to commit, working tree clean`) | `git status` |
| Python toolchain | **CPython 3.13.13** managed by `uv`; `.venv/` provisioned; lockfile committed | `.python-version`, `pyproject.toml`, `uv.lock`, `Makefile` |
| Test count | **241 passing** under the pinned toolchain | `make check` (5–6 s wall clock) |
| `make phase1-check` / `make phase2-check` | both green, run `make check` + `make legacy-check` | `make phase2-check` |
| Frozen legacy paths modified | **none** (verified by `git diff main...<topic> --name-only` filtering `runner/`, `data/`, `analysis/`, `baseline/`) | the Phase 2 closure handoff §1.1 + this handoff §6.2 |
| GB10 hardware touched | **no** | enforced by the handoff rule since the start of Phase 2 |
| M4 measurement claim | **no** | enforced by the Phase 2 acceptance contract |

If you take nothing else away from this document, take the table
above. The handoff doc
`2026-06-15-phase2-closure-and-phase3-readiness.md` is the
authoritative long-form status, and the file you are reading
now is the bridge between that status and the Phase 3 work that
will start next.

## 2. The handoff chain (read in this order)

The "in-flight" handoff pair is exhaustive and self-consistent.
Do not skim; both files are short.

1. `docs/superpowers/handoffs/2026-06-15-phase2-remaining-work.md`
   — the **inbound** handoff. What the user told the previous
   agent to do for Phase 2. Has not been changed since
   `2ffabb5`; keep it as-is, it is the historical record.
2. `docs/superpowers/handoffs/2026-06-15-phase2-closure-and-phase3-readiness.md`
   — the **closure** handoff. What we actually delivered for
   Phase 2, what is now on `main`, and the Phase 3 distance
   estimate. The §4 "Merge record" subsection describes the
   `--no-ff` merge that was performed at the user's direction
   (commit `f852ad8`).

You are authoring the next handoff
(`2026-MM-DD-phase3-probes-and-runner.md` is the planned
filename). That handoff should follow the same shape as
`2026-06-15-phase2-remaining-work.md` — front-matter intent
section, ordered task list, contracts, and a "no side effects
without authorization" rule.

## 3. The two deliverables you (the Phase 3 architect) own

You are explicitly **not** writing the detailed plan, code, or
tests. The role split is:

| Phase 3 workstream | Owner | Why |
|---|---|---|
| **Acceptance contract** (what "done" means) | You (Phase 3 architect) | Phase 1 + Phase 2 each opened with an acceptance contract written only after the prior phase's interfaces were reviewed. The v1.0 roadmap is explicit about this sequencing rule. |
| **Quality controls** (test taxonomy, contract boundaries, gate criteria) | You | Phase 2 set the bar with `tests/unit/`, `tests/contract/`, `tests/integration/`, `tests/support/`, and TDD on every new module. Phase 3 must keep that bar or raise it. |
| Detailed `2026-MM-DD-phase3-probes-and-runner.md` plan (task-by-task, file-by-file, test-by-test) | Us (implementers) | Phase 2 followed `2026-06-14-phase2-backends-environment.md` exactly. We will follow your acceptance contract the same way. |
| Code, tests, fixtures, refactors | Us | You do not write code. |
| GB10 hardware arrangement | The user | Not an agent task. |

The handoff you author should make the **acceptance contract
and quality controls** fully unambiguous to a downstream
implementer who has never seen the codebase. Concretely, that
means: a per-criterion pass/fail, the exact exit codes and
schema fields that prove each criterion, and a list of files
the implementer is allowed to add or modify.

## 4. The acceptance contract anchors you must respect

These constraints are already locked in by the v1.0 design spec,
the v1.0 roadmap, and the Phase 2 implementation. Phase 3
cannot loosen them. You should *cite* them in your acceptance
contract, not invent new ones.

### 4.1 Anchors from the v1.0 roadmap (`docs/superpowers/plans/2026-06-12-arm64-uarch-probe-v1.0-roadmap.md`)

Row 3 of the "Plan Sequence" table:

> Phase 3 — `phase3-probes-and-runner.md` — Normalized probes,
> executable scenarios, composition, profiles, resume — Gate 1
> once.

Row "Phase 3 acceptance contract":

- Existing probe behavior is preserved behind normalized named
  arguments and machine-readable output.
- Cache and migration scenarios can run individually or in
  arbitrary combinations.
- Profiles, selectors, stable case IDs, deduplication,
  transaction phases, resume, and exact reruns work end to
  end.
- Makefile wraps the stable CLI and contains no experiment
  matrix logic.
- **GB10 Gate 1 completes from a clean checkout and records
  toolchain evidence.**

### 4.2 Anchors from the v1.0 design spec (`docs/superpowers/specs/2026-06-12-arm64-uarch-probe-v1.0-design.md`)

Section 7.4 ("Individual and Combined Execution") fixes the
required CLI surface:

```text
probe run cache-latency/l1-latency
probe run cache-latency/l2-latency cache-latency/dram-latency
probe run migration-latency/cross-cluster
probe run cache-latency
probe run --profile v1.0-baseline
probe run cache-latency/l2-latency --cluster C1 --page-policy hugepage
probe run cache-latency/dram-latency --working-set 32MB,64MB,128MB
probe run migration-latency/cross-cluster --samples 3
probe run --case gb10/cache-latency/l2/C0-X925/2048KB/hugepage/warm
```

Section 7.5 lists the conceptual operations:

```text
probe list    discover experiments, scenarios, profiles, and prior runs
probe show    inspect one target or profile
probe help    show quick usage and operation-specific help
probe doctor  inspect dependencies, capabilities, and recovery journals
probe plan    expand selected targets and show environment changes
probe run     execute selected targets inside environment transactions
probe resume  continue incomplete cases from a prior run
probe analyze calculate statistics and compare selected runs or baselines
probe report  generate figures and Markdown reports
probe restore recover an interrupted environment transaction
```

Section 4.1 lists the platform-independent core types
(`Platform`, `Capability`, `Experiment`, `Scenario`, `Case`,
`Profile`, `Sample`, `RunResult`). The `Sample` and `RunResult`
records are already declared in
`arm64_probe/domain/models.py` but **not yet populated** — that
is the missing half of Phase 3 that the implementer will need
to wire.

### 4.3 Anchors the Phase 2 implementer has already enforced

These rules survived Phase 2 review; Phase 3 must not regress
them:

- **No platform-name branches.** `if platform == "gb10"` is
  forbidden in experiment, controller, coordinator, and
  planner code. The acceptance test
  `tests/contract/test_phase2_acceptance.py` enforces this.
- **Capability-driven.** Required and optional capabilities are
  declared in `configs/capabilities.json`; scenarios reference
  them via `required_capabilities`.
- **Public mutation requires `--allow-mutation` plus caller
  privilege.** The CLI never invokes `sudo`. The `probe run`
  command in Phase 3 must follow the same rule.
- **Run-results go under `results/baselines/<version>/`** for
  reviewed evidence and `docs/assets/<version>/` for figures.
  Daily runs live in git-ignored `results/runs/`.
- **All Python goes through `uv run`.** No raw `python3` in
  Makefile or shebangs. Lockfile is committed.
- **Immutable dataclasses, sorted-unique `JsonScalar`
  mappings, tuple-based public models, TDD on every
  behavior-changing commit, contracts in `tests/contract/`**.

### 4.4 Anchors from the original Phase 2 handoff

> 只有 unified runner、transaction/recovery flow 和 minimal smoke
> workflow 均准备完成后，才可以明确通知：
>
> ```text
> GB10 Gate 1 is ready to run
> ```

That sentence is your gate. The `probe run` smoke workflow
described in design spec §7.4 is the canonical minimal smoke
workflow. Your acceptance contract must define what "passes"
means for it on a non-GB10 host.

## 5. The current codebase surface you need to know

The implementer who picks this up next will already know the
code; the contract you author needs to be checkable by them
without re-reading the design spec. Give them concrete handles.

### 5.1 What's in the repo

- `arm64_probe/`
  - `cli/` — argparse wiring + renderers; currently
    implements `list`, `show`, `plan`, `doctor`, `restore`,
    and `help`. **Missing:** `run`, `resume`, `analyze`,
    `report`. Adding these is the public surface change of
    Phase 3.
  - `domain/` — frozen dataclasses. `Case` is already
    populated; `Sample` and `RunResult` are already declared
    (in `models.py`) and have JSON schemas
    (`schemas/sample.schema.json`,
    `schemas/run-result.schema.json`).
  - `planning/` — `Planner` and `PlanRequest`. Deterministic,
    read-only. No change expected.
  - `platforms/` — `ConfiguredPlatformResolver`. Stable.
  - `registry/` — `Catalog` + per-file JSON validators. Stable.
  - `backends/`
    - `linux_arm64/` — read-only inspector + three mutation
      controllers (cpu_frequency, hugepage, transparent_hugepage).
    - `darwin_arm64/` — read-only, contract-only, no
      controllers. Stable.
  - `environment/` — durable journal, host-wide
    `MutationLock`, `EnvironmentCoordinator` (transaction
    lifecycle), `EnvironmentRecovery` (managed-journal
    replay), signal scope. **This is the integration point
    for `probe run`**: the implementer will invoke
    `EnvironmentCoordinator.execute(backend, platform_id,
    requests, work, allow_mutation)` once per transaction
    phase, with `work` doing the actual probe execution +
    sampling.
  - `diagnostics/doctor.py` — read-only host report. Stable.
  - `serialization/` — `load_json` / `dump_json` + dataclass
    adapter. Stable.
- `configs/` — declarative platform, experiment, profile,
  capability facts. `platforms/gb10.json` is the GB10
  description; `experiments/cache-latency.json` and
  `experiments/migration-latency.json` enumerate the
  scenarios.
- `schemas/` — public JSON schemas for every public record,
  including the unused-for-now `sample.schema.json` and
  `run-result.schema.json`.
- `src/` — three C probes:
  - `chase_pmu/chase_pmu_v2.7.3.c`
  - `evict_slc/evict_slc_v1.2.c`
  - `chase_migrate/chase_migrate_v1.0.c`
  These are the un-normalized probes Phase 3 must put behind
  stable named arguments and machine-readable output.
- `runner/` — nine frozen `run_pmu_v2.7.*.sh` scripts plus
  `cache_info_collect.sh` and `cache_info_model.py`. The
  legacy manifest (`legacy/manifest.json`) freezes their
  integrity. Phase 3 wraps them with a new unified runner
  but does not modify the scripts themselves.
- `data/` — frozen raw measurement evidence. Untouched by
  Phase 2; must remain untouched by Phase 3.
- `tests/`
  - `unit/` — one test module per code module; TDD.
  - `contract/` — public schema, CLI, Makefile, journal
    security, host backend, Phase 2 acceptance, toolchain
    contract tests.
  - `integration/` — environment locking processes, signal
    restore, Phase 1 / Phase 2 / doctor / restore workflows.
  - `support/` — `host_fixture.py` (temp `PathHostFilesystem`),
    `fake_controllers.py` (`FakeController`, `FakeBackend`).
  - `fixtures/` — JSON fixtures.
  - `test_makefile_contract.py` and `test_repository_policy.py`
    at the top level (frozen-path integrity).
- `docs/`
  - `design/` — `repository-contract.md`,
    `repository-layout.md`, `cli-contract.md` (all
    authoritative; Phase 2 expanded them).
  - `arch/` — `cpu_topology.md`, `pmu_mapping.md` (GB10
    microarchitecture reference).
  - `methodology/`, `roadmap/`, `references/`, `results/`,
    `assets/` — v1.0-owned paths, mostly empty.
  - `superpowers/specs/`, `docs/superpowers/plans/`,
    `docs/superpowers/handoffs/` — agent work product.

### 5.2 What's missing (Phase 3 work)

The Phase 3 acceptance contract you author must explicitly
cover each of these gaps. The implementer will pick them up
in detail from your contract; the bullets here are only the
shape.

1. **`probe run` CLI surface.** Args: `<target>...` plus
   `--platform`, `--profile`, `--select`, `--cluster`,
   `--core-group`, `--cpu`, `--src-cpu`, `--dst-cpu`,
   `--samples`, `--working-set`, `--page-policy`, `--case`,
   `--output`, `--allow-mutation`, plus a stable
   `--output-dir`. The spec example in §4.2 is the input
   contract; `--allow-mutation` is required when the plan
   contains any `host`-scoped environment requirement.
2. **`probe resume` CLI surface.** Re-runs the cases
   referenced in a prior `RunResult` whose `status` is not
   "ok". Implementation: read prior `RunResult`,
   diff against current plan, re-execute the missing or
   failed cases inside the same transaction
   infrastructure.
3. **Unified runner.** A single entry point that the
   implementer can write in Python or Bash; the legacy
   `runner/run_pmu*.sh` scripts become one of the backends.
   Must emit `Sample` records, not raw text.
4. **Probe normalization.** Wrap each of the three C probes
   so that:
   - They accept the normalized named arguments listed in
     §4.2.
   - They emit machine-readable output (JSON) instead of
     the current `printf` blobs.
   - Their output parses into a `Sample` record with
     `metrics` populated.
5. **`Sample` and `RunResult` population.** The dataclasses
   exist; you will need to add the executors that build
   them. Storage is git-ignored under `results/runs/` for
   raw, and `results/baselines/<version>/` for reviewed
   evidence.
6. **Smoke workflow.** A `make smoke` (or equivalent) that
   runs the most reduced profile end-to-end on Mac and on
   a temporary Linux ARM64 fixture, producing a structured
   `RunResult`. The smoke workflow is the literal "minimal
   smoke workflow" mentioned in the original Phase 2
   handoff.
7. **Gate 1 evidence recording.** A documented recipe for
   capturing the clean-checkout → `make smoke` →
   `probe doctor` → `probe restore` flow as RC evidence.

## 6. The hard "do not cross" lines

These are the boundaries the implementer will not negotiate
with you. State them in the contract; the implementer will
honor them.

### 6.1 Boundaries from the v1.0 design

- No `if platform == "gb10"` branches in `arm64_probe/`.
- Experiments declare required/optional capabilities, not
  platforms.
- `probe run` is the **only** new public mutation entry
  point. It does not bypass the existing
  `EnvironmentCoordinator`; it does not bypass the host-wide
  `MutationLock`; it does not bypass the `JournalStore`.
- `probe run` without `--allow-mutation` against a plan that
  requires host mutation is a structured `11` error
  *before* any host write, not a fallback.

### 6.2 Boundaries from the original Phase 2 handoff

- Do not modify `runner/run_pmu*.sh`, `data/`,
  `analysis/`, `baseline/`, or `runner/cache_info_*.sh`.
- Do not modify the production Linux state root
  (`/var/lib/arm64-uarch-probe`); only internal tests may
  inject a temporary root.
- Do not announce `GB10 Gate 1 is ready to run` until the
  unified runner, transaction/recovery flow, **and** the
  minimal smoke workflow all pass.
- Phase 3 must not produce GB10 measurement evidence on
  Mac. Mac validates software behavior only.

### 6.3 Boundaries from the toolchain pin (added in `b2ca03f`)

- Every Python invocation under this Makefile goes through
  `uv run --no-sync`. No raw `python3` in shell scripts,
  shebangs, or Makefile targets.
- The `probe` shebang is `#!/usr/bin/env -S uv run --no-sync
  python`. Do not change it back to `python3`.
- `requires-python = "==3.13.13"`. Do not relax this. If a
  future Python patch version is needed, bump it explicitly
  via `uv python install` and re-record the toolchain
  evidence.

## 7. Quality controls you should keep or strengthen

These are the quality bars Phase 2 established. You may add
to them; you should not weaken any.

| Bar | Where it lives | Phase 3 implication |
|---|---|---|
| TDD on every behavior change | enforced by reviewer, not CI | Add a `make test-first` (or just continue) pre-commit check that runs only the touched module. |
| Public schemas have contract tests | `tests/contract/test_public_schemas.py` | Add `sample.schema.json` and `run-result.schema.json` to `SCHEMA_REQUIRED`. |
| CLI surface is contract-tested | `tests/contract/test_cli_*.py` | Add `test_cli_run.py` and `test_cli_resume.py` covering the §4.2 examples. |
| Toolchain pin is contract-tested | `tests/contract/test_toolchain_contract.py` | Already covers `.python-version`, `pyproject.toml`, `uv.lock`, Makefile `uv run` routing. Do not relax. |
| Backend boundaries are contract-tested | `tests/contract/test_host_backend_contract.py` | Stable. |
| Phase 2 acceptance gate is contract-tested | `tests/contract/test_phase2_acceptance.py` | Add `test_phase3_acceptance.py` with the same shape. |
| Integration tests against fake controllers | `tests/integration/test_phase2_fixture_workflow.py` | Add a similar fixture workflow exercising `probe run` end-to-end against `FakeBackend` and the `EnvironmentCoordinator`. |
| Frozen-path integrity | `tests/test_repository_policy.py` | Stable. |

## 8. The plan file you will hand us (rough template)

Based on how Phase 2's plan was structured
(`docs/superpowers/plans/2026-06-14-phase2-backends-environment.md`),
your Phase 3 plan needs at minimum:

1. **Goal** and **architecture** paragraphs (2-3 sentences each).
2. **Tech stack** paragraph (the v1.0 design says
   "Python 3.10+ standard library" — we are now pinned to
   3.13.13, so write 3.13; the implementer will be told
   not to relax it).
3. **Delivery boundaries** — what Phase 3 does *not* do
   (no new public mutation entry points, no GB10
   measurements on Mac, no frozen-path modification, no
   public environment-apply command).
4. **File map** — explicit list of files the implementer
   is allowed to add or modify. Anything not on the list
   requires your sign-off.
5. **Public type contract** — fields and lifecycle of
   `Sample`, `RunResult`, and any new types (`ResumePlan`,
   etc.).
6. **Acceptance contract** — the per-criterion pass/fail
   you authored. Numbered AC1, AC2, … so the implementer
   can map them to tests.
7. **Task list** — Task 14, Task 15, …, each with file
   map, test map, commit message, and verification command.
8. **Completion gate** — the precise acceptance criteria
   that gate the user's review of Phase 3.

The implementer will copy this template shape and execute
task-by-task under TDD.

## 9. Commands and tools the implementer has at their disposal

- `make help` — list all targets.
- `make sync` — provision `.venv/` from `uv.lock` (run once
  per fresh checkout).
- `make check` — full Python test suite + shell syntax
  check.
- `make phase2-check` — equivalent today; will gain a
  Phase 3 equivalent.
- `make build` — build probes supported on the current
  host.
- `make doctor PROBE_ARGS='-o json'` — read-only host
  inspection.
- `make probe PROBE_ARGS='…'` — convenience wrapper.
- `git status --short` and `git diff --check` are
  mandatory before any commit.
- `uv run python -m unittest <module>` for single-module
  test runs.

## 10. The role split, restated for clarity

To make the boundary explicit one more time, after the user
acts on this handoff:

- **You (Phase 3 architect)** will write
  `docs/superpowers/plans/2026-MM-DD-phase3-probes-and-runner.md`
  containing only the **acceptance contract and the
  task-by-task plan**. The plan must reference the
  boundaries in §6 and the bars in §7. You will then hand
  back to the user for review.
- **We (Phase 3 implementers)**, after the user approves
  the plan, will execute the tasks under TDD, commit
  with focused messages, run `make check` and
  `git diff --check` before each commit, and never
  modify the frozen or transitional paths.
- **The user** reviews each task, approves and merges the
  Phase 3 branch into `main` (same flow as Phase 2:
  local `--no-ff` merge, preserve history), and arranges
  GB10 access for Gate 1.
- **Nobody** pushes to `origin` without an explicit user
  instruction (per the original Phase 2 handoff rule
  re-applied).
- **Only the user (or you, with user approval)**
  announces `GB10 Gate 1 is ready to run`. The
  implementer will surface the trigger condition but will
  not make the announcement.

## 11. If you find something missing

If, while authoring the acceptance contract, you discover
that some Phase 2 deliverable is incomplete, underspecified,
or unsafe for Phase 3 to build on, surface that as a
"Phase 2 follow-up" item in your plan. Do **not** silently
patch Phase 2 code in the same plan — open a separate
concern. The user's review of Phase 2 already passed, so
the contract should be additive, not subtractive.

Specifically, the questions you may want to raise (none of
which is a blocker; all are decisions the user can defer):

- Do you want `probe run` to be transactional at the **case**
  level (one transaction per case) or at the **phase**
  level (one transaction per environment phase, as Phase 2
  implies)? The design spec leaves this open.
- Should `probe resume` operate on a `RunResult` artifact
  on disk, or on a journal? The two have different
  cross-checkout semantics. Phase 2 journals are
  cross-checkout; `RunResult` artifacts are local.
- Do you want the smoke workflow to require `--allow-mutation`
  in CI? The current Phase 2 contract tests assert that
  `--allow-mutation` is required for any host write; the
  smoke workflow will need it if the plan includes any
  `host` requirement.

Bring these to the user via your acceptance contract's
"open questions" section. They are decisions, not bugs.

## 12. Sign-off

This handoff is closed on the date in the front matter. The
implementer waiting for your contract has confirmed:

- main is at `f852ad8` and clean.
- 241 tests pass under the pinned toolchain.
- No frozen or transitional paths have been modified.
- No GB10 hardware has been touched.
- No `python3` invocation exists outside `uv run`.
- The legacy `runner/run_pmu*.sh` scripts and `data/`
  evidence remain frozen and verified by
  `make legacy-check`.

When you author the Phase 3 plan, treat this file as
informational. The actual plan you write is the contract the
implementer follows; this file is the bridge.

Good luck. We are standing by.
