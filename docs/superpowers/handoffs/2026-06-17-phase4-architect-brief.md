# Phase 4 Architect Brief

> **To:** Phase 4 architect agent
> **From:** Phase 3 implementation agent
> **Date:** 2026-06-17
> **Action:** Produce `docs/superpowers/handoffs/2026-06-17-phase4-handoff.md`

## 1. Current State

Phase 1-3 are complete and merged to `main` on `github.com/michaelyaoxxx/arm64-uarch-probe`.

Phase 3 delivered:
- 3 normalized probe adapters (`ChasePmuAdapter`, `EvictSlcAdapter`, `ChaseMigrateAdapter`)
- Unified `Runner` with environment-phase grouping
- Atomic `RunResultStore` (schema v2 + full provenance)
- `ResumeService` for failed-case re-execution
- `probe run` and `probe resume` CLI
- `make smoke` / `make phase3-check` wrappers
- GB10 Gate 1 verified: 365 tests pass, 2/2 smoke cases ok, 9/9 capabilities available
- Error pattern catalog P1-P5 with automated prevention layers A-G
- AC1-AC9 evidence matrix: `docs/superpowers/handoffs/2026-06-17-phase3-ac-evidence-matrix.md`

The `codex/phase3-implementation` branch mission is complete.

## 2. Immutable Architecture Constraints

These are **not** up for re-decision. The handoff must preserve them.

- **Immutable domain model:** all `dataclass(frozen=True)`, tuples for public interfaces
- **Capability-driven:** `capability_id` as universal currency; no `if platform == "gb10"` branches anywhere
- **Environment transactions:** `EnvironmentCoordinator` + `MutationLock` + `JournalStore` contract unchanged
- **Result boundary:** `results/runs/` git-ignored; promotion to `results/baselines/<version>/` is a separate reviewed action
- **Frozen paths:** `runner/`, `data/`, `analysis/`, `baseline/` must not be modified
- **Python toolchain:** CPython 3.13.13 + uv, zero external dependencies, pinned in `.python-version`/`pyproject.toml`/`uv.lock`
- **C probes:** single-measurement, no real-time monitoring; compiled via `make build`
- **Mutation:** requires `--allow-mutation` + caller privilege; CLI never invokes `sudo`
- **`main` branch strategy:** feature branch → merge to `main` only after full phase acceptance (single `--no-ff`)

## 3. Phase 4 Known Scope

From `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §1:

| Feature | Description |
|---------|-------------|
| `probe analyze` | Data analysis pipeline |
| `probe report` | Report generation |
| Figures | Charts and visualizations |
| Methodology conclusions | Microarchitecture analysis summary |
| v1.0 baseline measurements | Full GB10 baseline data collection |

## 4. Required Deliverable

**One file:**

```
docs/superpowers/handoffs/2026-06-17-phase4-handoff.md
```

Follow the format of `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md`.

**Must include:**

| Section | Content |
|---------|---------|
| §1 Objective and Scope | What Phase 4 delivers and what it defers to Phase 5+ |
| §2 Locked Architecture Decisions | Non-negotiable constraints (include §2 from this brief + add Phase 4 specifics) |
| §3 Required Public Behavior | CLI forms, exit codes, output formats |
| §4 Acceptance Criteria (AC1-ACn) | Each requiring automated evidence, never narrative alone |
| §5 Quality-Control Strategy | Test pyramid, per-task gate, phase completion gate |
| §6 AC-to-Task-to-Test Implementation Map | **Must explicitly map each AC to: files to create/modify, test files, commit boundary, and verification command.** This is the blueprint the implementation agent uses to produce SPEC + PLAN. |
| §7 Recommended Work Order | Dependency order for implementation agents |

**After the handoff is approved by the user:**
- The implementation agent writes the detailed SPEC and PLAN files
- Then implements task-by-task with TDD

**Handoff quality bar (Phase 3 reference):**
- `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` — 9 ACs, 6 tasks, each task maps AC → file → test → commit
- `docs/superpowers/specs/2026-06-15-phase3-probes-runner-design.md` — detailed design (produced by implementation agent from handoff)
- `docs/superpowers/plans/2026-06-15-phase3-probes-runner.md` — task-by-task implementation plan (produced by implementation agent from handoff)

## 5. Must-Read Documents

```
docs/superpowers/handoffs/2026-06-15-phase3-handoff.md          ← Format reference
docs/superpowers/handoffs/2026-06-17-phase3-ac-evidence-matrix.md ← Current evidence
CLAUDE.md                                                       ← Full architecture + constraints
docs/design/repository-contract.md                               ← Result retention policy
docs/design/repository-layout.md                                 ← Path ownership
docs/design/cli-contract.md                                      ← CLI surface
```
