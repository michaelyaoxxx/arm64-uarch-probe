# Phase 3 Probes and Unified Runner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Companion design:** `docs/superpowers/specs/2026-06-15-phase3-probes-runner-design.md`.
> **Architect contract:** `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` (AC1–AC9, locked architecture, quality controls).

**Goal:** Implement the unified measurement runner. Concretely, ship `probe run`, `probe resume`, atomic `RunResult` persistence, and the `make smoke` / `make phase3-check` wrappers, all behind the existing `EnvironmentCoordinator` and the pinned CPython 3.13.13 toolchain — without touching any frozen or transitional path, without an `if platform == "gb10"` branch anywhere, and without claiming GB10 Gate 1 readiness on the architect's behalf.

**Architecture:** Phase 3 is additive on top of Phase 2. The `Runner` consumes the existing `Plan` from `Planner`, groups cases by `EnvironmentPhase`, and calls `EnvironmentCoordinator.execute` once per phase. Inside each `execute` call, a `work` closure drives per-case `ProbeAdapter` invocations through an injected `CommandExecutor`. The runner never parses probe output itself; each `ProbeAdapter` does. Results accumulate into `RunResult` records (schema v2, with `case_definitions_signature`, `repository_commit`, `toolchain`, `prior_run_id`, `resume_kind`) and land atomically under `results/runs/<run_id>.json` (git-ignored). `probe resume` reads a prior `RunResult`, validates four compatibility fields strictly (no auto-conversion), diffs sample state, and re-runs only `error` cases. Two new `ExitCode` values (`15`, `16`) complete the exit-code ladder; the rest of the `0`-`14` matrix from Phase 2 is unchanged.

**Tech Stack:** Python 3.13.13 (uv-managed, pinned in `.python-version`/`pyproject.toml`/`uv.lock`); the standard library; existing `arm64_probe` packages. C probes continue to build via `make build` and execute via `subprocess.run(argv, shell=False, text=True, capture_output=True, timeout=60)` driven by the injected `CommandExecutor` protocol from `arm64_probe/backends/io.py:19`. JSON Schema 2020-12 for the public schemas. Make, Git.

## Delivery Boundaries

- All development, characterization, and acceptance runs happen on
  Mac or on temporary Linux sysfs/procfs fixture trees. **No GB10
  hardware is touched.** GB10 Gate 1 readiness is announced only by
  the user; this plan ends with a runbook, not an announcement.
- Phase 3 must **not** modify `runner/run_pmu*.sh`, `data/`,
  `analysis/`, `baseline/`, or `runner/cache_info_*.sh`. A frozen
  legacy-wrapper adapter is documented but **not** registered on
  the `probe run` happy path; if a follow-up task needs it, that
  task is a separate, scoped concern.
- The Phase 2 architecture, the toolchain pin, the environment
  transaction model, and the journal / lock / restoration
  contract are **not** re-decided. The plan re-uses
  `EnvironmentCoordinator.execute`, `JournalStore._atomic_write`,
  and the existing `ControllerRequest` ordering. No new public
  mutation entry point is introduced; `probe run` is the only
  such entry point added in Phase 3.
- The Makefile is extended with **only** the thin `smoke` and
  `phase3-check` wrappers. No scenario matrix, no platform-name
  branch, no probe output parser, no mutation logic, no result
  logic appears in the Makefile.
- Public mutation in `probe run` requires both `--allow-mutation`
  and the caller's privilege. The CLI never invokes `sudo` and
  never accepts a public `--state-root` override.
- The Python toolchain stays at `==3.13.13`. No version bump,
  no new dependency, no relaxation of `requires-python`.
- The `probe` shebang (`uv run --no-sync python`) is unchanged.
- `probe analyze` and `probe report` are **out of scope** (Phase 4).

## Architecture Decision Anchors (from the spec §12)

This plan's tasks implement the design as it stands in the spec.
The 9 architectural decisions captured by the brainstorming flow
are anchored here for the implementer:

| # | Decision | Implemented in |
|---|---|---|
| 1 | Transaction granularity: per environment phase, not per case (handoff §2.1) | Task 17 (`Runner` algorithm step 2) |
| 2 | Resume data source: prior `RunResult` (handoff §2.2) | Task 19 (`ResumeService`) |
| 3 | `EvictSlcAdapter` registered against synthetic `evict-slc.setup`, not in `probe run` happy path | Task 15 (Step 5) |
| 4 | Schema `1 → 2` upgrade: strict reject on resume (exit `16`) | Task 16 (`RunResultStore.validate_compatibility`) and Task 19 (`ResumeService` abort path) |
| 5 | Resume sample state machine: re-record `error`, carry `ok`, drop `skipped` | Task 19 (Step 3) |
| 6 | Default case timeout: 60 seconds (override via `--case-timeout` / `--no-case-timeout`) | Task 17 (Step 3, `Runner` argv builder) and Task 18 (parser) |
| 7 | Characterization fixture capture: hand-rolled byte-for-byte snapshots documented in a code-handoff, no `tests/support/capture.py` | Task 14 (Step 3) |
| 8 | Mutation boundary: `--allow-mutation` required when plan has `host` requirements (Phase 2 contract re-applied) | Task 18 (Step 4) |
| 9 | GB10 Gate 1 runbook commit: included in the Phase 3 acceptance commit | Task 20 (Step 8) |

## File Map

### New modules (additive under `arm64_probe/`)

- `arm64_probe/execution/__init__.py`
- `arm64_probe/execution/adapters/__init__.py`
- `arm64_probe/execution/adapters/base.py` — `ProbeAdapter` Protocol + `ProbeOutcome` dataclass + `ProbeFailure` / `ProbeFailureMode` records
- `arm64_probe/execution/adapters/chase_pmu.py` — `ChasePmuAdapter`
- `arm64_probe/execution/adapters/evict_slc.py` — `EvictSlcAdapter` (registered against a synthetic setup scenario)
- `arm64_probe/execution/adapters/chase_migrate.py` — `ChaseMigrateAdapter`
- `arm64_probe/execution/adapters/legacy_wrapper.py` — documentation-only stub; not registered for execution
- `arm64_probe/execution/runner.py` — `Runner` and `RunRequest` / `ToolchainEvidence` records
- `arm64_probe/execution/result_store.py` — `RunResultStore` + `case_definitions_signature`
- `arm64_probe/execution/resume.py` — `ResumeService`

### Additions to existing modules

- `arm64_probe/errors.py` — add `PROBE_EXECUTION = 15`,
  `RUN_RESULT = 16` to `ExitCode`; the handoff contract test
  asserts both exist.
- `arm64_probe/domain/models.py` — extend `RunResult` with
  `prior_run_id: str | None = None` and
  `resume_kind: str | None = None` (frozen dataclass; new
  fields, default `None`, no breaking change to existing
  consumers because the new fields are optional).
- `arm64_probe/serialization/model_json.py` — extend
  `to_data()` for `Sample`, `RunResult`, `ToolchainEvidence`;
  bump `RunResult` `schema_version` to `2` (see Task 16).
- `arm64_probe/cli/parser.py` — add `run` and `resume`
  subcommands; extend `COMMANDS` to include them.
- `arm64_probe/cli/main.py` — dispatch `run` and `resume`;
  resolve `Platform` exactly as `plan` does.
- `arm64_probe/cli/render.py` — add `render_run`, `render_resume`
  (table and JSON branches).
- `Makefile` — add `smoke` and `phase3-check` targets; extend
  the `help` text and `.PHONY` list.
- `schemas/sample.schema.json` — add optional `toolchain` object.
- `schemas/run-result.schema.json` — add optional
  `summary.case_definitions_signature`,
  `summary.repository_commit`, `summary.dirty_tree`,
  `summary.toolchain`, `summary.prior_run_id`,
  `summary.resume_kind`, `environment.toolchain`; document
  the `schema_version` bump to `2`.
- `tests/support/fake_coordinator.py` — new
- `tests/support/fake_adapter.py` — new
- `tests/support/executor_recorder.py` — new
- `tests/fixtures/probe_output/chase_pmu_v2.7.3/` — new
  (captured stdout/stderr fixtures for `chase_pmu`)
- `tests/fixtures/probe_output/evict_slc_v1.2/` — new
- `tests/fixtures/probe_output/chase_migrate_v1.0/` — new

### Tests (additive)

- `tests/unit/test_characterization_probes.py`
- `tests/unit/test_chase_pmu_adapter.py`
- `tests/unit/test_evict_slc_adapter.py`
- `tests/unit/test_chase_migrate_adapter.py`
- `tests/unit/test_runner.py`
- `tests/unit/test_result_store.py`
- `tests/unit/test_resume.py`
- `tests/contract/test_cli_run.py`
- `tests/contract/test_cli_resume.py`
- `tests/contract/test_run_plan_equivalence.py`
- `tests/contract/test_exit_codes.py`
- `tests/contract/test_probe_adapters.py`
- `tests/integration/test_phase3_smoke_workflow.py`
- `tests/integration/test_phase3_resume_workflow.py`
- `tests/integration/test_phase3_signal_restore.py`
- `tests/integration/test_phase3_fixture_workflow.py`
- `tests/test_makefile_contract.py` — extended (existing file)

### Frozen / transitional paths (must not change)

`runner/`, `data/`, `analysis/`, `baseline/`, `runner/cache_info_*.sh`. Any of these touched by an accidental commit fails the Phase 3 Completion Gate.

### Code-handoff document (added in Task 14, not committed in this plan)

- `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md` — captures the exact `subprocess.run` argv and capture flags for each fixture file; the implementer hand-rolls the fixture bytes per this document.

## Public Type Contract (additive to Phase 2)

```python
# arm64_probe/errors.py
class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    CONFIG = 3
    CAPABILITY = 4
    PLANNING = 5
    HOST_INSPECTION = 10
    MUTATION_AUTHORIZATION = 11
    ENVIRONMENT_APPLY = 12
    ENVIRONMENT_RESTORE = 13
    ENVIRONMENT_BUSY = 14
    PROBE_EXECUTION = 15   # NEW
    RUN_RESULT = 16        # NEW


# arm64_probe/execution/adapters/base.py
@dataclass(frozen=True)
class ProbeFailure:
    stage: str         # "launch" | "timeout" | "exit" | "parse" | "signal"
    category: str
    message: str


@dataclass(frozen=True)
class ProbeFailureMode:
    stage: str
    category: str
    regex: str          # matched against the probe's stderr for diagnostics


@dataclass(frozen=True)
class ProbeOutcome:
    status: str                                    # "ok" | "error" | "skipped"
    metrics: tuple[tuple[str, JsonScalar], ...]
    evidence: tuple[str, ...]
    failure: ProbeFailure | None


class ProbeAdapter(Protocol):
    adapter_id: str
    scenario_id: str
    schema_version: int
    @property
    def supported_cpu_modes(self) -> tuple[str, ...]: ...
    def build_argv(self, request: RunRequest) -> tuple[str, ...]: ...
    def parse_output(
        self, *, stdout: str, stderr: str, exit_code: int, timed_out: bool
    ) -> ProbeOutcome: ...
    def known_failure_modes(self) -> tuple[ProbeFailureMode, ...]: ...


# arm64_probe/execution/runner.py
@dataclass(frozen=True)
class ToolchainEvidence:
    python_version: str
    uv_version: str
    cc: str
    host_os: str


# arm64_probe/domain/models.py  (additive; existing fields preserved)
@dataclass(frozen=True)
class RunResult:
    run_id: str
    plan: Plan
    samples: tuple[Sample, ...]
    summary: tuple[tuple[str, JsonScalar], ...]
    environment: tuple[tuple[str, JsonScalar], ...]
    schema_version: int = 2
    prior_run_id: str | None = None
    resume_kind: str | None = None
```

Apply order: `linux.cpufreq`, `linux.hugepage`,
`linux.transparent-hugepage` (re-used unchanged from Phase 2
`CONTROLLER_ORDER`).

Controller IDs (re-used unchanged from Phase 2):
`linux.cpufreq`, `linux.hugepage`,
`linux.transparent-hugepage`. No new controller is added
in Phase 3.

## Public Behavior Contract

The detailed design (§3 of the spec) freezes these forms. The
plan's contract tests below assert each one.

```text
# Spec §3.2
probe run cache-latency/l1-latency
probe run cache-latency/l2-latency cache-latency/dram-latency
probe run migration-latency/cross-cluster
probe run cache-latency
probe run --profile smoke
probe run --case <stable-case-id>
probe run --platform gb10 --profile baseline --output-dir /tmp/runs
probe run --platform gb10 --profile smoke --allow-mutation
probe run --platform gb10 --profile smoke --case-timeout 30

# Spec §3.3
probe resume --run <run-result-path>
probe resume --run <run-result-path> --output-dir /tmp/runs
probe resume --run <run-result-path> --allow-mutation
```

Exit codes: `0` success; `2` usage; `3` config; `4` capability;
`5` planning; `10` host inspection; `11` mutation
authorization; `12` apply/work failure (restoration
succeeded); `13` restore failure; `14` active lock or
unfinished journal; **15 probe execution**; **16 run
result**. A partial `RunResult` is always written for an
invocation with any failed case (status `15`); restore
failure takes priority (`13`).

## Phase 3 Acceptance Criteria (mapped to plan tasks)

These criteria are the handoff's AC1–AC9, restated for the
implementer with the test path that proves each one. Every
criterion must be closed by automated evidence, not narrative
assertion.

| AC | Proven by | Covered in |
|---|---|---|
| AC1 Normalized probe contract | `tests/contract/test_probe_adapters.py`, `tests/unit/test_characterization_probes.py`, `tests/unit/test_chase_pmu_adapter.py` (and siblings) | Task 14, Task 15 |
| AC2 Selection and composition | `tests/contract/test_run_plan_equivalence.py`, `tests/contract/test_cli_run.py` (selection + `--case`) | Task 18, Task 19 |
| AC3 Transactional execution | `tests/unit/test_runner.py`, `tests/integration/test_phase3_signal_restore.py` | Task 17 |
| AC4 Structured results and provenance | `tests/unit/test_result_store.py`, `tests/contract/test_public_schemas.py` (extended), `tests/unit/test_characterization_probes.py` | Task 15, Task 16, Task 20 |
| AC5 Resume and exact rerun | `tests/unit/test_resume.py`, `tests/contract/test_cli_resume.py`, `tests/integration/test_phase3_resume_workflow.py` | Task 19 |
| AC6 Stable CLI and Makefile | `tests/contract/test_cli_run.py`, `tests/contract/test_cli_resume.py`, `tests/test_makefile_contract.py` (extended) | Task 18, Task 19, Task 20 |
| AC7 Compatibility and boundaries | `tests/contract/test_phase2_acceptance.py` (extended), `tests/contract/test_repository_policy.py` (extended), `tests/contract/test_public_schemas.py` (extended) | Task 20 |
| AC8 Minimal smoke workflow | `tests/integration/test_phase3_smoke_workflow.py`, `tests/integration/test_phase3_fixture_workflow.py`, `tests/test_makefile_contract.py` (extended), the live `make smoke` target | Task 20 |
| AC9 GB10 Gate 1 runbook | the runbook subsection of the Phase 3 Completion Gate (in this plan, "Phase 3 Completion Gate" §1.1) | Task 20 |

## AC → Task → Test map

| AC | Task that closes it | Verifying test(s) |
|---|---|---|
| AC1 | Task 14 (characterization), Task 15 (adapters) | `test_characterization_probes.py`, `test_chase_pmu_adapter.py`, `test_evict_slc_adapter.py`, `test_chase_migrate_adapter.py`, `test_probe_adapters.py` |
| AC2 | Task 18 (runner + `probe run`) | `test_run_plan_equivalence.py`, `test_cli_run.py`, `test_runner.py` (selection-by-profile and exact-case-id subsets) |
| AC3 | Task 17 (runner / coordinator integration) | `test_runner.py`, `test_phase3_signal_restore.py` |
| AC4 | Task 16 (result store + serialization) | `test_result_store.py`, `test_public_schemas.py` (extended), `test_characterization_probes.py` (sample round-trip) |
| AC5 | Task 19 (resume + `probe resume`) | `test_resume.py`, `test_cli_resume.py`, `test_phase3_resume_workflow.py` |
| AC6 | Task 20 (Makefile wrappers + extended CLI) | `test_cli_run.py`, `test_cli_resume.py`, `test_makefile_contract.py` (extended) |
| AC7 | Task 20 (boundary tests) | `test_phase2_acceptance.py` (extended), `test_repository_policy.py` (extended), `test_public_schemas.py` (extended) |
| AC8 | Task 20 (smoke workflow) | `test_phase3_smoke_workflow.py`, `test_phase3_fixture_workflow.py`, `test_makefile_contract.py` (extended) |
| AC9 | Task 20 (runbook) | the runbook subsection of the Phase 3 Completion Gate is reviewed by the architect |

## Test Taxonomy

- **Unit** (`tests/unit/`): argument normalization, output
  parsing, process outcomes, result assembly/storage, resume
  diffing, phase grouping, schema-version compatibility.
- **Contract** (`tests/contract/`): CLI examples, schemas,
  exit codes, plan/run equivalence, capability-driven
  boundaries, frozen paths, uv/Makefile rules, exit-code
  ladder.
- **Integration** (`tests/integration/`): fake process
  executor + fake backend + real coordinator; exhaustive
  failure/signal/timeout restoration; result persistence
  and resume.
- **Host validation** (run on Mac; future Linux ARM64):
  build, fixture smoke, `probe doctor` round-trip.

All behavior changes use TDD. Fault-injection tests are
mandatory at each external boundary: process start, output
parse, sample persistence, journal transition, work callback,
restoration, and resume persistence.

## Per-Task Gate

Before each focused commit:

```sh
uv run --no-sync python -m unittest <focused-modules> -v
make check
make legacy-check
git diff --check
git status --short
```

Each commit owns one coherent behavior and its tests. Do not
combine probe normalization, runner orchestration, resume, and
acceptance closure in one commit.

## Phase Completion Gate

Before final architect review (mirrors the handoff §5
"Phase Completion Gate"):

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

The implementation agents must provide an **AC1–AC9 evidence
matrix** containing the criterion, proving test/command,
result, and artifact path. No criterion may be closed by
narrative assertion alone.

### 1. GB10 Gate 1 runbook (only after AC1–AC8 close)

AC9 is a **runbook**, not an automated test. The implementer
produces a Markdown runbook in
`docs/superpowers/handoffs/2026-06-15-phase3-gate1-runbook.md`
(added in Task 20, **committed together with the acceptance
evidence** in Task 20 Step 11) with the exact steps the user
will execute on GB10, in this order:

1. Record the commit SHA and confirm `git status` is clean.
2. Capture pinned toolchain evidence:
   `uv run --no-sync python -V`, `uv --version`, `cc --version`,
   `uname -srm`.
3. Run `make build`; record the produced binaries and
   `file build/bin/chase_pmu` etc.
4. Run `make phase3-check`; record the final test count and
   status.
5. Run `./probe doctor -o json`; save the artifact.
6. Run `./probe plan --platform gb10 --profile smoke -o
   json`; save the artifact.
7. Run
   `./probe run --platform gb10 --profile smoke --allow-mutation
   --output-dir results/gate1-runs`; record the produced
   `RunResult` JSON path and the journal path.
8. Run `./probe doctor -o json` again; confirm
   `journals` is empty and `restoration_status` is
   `succeeded` for the just-written journal.
9. Do **not** add resume / rerun invocations on GB10 merely
   for Gate 1; the AC5 fixture evidence on Mac / Linux
   ARM64 already proves them.

The runbook is the **only** deliverable AC9 requires from the
implementer. Gate 1 execution itself is the user's
responsibility; only the user announces
`GB10 Gate 1 is ready to run`.

---

## Batch 1: Characterization + Probe Adapters

### Task 14: Capture and Lock the Current Probe Output

**Files:**
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/warm-32KiB.stdout.txt`
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/warm-32KiB.stderr.txt`
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/cold-64MiB.stdout.txt`
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/cold-64MiB.stderr.txt`
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/quiet-default.stdout.txt` (empty)
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/quiet-default.stderr.txt`
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/verbose.stdout.txt`
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/verbose.stderr.txt`
- Create: `tests/fixtures/probe_output/chase_migrate_v1.0/cross-cluster.stdout.txt`
- Create: `tests/fixtures/probe_output/chase_migrate_v1.0/cross-cluster.stderr.txt`
- Create: `tests/unit/test_characterization_probes.py`
- Create: `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md` (code-handoff only; not part of the spec/plan acceptance)

- [ ] **Step 1: Write failing characterization tests**

  In `tests/unit/test_characterization_probes.py`, for each
  probe and capture variant, assert that the expected
  fixture file exists and that the current C probe's textual
  output matches a recorded baseline. Each test must read
  the fixture and assert byte-for-byte equality; this is the
  behavior-pinning layer that the handoff requires. Example:

  ```python
  def test_chase_pmu_warm_32kib_output_pinned(self):
      fixture = (FIXTURES / "chase_pmu_v2.7.3"
                 / "warm-32KiB.stdout.txt").read_text()
      self.assertIn("=== chase_pmu v2.7.3 ===", fixture)
      self.assertIn(">>> latency =", fixture)
      self.assertRegex(fixture, r"elapsed=\d+ ns")
  ```

  Mark the assertion that compares against live probe output
  with `# TODO(phase-3): populate live fixtures via deferred
  capture script`.

- [ ] **Step 2: Run focused tests and verify they fail**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_characterization_probes -v
  ```

  Expected: FAIL (no fixtures, no module).

- [ ] **Step 3: Document the capture procedure in a code-handoff**

  Create
  `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md`
  with the exact `subprocess.run(argv, shell=False, text=True,
  capture_output=True, timeout=60)` invocation needed to
  populate each fixture file. Working directory after
  `make build` is `build/bin/`. The handoff does **not**
  ship an in-tree capture script; the rationale is in
  spec §8.4. The handoff document is informational, not
  part of the contract tests.

- [ ] **Step 4: Hand-roll fixtures for offline CI**

  The characterization tests must pass on Mac and in CI
  without running the C probes. Hand-roll the fixtures by
  copying representative output from the existing
  `runner/run_pmu*.sh` invocations (or from a one-shot
  `make build` + manual probe invocation, if the user
  authorizes that). Each fixture is a byte-for-byte snapshot
  of stdout or stderr; tests assert presence of the
  structural anchors only (e.g. `=== chase_pmu v2.7.3 ===`,
  `>>>` markers, `lat=` substrings).

- [ ] **Step 5: Run tests and commit**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_characterization_probes -v
  make check
  make legacy-check
  git diff --check
  git add tests/fixtures/probe_output tests/unit/test_characterization_probes.py
  git add docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md
  git commit -m "Pin current probe textual output as characterization fixtures"
  ```

  Expected: focused tests and the Phase 1+2 suite (241 + N
  characterization tests) pass.

### Task 15: Implement the Three Probe Adapters and Their Public Protocol

**Files:**
- Create: `arm64_probe/execution/__init__.py`
- Create: `arm64_probe/execution/adapters/__init__.py`
- Create: `arm64_probe/execution/adapters/base.py`
- Create: `arm64_probe/execution/adapters/chase_pmu.py`
- Create: `arm64_probe/execution/adapters/evict_slc.py`
- Create: `arm64_probe/execution/adapters/chase_migrate.py`
- Create: `arm64_probe/execution/adapters/legacy_wrapper.py` (doc-only stub)
- Create: `tests/unit/test_chase_pmu_adapter.py`
- Create: `tests/unit/test_evict_slc_adapter.py`
- Create: `tests/unit/test_chase_migrate_adapter.py`
- Create: `tests/contract/test_probe_adapters.py`
- Create: `tests/support/fake_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

  For each adapter:

  - `build_argv` test: assert exact argv tuples for
    representative request dataclasses.
  - `parse_output` test: feed the captured fixture strings
    (Task 14), assert `status == "ok"` and the exact
    `metrics` tuple.
  - `parse_output` failure tests: empty stdout, nonzero
    exit, `timed_out=True`, malformed `>>>` line.
  - `supported_cpu_modes` test: assert the returned tuple
    matches the scenario's `cpu_mode` from
    `configs/experiments/*.json`.

- [ ] **Step 2: Run focused tests and verify they fail**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_chase_pmu_adapter -v
  ```

  Expected: FAIL (no module).

- [ ] **Step 3: Implement the `ProbeAdapter` Protocol and base dataclasses**

  In `arm64_probe/execution/adapters/base.py`:

  - `ProbeFailure` and `ProbeFailureMode` (frozen dataclasses).
  - `ProbeOutcome` (frozen dataclass with `status`,
    `metrics`, `evidence`, `failure`).
  - `ProbeAdapter` Protocol with the four members from
    the public type contract.
  - An `AdapterRegistry` mapping `scenario_id` to
    `ProbeAdapter`. Population happens at module import
    time in `arm64_probe/execution/adapters/__init__.py`.

- [ ] **Step 4: Implement `ChasePmuAdapter`**

  `arm64_probe/execution/adapters/chase_pmu.py`:

  - `ChasePmuArgs(size_kb: int, warm: int, force_rounds: int = 0,
    seed: int = 0, clflush: int = 0, hugepage: int = 0,
    cpu: int | None = None)` (frozen).
  - `ChasePmuAdapter` with `scenario_id` matching the
    `cache-latency.*` scenarios.
  - `build_argv`: when `cpu is not None`, prefix with
    `("taskset", "-c", str(cpu))`. Otherwise, the probe
    binary argv is exactly the seven positional
    `chase_pmu` expects.
  - `parse_output`: regex-extract `elapsed=`, `accesses=`,
    `latency =` from stdout. If `warm=0 && force_rounds=1`,
    parse both `src_latency` and the `migrate_latency`
    fallback to the cold-DRAM semantic. On nonzero exit
    or missing `>>>` marker, return
    `status="error"`, `failure=ProbeFailure("exit", ...)`
    or `ProbeFailure("parse", ...)`.

- [ ] **Step 5: Implement `EvictSlcAdapter`**

  `arm64_probe/execution/adapters/evict_slc.py`:

  - Registered against the synthetic `evict-slc.setup`
    scenario. The runner does not dispatch to it from
    `probe run --profile smoke`; it exists for
    completeness and for future direct invocation. The
    `ChasePmuAdapter` cold-DRAM path does **not** call
    `evict_slc` itself; the integration plan (Task 17)
    arranges the order if needed.
  - `EvictSlcArgs(evict_mb: int = 64, seed: int = 42,
    seq: bool = False, random: bool = True, touch_init:
    bool = True, verbose: bool = False)`.
  - `build_argv`: emit long-form flags by default;
    positional `[evict_mb] [seed]` accepted for
    backward-compat.
  - `parse_output`: on `--quiet` (default) stdout is
    empty; the adapter extracts `approx_bw`, `evict_ms`,
    `touch_ms` from stderr regex. On `--verbose` the
    adapter extracts the same plus the runtime header.

- [ ] **Step 6: Implement `ChaseMigrateAdapter`**

  `arm64_probe/execution/adapters/chase_migrate.py`:

  - `ChaseMigrateArgs(src_cpu: int, dst_cpu: int,
    size_kb: int, warm_src: int = 5, measure_rounds: int =
    1, measure_src: bool = True, seed: int = 42,
    hugepage: bool = True, strict_hugepage: bool = True,
    sleep_us: int = 0, label: str | None = None)`.
  - `scenario_id` matches `migration-latency.*`. The
    adapter's `build_argv` is identical to the existing
    C probe's `getopt_long` invocation. The runner passes
    the right `cpu_mode` (`pair-same-core`,
    `pair-same-cluster`, `pair-cross-cluster`) via the
    Plan's `Case` selection, but the argv itself is
    platform-agnostic.
  - `parse_output`: extract the three `>>>` markers
    (`src_latency`, `migrate_latency`, `migrate_penalty`).
    On `cpu_before != src_cpu` or `cpu_after != dst_cpu`,
    return `status="error", failure=ProbeFailure("parse",
    "affinity_lost")`.

- [ ] **Step 7: Implement the doc-only `legacy_wrapper.py`**

  `arm64_probe/execution/adapters/legacy_wrapper.py` is a
  single `@dataclass(frozen=True) class LegacyWrapperAdapter`
  whose `parse_output` raises
  `NotImplementedError("legacy wrapper is documentation only
  for Phase 3")`. The class docstring states that a future
  task may register it against a synthetic
  `legacy.run-pmu-v2.7.7` scenario that calls
  `runner/run_pmu_v2.7.7.sh` for behavior preservation; the
  Phase 3 happy path does not register it.

- [ ] **Step 8: Run focused tests and commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.unit.test_chase_pmu_adapter \
    tests.unit.test_evict_slc_adapter \
    tests.unit.test_chase_migrate_adapter \
    tests.contract.test_probe_adapters -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/execution tests/unit/test_chase_pmu_adapter.py \
    tests/unit/test_evict_slc_adapter.py \
    tests/unit/test_chase_migrate_adapter.py \
    tests/contract/test_probe_adapters.py \
    tests/support/fake_adapter.py
  git commit -m "Add normalized probe adapters behind ProbeAdapter protocol"
  ```

  Expected: all focused tests pass; AC1 closes.

## Batch 2: Result Persistence and Runner

### Task 16: Add the Atomic `RunResultStore` and Bump `RunResult` Schema to v2

**Files:**
- Modify: `arm64_probe/errors.py` (add `PROBE_EXECUTION = 15`, `RUN_RESULT = 16`)
- Modify: `arm64_probe/domain/models.py` (extend `RunResult` with `prior_run_id`, `resume_kind`; default both to `None`; set `schema_version` default to `2`)
- Modify: `arm64_probe/serialization/model_json.py` (extend `to_data` for the new fields and the new `ToolchainEvidence`)
- Modify: `schemas/sample.schema.json` (add `toolchain` object)
- Modify: `schemas/run-result.schema.json` (add `summary.*` and `environment.toolchain`)
- Create: `arm64_probe/execution/result_store.py`
- Create: `tests/unit/test_result_store.py`
- Create: `tests/support/fake_coordinator.py`

- [ ] **Step 1: Write failing `ExitCode` and schema contract tests**

  In `tests/contract/test_exit_codes.py`:

  ```python
  from arm64_probe.errors import ExitCode

  class ExitCodeContractTests(unittest.TestCase):
      def test_phase_3_codes_exist(self):
          self.assertEqual(ExitCode.PROBE_EXECUTION, 15)
          self.assertEqual(ExitCode.RUN_RESULT, 16)
  ```

  In `tests/contract/test_public_schemas.py` (extended
  with the new keys), assert
  `run-result.schema.json` requires
  `summary.case_definitions_signature`,
  `summary.repository_commit`, `summary.dirty_tree`,
  `summary.toolchain`, `summary.prior_run_id`,
  `summary.resume_kind`, `environment.toolchain`.

- [ ] **Step 2: Run focused tests and verify they fail**

  ```sh
  uv run --no-sync python -m unittest tests.contract.test_exit_codes -v
  uv run --no-sync python -m unittest tests.contract.test_public_schemas -v
  ```

  Expected: FAIL (no new codes, no new schema fields).

- [ ] **Step 3: Add `ExitCode` members and extend the dataclass**

  In `arm64_probe/errors.py`:

  ```python
  class ExitCode(IntEnum):
      ...
      ENVIRONMENT_BUSY = 14
      PROBE_EXECUTION = 15   # probe launch, timeout, signal, nonzero exit, malformed output
      RUN_RESULT = 16        # run-result read, validation, compatibility, or persistence failure
  ```

  In `arm64_probe/domain/models.py`, extend
  `RunResult` (preserving the existing field order so that
  any positional construction in tests still works):

  ```python
  @dataclass(frozen=True)
  class RunResult:
      run_id: str
      plan: Plan
      samples: tuple[Sample, ...]
      summary: tuple[tuple[str, JsonScalar], ...]
      environment: tuple[tuple[str, JsonScalar], ...]
      schema_version: int = 2
      prior_run_id: str | None = None
      resume_kind: str | None = None
  ```

  Add `from __future__ import annotations` import if not
  already present.

- [ ] **Step 4: Extend `to_data` for the new fields**

  In `arm64_probe/serialization/model_json.py`, the
  `RunResult` branch must emit `schema_version`,
  `prior_run_id`, and `resume_kind` (the latter two as
  `None` when unset). Add a `to_data_toolchain_evidence`
  branch and a `to_data_sample_toolchain` branch.

- [ ] **Step 5: Extend the public schemas**

  `schemas/sample.schema.json`: add the optional `toolchain`
  object (sub-schema reuse is fine; `additionalProperties:
  false` is preserved). The new fields are **optional**;
  the existing required-key set is unchanged.

  `schemas/run-result.schema.json`: add the optional
  `summary.case_definitions_signature`,
  `summary.repository_commit`, `summary.dirty_tree`,
  `summary.toolchain`, `summary.prior_run_id`,
  `summary.resume_kind`, `environment.toolchain`. All
  optional. `additionalProperties: false` is preserved.

  The `RunResult` `schema_version` field is now part of
  the public contract; bump the schema docstring in the
  contract test to reflect `2`.

- [ ] **Step 6: Write failing `RunResultStore` tests**

  In `tests/unit/test_result_store.py`:

  - `test_write_local_creates_atomic_file` — assert the
    temp + replace pattern.
  - `test_read_rejects_outside_root` — symlink parent
    test.
  - `test_read_rejects_oversize` — `MAX_RESULT_BYTES = 1
    MiB`.
  - `test_validate_compatibility_rejects_schema_version_mismatch`
    — `schema_version=1` prior + current `RunResult`
    raises `ProbeError(16)`.
  - `test_validate_compatibility_rejects_case_definitions_signature_mismatch`.
  - `test_validate_compatibility_rejects_repository_id_mismatch`.
  - `test_validate_compatibility_rejects_platform_id_mismatch`.

- [ ] **Step 7: Implement `RunResultStore`**

  In `arm64_probe/execution/result_store.py`:

  - Re-use the `JournalStore._atomic_write` pattern
    (`arm64_probe/environment/journal.py:338`): write to
    `.<run_id>.<uuid>.tmp`, `fsync`, `os.replace`,
    parent `fsync`, owner/mode check.
  - `validate_compatibility` checks
    `schema_version`, `platform_id`, `repository_id`,
    `repository_commit`, and
    `case_definitions_signature` (computed over the
    `Plan`).
  - `MAX_RESULT_BYTES = 1024 * 1024`.
  - `read` validates `schema_version == 2`.

- [ ] **Step 8: Run tests and commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.contract.test_exit_codes \
    tests.contract.test_public_schemas \
    tests.unit.test_result_store -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/errors.py arm64_probe/domain/models.py \
    arm64_probe/serialization/model_json.py \
    schemas/sample.schema.json schemas/run-result.schema.json \
    arm64_probe/execution/result_store.py \
    tests/unit/test_result_store.py \
    tests/contract/test_exit_codes.py
  git commit -m "Add RunResult schema v2 and atomic RunResultStore"
  ```

  Expected: AC4 partially closes (storage + schema). The
  runner populates the new fields in Task 17.

### Task 17: Implement the `Runner` and the Fake Coordinator

**Files:**
- Create: `arm64_probe/execution/runner.py`
- Create: `tests/support/fake_coordinator.py` (or extend
  `tests/support/fake_controllers.py` if a separate file
  is redundant — the plan calls out a new file for clarity)
- Create: `tests/support/executor_recorder.py`
- Create: `tests/unit/test_runner.py`
- Modify: `tests/support/fake_controllers.py` (extend
  `FakeController.events` to accept a `frozen` observer
  callback if needed for the runner)

- [ ] **Step 1: Write failing runner tests**

  In `tests/unit/test_runner.py`:

  - `test_run_with_no_controllers_runs_work_immediately` —
    when the resolved `Plan` has no cases, the runner
    returns an empty `RunResult` and does not call
    `EnvironmentCoordinator.execute`. Mirrors the Phase 2
    "no requests" branch.
  - `test_run_groups_cases_by_environment_phase` — a
    `Plan` with two phases produces two
    `EnvironmentCoordinator.execute` invocations; assert
    the `requests` tuple for each.
  - `test_run_propagates_environment_apply_exit_code_12`
    — when the coordinator raises `ENVIRONMENT_APPLY`,
    the runner re-raises the same code; the partial
    `RunResult` is written with `complete=False`.
  - `test_run_propagates_environment_restore_exit_code_13`.
  - `test_run_returns_propagates_environment_busy_14`.
  - `test_run_writes_partial_result_on_case_failure_15`
    — the runner wraps per-case adapter exceptions in
    `ProbeError(PROBE_EXECUTION)`; the partial
    `RunResult` lists the failed case as
    `status: "error"`.
  - `test_run_uses_default_60s_case_timeout` — when
    `--case-timeout` is not given, the runner passes
    `timeout=60` to the injected `CommandExecutor`.
  - `test_run_persists_run_result_atomically` — the
    `RunResultStore.write_local` is called exactly once
    per `probe run`; the file on disk matches
    `to_data(result)`.
  - `test_run_records_repository_commit_dirty_tree_toolchain`
    — assert the `summary` map contains
    `repository_commit`, `dirty_tree`, and
    `toolchain` keys with the expected types.
  - `test_run_uses_injected_command_executor_not_subprocess`
    — the runner does **not** call `subprocess` directly;
    it routes through the injected `CommandExecutor`.

- [ ] **Step 2: Run focused tests and verify they fail**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_runner -v
  ```

  Expected: FAIL (no module).

- [ ] **Step 3: Implement the `Runner` and `ToolchainEvidence`**

  In `arm64_probe/execution/runner.py`:

  - `ToolchainEvidence` frozen dataclass with
    `python_version: str`, `uv_version: str`,
    `cc: str`, `host_os: str`. Constructed at runner
    instantiation via `subprocess.run(("uv", "--version"),
    capture_output=True, text=True, check=False,
    shell=False)` and similar; on any failure, fall
    back to `"unknown"`.
  - `RunRequest` (frozen) wrapping `case`, `platform_id`,
    `backend`, `allow_mutation`. Not used externally; the
    runner builds it internally.
  - `Runner.__init__(self, adapter_registry,
    store, *, executor: CommandExecutor | None = None,
    case_timeout_seconds: int = 60)`. The
    `case_timeout_seconds` is the default the runner
    passes to `executor.run(argv, timeout=...)`. Override
    at construction (CLI flags translate to constructor
    args).
  - `Runner.run(plan, platform_id, backend,
    allow_mutation, output_dir, run_id=None,
    toolchain_evidence=None, started_at=None)`
    follows the algorithm in the design §4.2 and §5.
  - The runner's work callback (passed to
    `EnvironmentCoordinator.execute`) iterates the cases
    in the phase, looks up the `ProbeAdapter` for each
    `case.scenario_id`, builds the argv, calls
    `self._executor.run(argv, timeout=self._case_timeout)`,
    and feeds `(stdout, stderr, exit_code, timed_out)`
    to the adapter's `parse_output`. The resulting
    `Sample` objects are appended to the closure-captured
    list. The `timed_out` flag is set when
    `subprocess.TimeoutExpired` is raised; the runner
    catches it and synthesizes the `ProbeFailure` per
    spec §5.4.
  - The runner does not raise `ProbeError(15)` itself
    unless an adapter raises; the per-case failure path
    is `status: "error"`, not a coordinator abort.
  - The `RunResult` is written **after** the coordinator
    returns; for partial runs, the runner still calls
    `write_local` with `complete=False`.

- [ ] **Step 4: Implement `tests/support/fake_coordinator.py`**

  A recording fake that returns a configurable
  `EnvironmentJournal` and optionally raises a
  `ProbeError`. Mirrors the role of
  `tests/support/fake_controllers.py:FakeController`.

- [ ] **Step 5: Implement `tests/support/executor_recorder.py`**

  Implements the existing `CommandExecutor` Protocol from
  `arm64_probe/backends/io.py:19`. Maintains a queue of
  `argv → CompletedProcess` mappings. Tests push
  responses; the runner consumes them. The recorder
  exposes the `argv` it received, including the
  `timeout` parameter, so `test_run_uses_default_60s_case_timeout`
  can assert it.

- [ ] **Step 6: Run tests and commit**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_runner -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/execution/runner.py tests/unit/test_runner.py \
    tests/support/fake_coordinator.py \
    tests/support/executor_recorder.py
  git commit -m "Add Runner that groups cases by environment phase"
  ```

  Expected: focused tests pass; AC3 closes (runner side);
  AC4 closes (summary fields).

### Task 18: Wire the `probe run` CLI Surface

**Files:**
- Modify: `arm64_probe/cli/parser.py` (add `run` subcommand; extend `COMMANDS`)
- Modify: `arm64_probe/cli/main.py` (dispatch `run`)
- Modify: `arm64_probe/cli/render.py` (add `render_run` with table and JSON branches)
- Create: `tests/contract/test_cli_run.py`
- Create: `tests/contract/test_run_plan_equivalence.py`

- [ ] **Step 1: Write failing CLI tests**

  In `tests/contract/test_cli_run.py`, every example from
  spec §3.2 plus the failure paths:

  - `probe run cache-latency/l1-latency` — exit 0; the
    JSON output contains a `RunResult` with one or more
    `Sample` records whose `case_id` matches the
    scenario.
  - `probe run --profile smoke` — exit 0; the JSON
    output's `RunResult.plan.cases` matches the smoke
    profile's selections.
  - `probe run --case <stable-case-id>` — exit 0; exactly
    one case in the result.
  - `probe run --case-timeout 30` — the runner is
    constructed with `case_timeout_seconds=30`;
    `executor.run` is called with `timeout=30`. Asserted
    via the `ExecutorRecorder`.
  - `probe run` with no target and no `--profile` —
    exit 2 (usage).
  - `probe run --case bogus` — exit 2 (usage).
  - `probe run --platform gb10 --profile smoke` without
    `--allow-mutation` and a mutating profile — exit 11.
  - `probe run` with no `--output-dir` — exits 0 and
    writes under `results/runs/` (git-ignored; the test
    overrides the workdir to a tempdir).
  - `probe run -o json` — JSON output is `to_data(result)`.
  - `probe run -o table` — table output includes
    `CASE`, `STATUS`, `SAMPLES`, `METRIC` columns.

  In `tests/contract/test_run_plan_equivalence.py`:

  - `test_run_and_plan_emit_same_case_set` — for each
    selection in the smoke profile, the case IDs
    emitted by `probe plan` and `probe run` (table
    output) are equal.
  - `test_run_and_plan_emit_same_parameter_values` —
    `samples`, `working-set`, `page-policy` match.

- [ ] **Step 2: Run focused tests and verify they fail**

  ```sh
  uv run --no-sync python -m unittest \
    tests.contract.test_cli_run \
    tests.contract.test_run_plan_equivalence -v
  ```

  Expected: FAIL (no subcommand, no renderer).

- [ ] **Step 3: Add the `run` subcommand to the parser**

  In `arm64_probe/cli/parser.py`:

  - Extend `COMMANDS` to `("list", "show", "plan", "doctor",
    "restore", "run", "resume")`.
  - Add a `run_parser` with the args in spec §3.2,
    including the new `--case-timeout <seconds>` and
    `--no-case-timeout` flags. `--no-case-timeout` is the
    argparse action that stores `0`; the runner maps
    `0` to "no timeout" (`executor.run(argv, timeout=None)`).
  - Reject repeated `--platform` via argparse `default`
    and document the de-facto single-occurrence.

- [ ] **Step 4: Add the dispatch in `main.py`**

  In `arm64_probe/cli/main.py`:

  - Resolve the platform exactly as `plan` does
    (`_resolve_platform`).
  - Build the `Planner` and call
    `Planner(catalog).plan(_plan_request(args))`.
  - Construct the `Runner` with the default registry and
    the `RunResultStore(root=output_dir_default)`. The
    `output_dir` defaults to `results/runs/`. The runner
    injects a `LocalCommandExecutor` in production; tests
    inject `ExecutorRecorder`.
  - Pass the `case_timeout_seconds` from the parsed
    arguments: `--case-timeout N` → `N`,
    `--no-case-timeout` → `0` (mapped to `None`),
    default `60`.
  - Call `runner.run(...)`. Catch `ProbeError` and route
    to the existing structured-error path.
  - Print `render_run(result, args.output)`.

- [ ] **Step 5: Implement `render_run`**

  In `arm64_probe/cli/render.py`:

  - JSON branch: `dump_json(to_data(result))`.
  - Table branch: case ID, status, samples (count),
    primary metric (e.g. `latency_ns` or
    `migrate_penalty_ns`). The exact column set is
    captured by `test_cli_run.py`; no on-the-fly schema
    design happens in this task.

- [ ] **Step 6: Run tests and commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.contract.test_cli_run \
    tests.contract.test_run_plan_equivalence -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/cli/parser.py arm64_probe/cli/main.py \
    arm64_probe/cli/render.py \
    tests/contract/test_cli_run.py \
    tests/contract/test_run_plan_equivalence.py
  git commit -m "Add probe run CLI with plan equivalence"
  ```

  Expected: focused tests pass; AC2 closes; AC6
  partially closes (CLI side).

### Task 19: Implement `probe resume` and the Resume Service

**Files:**
- Create: `arm64_probe/execution/resume.py`
- Create: `tests/unit/test_resume.py`
- Create: `tests/contract/test_cli_resume.py`
- Create: `tests/integration/test_phase3_resume_workflow.py`

- [ ] **Step 1: Write failing resume tests**

  In `tests/unit/test_resume.py`:

  - `test_resume_runs_only_error_cases` — a prior
    `RunResult` with two `status: "ok"` cases and one
    `status: "error"` case; the resume produces a new
    `RunResult` with **two** samples (one carried
    `ok`, one fresh re-run); the carried case preserves
    its original `Sample.run_id`; the re-run case has a
    new `Sample.run_id`.
  - `test_resume_drops_skipped_cases` — a prior
    `RunResult` with one `status: "skipped"` case; the
    resume produces a new `RunResult` with **zero**
    samples (the skipped case is neither carried nor
    re-executed). `summary["skipped_cases"]` records the
    dropped case IDs.
  - `test_resume_is_idempotent_on_fully_successful_prior` —
    repeated resume returns `0` and writes a new
    `RunResult` with `resume_kind: "no-op"`.
  - `test_resume_rejects_schema_version_mismatch` — exit
    16; the abort happens **before** any case is
    re-executed (assert by counting `executor.run` calls).
  - `test_resume_rejects_case_definitions_signature_mismatch`
    — exit 16.
  - `test_resume_rejects_platform_id_mismatch` — exit 16.
  - `test_resume_rejects_repository_id_mismatch` — exit 16.

  In `tests/contract/test_cli_resume.py`:

  - `probe resume --run <path>` — exit 0; new
    `RunResult` JSON includes `prior_run_id` and
    `resume_kind: "missing"` or `"failed"`.
  - `probe resume --run <path>` on a non-existent path
    — exit 16.
  - `probe resume --run <path>` on a malformed JSON
    file — exit 16.
  - `probe resume --run <path>` on a JSON file with the
    wrong `repository_id` — exit 16.
  - `probe resume` requires `--allow-mutation` when the
    underlying plan mutates the host; missing → 11.

  In `tests/integration/test_phase3_resume_workflow.py`:

  - End-to-end: `FakeBackend` + `FakeController` +
    `FakeAdapter` + `ExecutorRecorder`. The first run
    produces a `RunResult` with one failed case; the
    second run (`probe resume`) re-executes only that
    case; both runs land under the same `output_dir`.

- [ ] **Step 2: Run focused tests and verify they fail**

  ```sh
  uv run --no-sync python -m unittest \
    tests.unit.test_resume \
    tests.contract.test_cli_resume \
    tests.integration.test_phase3_resume_workflow -v
  ```

  Expected: FAIL (no module).

- [ ] **Step 3: Implement `ResumeService`**

  In `arm64_probe/execution/resume.py`:

  - `ResumeService(store: RunResultStore, runner: Runner)`.
  - `resume(prior_path: Path, *, plan: Plan, platform_id:
    str, backend: HostBackend, allow_mutation: bool,
    output_dir: Path, case_timeout_seconds: int = 60) -> RunResult`.
  - `validate_compatibility(prior, plan)` calls the
    `RunResultStore.validate_compatibility`; any
    `ProbeError(16)` propagates. **This happens before
    any re-execution**; see test
    `test_resume_rejects_schema_version_mismatch`.
  - Sample diff logic per spec §5.5: cases with
    `status: "ok"` are carried over; cases with
    `status: "error"` are re-executed; cases with
    `status: "skipped"` are dropped (and recorded in
    `summary["skipped_cases"]`).
  - The new `RunResult` records
    `summary["prior_run_id"] = prior.run_id` and
    `summary["resume_kind"]` ∈
    `{"missing", "failed", "no-op"}`.

- [ ] **Step 4: Add the `resume` subcommand to the parser**

  In `arm64_probe/cli/parser.py`:

  - Extend `COMMANDS`.
  - Add a `resume_parser` with `--run <path>` (required),
    `--output-dir`, `--case-timeout` (or
    `--no-case-timeout`), `--allow-mutation`,
    `-o/--output`.

- [ ] **Step 5: Add the dispatch in `main.py`**

  In `arm64_probe/cli/main.py`:

  - Read the prior `RunResult` via
    `RunResultStore.read(prior_path)`.
  - Reconstruct the `Plan` from the prior `RunResult.plan`
    (no fresh `Planner` invocation unless the user
    passed new `--select` / `--profile` — the handoff
    fixes the resume behavior as "re-runs the cases
    referenced in a prior `RunResult`").
  - Call `ResumeService.resume(...)`.
  - Print `render_resume(result, args.output)`.

- [ ] **Step 6: Implement `render_resume`**

  Mirror of `render_run`. Table view adds a `RESUME` column
  showing `missing` / `failed` / `no-op` per case. JSON
  output is `to_data(result)`.

- [ ] **Step 7: Run tests and commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.unit.test_resume \
    tests.contract.test_cli_resume \
    tests.integration.test_phase3_resume_workflow -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/execution/resume.py \
    arm64_probe/cli/parser.py arm64_probe/cli/main.py \
    arm64_probe/cli/render.py \
    tests/unit/test_resume.py \
    tests/contract/test_cli_resume.py \
    tests/integration/test_phase3_resume_workflow.py
  git commit -m "Add probe resume and ResumeService"
  ```

  Expected: focused tests pass; AC5 closes.

## Batch 3: Acceptance, Smoke, and Runbook

### Task 20: Phase 3 Acceptance, Smoke Workflow, Documentation, and Gate 1 Runbook

**Files:**
- Modify: `Makefile` (add `smoke` and `phase3-check`; update `help`; add to `.PHONY`)
- Create: `tests/contract/test_phase3_acceptance.py`
- Create: `tests/integration/test_phase3_smoke_workflow.py`
- Create: `tests/integration/test_phase3_signal_restore.py`
- Create: `tests/integration/test_phase3_fixture_workflow.py`
- Create: `docs/superpowers/handoffs/2026-06-15-phase3-gate1-runbook.md` (AC9 deliverable; **not** a frozen file — user reviews at Gate 1 time)
- Modify: `tests/test_makefile_contract.py` (extend with the `phase3-check` and `smoke` wrappers)
- Modify: `tests/contract/test_phase2_acceptance.py` (extend the platform-name branch check to cover `arm64_probe/execution/`)
- Modify: `tests/contract/test_repository_policy.py` (extend frozen-path integrity to assert the new file paths are not on the frozen list)
- Modify: `tests/contract/test_public_schemas.py` (already extended in Task 16; verify)
- Modify: `AGENTS.md` (Phase 3 section)
- Modify: `CLAUDE.md` (Phase 3 architecture section)
- Modify: `docs/design/cli-contract.md` (add `probe run` and `probe resume`)
- Modify: `docs/design/repository-contract.md` (add `make phase3-check` and `make smoke`)
- Modify: `docs/superpowers/handoffs/2026-06-15-phase2-closure-and-phase3-readiness.md` (replace "Phase 3 plan written and accepted" gate with the new state)

- [ ] **Step 1: Write failing acceptance tests**

  In `tests/contract/test_phase3_acceptance.py`:

  - `test_no_platform_name_branch_in_execution_modules` —
    extend the existing Phase 2 contract to forbid
    `gb10` / `m4` / `taskset` / `sudo ` / `/sys/` /
    `/proc/` literals in
    `arm64_probe/execution/`.
  - `test_runner_runner_cli_resume_schemas_have_contract_tests`
    — every public schema required by the
    `to_data(RunResult)` path is in
    `SCHEMA_REQUIRED`.
  - `test_probe_run_does_not_bypass_coordinator` — a
    focused test that imports `arm64_probe.cli.main` and
    asserts that the `run` dispatch routes through
    `Runner.run` (not a hand-rolled subprocess wrapper).
  - `test_resume_rejects_cross_version_results` — the
    four compat fields are individually exercised.
  - `test_smoke_workflow_runs_without_host_mutation` — the
    fake-backend path through `make smoke` produces a
    schema-valid `RunResult` and writes under a tempdir.
  - `test_frozen_paths_remain_unchanged` — the existing
    `git diff main..HEAD` filter over
    `runner/`, `data/`, `analysis/`, `baseline/` still
    passes.

- [ ] **Step 2: Write failing Makefile contract tests**

  In `tests/test_makefile_contract.py` (extended):

  - `test_phase3_wrappers_are_thin` — `make smoke` and
    `make phase3-check` exist; their recipes are
    uv-managed; they contain no parsing, no platform
    branch, no mutation logic.
  - `test_phase3_help_advertises_targets` — `make help`
    mentions `phase3-check` and `smoke`.

- [ ] **Step 3: Run focused tests and verify they fail**

  ```sh
  uv run --no-sync python -m unittest tests.contract.test_phase3_acceptance -v
  uv run --no-sync python -m unittest tests.test_makefile_contract -v
  ```

  Expected: FAIL (acceptance tests missing; Makefile
  targets missing).

- [ ] **Step 4: Add the Makefile targets and update the help**

  In `Makefile`:

  ```makefile
  phase3-check:
      $(UV_RUN) python -m unittest discover -s tests -p 'test_*.py' -v
      $(UV_RUN) python scripts/legacy_manifest.py verify
      $(UV_RUN) python -m unittest tests.contract.test_exit_codes -v
      $(UV_RUN) python -m unittest tests.contract.test_run_plan_equivalence -v
      $(UV_RUN) python -m unittest tests.contract.test_cli_run -v
      $(UV_RUN) python -m unittest tests.contract.test_cli_resume -v

  smoke:
      @mkdir -p $(BUILD_DIR)/smoke-runs
      $(UV_RUN) python ./probe plan --platform gb10 --profile smoke -o json > $(BUILD_DIR)/smoke-plan.json
      $(UV_RUN) python ./probe run --platform gb10 --profile smoke --allow-mutation \
          --output-dir $(BUILD_DIR)/smoke-runs
  ```

  Update `.PHONY` and `help`.

- [ ] **Step 5: Implement the smoke workflow integration tests**

  In `tests/integration/test_phase3_smoke_workflow.py`:

  - Drives the runner against a fake `Backend` +
    `FakeController` + `FakeAdapter` + `ExecutorRecorder`.
  - Asserts a schema-valid `RunResult` lands under a
    tempdir.

  In `tests/integration/test_phase3_signal_restore.py`:

  - Mid-run SIGTERM during the runner's `work` callback;
    the `EnvironmentCoordinator` restores the host and
    the partial `RunResult` is written.

  In `tests/integration/test_phase3_fixture_workflow.py`:

  - Equivalent of the Phase 2 fixture workflow, but for
    `probe run` against `FakeBackend` + `FakeController` +
    `FakeAdapter`.

- [ ] **Step 6: Extend the existing acceptance tests**

  In `tests/contract/test_phase2_acceptance.py`, add
  `arm64_probe/execution/` to the platform-name branch
  check.

  In `tests/contract/test_repository_policy.py`, add
  `runner/`, `data/`, `analysis/`, `baseline/` to the
  forbidden new entries under v1.0-owned paths (defense
  in depth; `make legacy-check` already protects frozen
  paths via `legacy/manifest.json`).

- [ ] **Step 7: Update the documentation**

  In `AGENTS.md`: add a Phase 3 section listing
  `probe run`, `probe resume`, `make smoke`,
  `make phase3-check`, the `Sample` and `RunResult`
  schema-version bump, and the AC1–AC9 evidence matrix
  pointer (`tests/contract/test_phase3_acceptance.py`).

  In `CLAUDE.md`: add a Phase 3 architecture section
  covering `Runner`, `ProbeAdapter`, `RunResultStore`,
  `ResumeService`, and the `Makefile` targets.

  In `docs/design/cli-contract.md`: add `probe run` and
  `probe resume` to the Phase 2 surface block (do **not**
  add `probe analyze` or `probe report`; they are
  Phase 4).

  In `docs/design/repository-contract.md`: add
  `make phase3-check` and `make smoke`.

  In `docs/superpowers/handoffs/2026-06-15-phase2-closure-and-phase3-readiness.md`:
  update the §1.3 table — mark Gate 2 (Phase 3 plan
  written and accepted) as done; mark Gate 3
  (`probe run` / `probe resume` CLI + domain model) and
  Gate 4 (probe normalization) and Gate 5 (unified
  runner + transactional integration) and Gate 6
  (Mac + Linux ARM64 fixture smoke workflow) as done
  by reference to the new commits; mark Gate 7 (GB10
  hardware) and Gate 8 (`GB10 Gate 1 is ready to
  run`) as still pending.

- [ ] **Step 8: Author the Gate 1 runbook**

  Create
  `docs/superpowers/handoffs/2026-06-15-phase3-gate1-runbook.md`
  with the exact step list from the Phase Completion
  Gate §1 (the runbook subsection). Mark it explicitly
  as a **user-executed** runbook; the implementer does
  **not** run it. The runbook is added to the
  AC9 evidence matrix as a deliverable, not as
  automated evidence.

- [ ] **Step 9: Run complete verification**

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

  Expected: all tests pass; the smoke workflow writes
  a `RunResult` under `build/smoke-runs/`; help for
  `run` and `resume` is present; no frozen or
  transitional paths appear in the diff.

- [ ] **Step 10: Review the complete Phase 3 diff**

  ```sh
  git diff --stat main...HEAD
  git diff --name-status main...HEAD
  git status --short
  ```

  Confirm:

  - no frozen or transitional files changed;
  - no `python3` literal in `Makefile` or shebangs;
  - no platform-name branch in `arm64_probe/`;
  - no new public `environment-apply` command;
  - documentation matches implemented behavior.

- [ ] **Step 11: Commit Phase 3 acceptance evidence**

  ```sh
  git add Makefile AGENTS.md CLAUDE.md \
    arm64_probe \
    docs/design \
    docs/superpowers/handoffs \
    tests
  git commit -m "Complete Phase 3 probes and unified runner"
  ```

  Expected: the branch is clean after the acceptance
  commit; the runbook is included in the commit
  (user reviews at Gate 1 time, not before).

## Phase 3 Completion Gate

Before requesting architect review:

1. Run `make phase3-check`, `make check`, `make
   legacy-check`, and `make build` from a clean tree.
2. Run `make smoke` and confirm a schema-valid
   `RunResult` lands under `build/smoke-runs/`.
3. Confirm every AC1–AC9 evidence entry in
   `tests/contract/test_phase3_acceptance.py` and the
   per-task proof matrix in this plan is satisfied.
4. Confirm `probe run` and `probe resume` are
   contract-tested (AC2, AC5, AC6) and the test count
   has grown by at least 25 from the Phase 2 baseline of
   241.
5. Confirm `results/runs/` is git-ignored; confirm
   `results/baselines/<version>/` is **not** touched
   by this phase.
6. Confirm the production `STATE_ROOT` for the
   environment layer remains `/var/lib/arm64-uarch-probe`
   and is not overridden.
7. Confirm Phase 3 contains no GB10 measurement
   evidence and makes no M4 measurement claim.
8. Confirm the AC9 runbook is present and
   user-executable.
9. Review and merge the Phase 3 implementation branch
   into `main` (the user does this; preserve-history,
   `--no-ff`) before the user announces `GB10 Gate 1 is
   ready to run`.

The implementer does **not** announce `GB10 Gate 1 is
ready to run`. The user does, after running the AC9
runbook on real GB10 hardware.

At Gate 1 time, if the user encounters a failure,
the implementer's role is to fix and revalidate on Mac
or Linux ARM64 first. Do not expand Gate 1 into broad
exploratory measurement; the handoff explicitly forbids
this.

After the user has merged the Phase 3 branch, the
implementer hands off to the user (and to Phase 4's
handoff architect if/when the user creates that
handoff). The Phase 3 branch is the next handoff
artifact; the handoff chain is now `phase1 → phase2 →
phase3`.
