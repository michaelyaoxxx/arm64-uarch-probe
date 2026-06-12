# arm64-uarch-probe v1.0 Delivery Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved v1.0 GB10 research baseline through independently reviewable and testable implementation phases.

**Architecture:** The roadmap sequences repository stabilization, platform-independent domain modeling, capability-driven OS/platform backends, transactional environment control, unified scenario execution, structured results, and publication. Each phase has a separate detailed implementation plan written only after the prior phase's interfaces and acceptance evidence are reviewed.

**Tech Stack:** C11 probes, Python 3 standard-library runtime, Bash/system utilities on GB10, repository-managed Python development dependencies, Make, JSON/JSONL, GitHub branches/PRs/tags.

---

## Delivery Rules

- `michaelyaoxxx/arm64-uarch-probe` is the only authoritative repository.
- Preserve existing Git history and historical `data/`.
- Keep each phase on a reviewed feature branch; do not develop directly on `main`.
- Use TDD for code and contract changes.
- Mac runs continuous engineering checks; Linux ARM64 validates Linux behavior.
- GB10 is used only at the approved gates.
- Do not start a later phase until the preceding phase acceptance criteria pass.

## Plan Sequence

| Phase | Detailed Plan | Primary Outcome | GB10 Use |
|---|---|---|---|
| 0 | `2026-06-12-phase0-repository-contract.md` | Reproducible repository/build contract and frozen legacy evidence | None |
| 1 | `phase1-core-domain-and-cli.md` | Domain models, schemas, scenario catalog, help/list/show/plan contracts | None |
| 2 | `phase2-backends-and-environment.md` | Linux ARM64 backend, GB10 description, environment transactions and recovery | None; fixture/CI only |
| 3 | `phase3-probes-and-runner.md` | Normalized probes, executable scenarios, composition, profiles, resume | Gate 1 once |
| 4 | `phase4-analysis-and-methodology.md` | Historical import, statistics, figures, methodology, article comparison, roadmap | Gate 2 |
| 5 | `phase5-release-closure.md` | README, extension guide, RC baseline, release evidence | Gate 3 |

## Phase Acceptance Contracts

### Phase 0: Repository Contract and History Freeze

- `origin` points to `michaelyaoxxx/arm64-uarch-probe`.
- Legacy runner and raw-data files have a machine-verifiable integrity manifest.
- `make help`, `make show-targets`, `make build`, and `make check` reflect actual repository paths.
- Mac builds the currently portable probe subset; Linux builds all existing probes.
- Temporary runs are ignored while v1.0 baseline evidence remains trackable.
- Contributor and GitHub handoff rules are documented.

### Phase 1: Core Domain and CLI Contract

- Platform-independent immutable models define Capability, Platform, Experiment,
  Scenario, Case, Profile, Sample, and RunResult.
- Canonical scenario names and stable case IDs are tested.
- JSON schemas or equivalent validators cover manifests, environment records,
  cases, and errors.
- `probe --help`, subcommand help, `list`, `show`, and read-only `plan` satisfy
  the approved usage contract without platform probing or side effects.
- GB10 and Apple M4 fixtures pass the same platform contract tests.

### Phase 2: Backends and Environment Transactions

- Capability interfaces contain no experiment-specific or GB10-specific logic.
- Linux ARM64 backend implements inspection and control mechanisms.
- GB10 platform description contains topology facts, policies, and scenario
  defaults without runner logic.
- Environment transactions persist before/requested/effective/after states,
  lock mutation, restore on failure/signals, and recover unfinished journals.
- Darwin ARM64 behavior is represented by a contract-tested unsupported/minimal
  backend boundary; v1.0 does not claim M4 measurement support.

### Phase 3: Probes and Unified Runner

- Existing probe behavior is preserved behind normalized named arguments and
  machine-readable output.
- Cache and migration scenarios can run individually or in arbitrary
  combinations.
- Profiles, selectors, stable case IDs, deduplication, transaction phases,
  resume, and exact reruns work end to end.
- Makefile wraps the stable CLI and contains no experiment matrix logic.
- GB10 Gate 1 completes from a clean checkout and records toolchain evidence.

### Phase 4: Analysis, Figures, and Methodology

- Historical text logs import through tested adapters into the structured
  protocol.
- Analysis consumes only structured results and generates reproducible tables,
  figures, anomaly flags, and Markdown summaries.
- Methodology documents connect probe code to measurement principles and limits.
- Chips and Cheese comparison marks agreement, difference, methodological
  mismatch, and uncovered experiments.
- X925/A725 deep-dive roadmap covers ROB capacity, decode/dispatch width,
  execution resources, load/store behavior, branch prediction, and cache/TLB
  behavior.
- GB10 Gate 2 validates representative methods and output.

### Phase 5: Release Closure

- A fresh GB10 checkout can follow README through the smoke workflow.
- Extension guide explains how to add OS backends, hardware descriptions,
  experiments, scenarios, profiles, and reports.
- Fixed RC tag passes minimal regression smoke and the complete v1.0 profile.
- Published conclusions trace to structured cases, selected raw evidence, and
  an immutable commit/tag.
- Baseline evidence and figures are frozen before `v1.0.0`.

## Review Checkpoints

After each phase:

1. Verify all phase-specific automated checks.
2. Review repository diff for unrelated changes.
3. Review public interfaces and data formats before the next plan is written.
4. Commit phase acceptance evidence.
5. Merge through GitHub PR before beginning the next phase branch.

