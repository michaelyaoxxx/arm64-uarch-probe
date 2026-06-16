# Phase 3 Probes and Unified Runner — Detailed Design

> **Status:** design (re-authored 2026-06-15 under the superpowers brainstorming flow). Authoritative inputs:
> - `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` (AC1–AC9, locked architecture decisions, quality controls)
> - `docs/superpowers/specs/2026-06-12-arm64-uarch-probe-v1.0-design.md` (§7.4 individual and combined execution, §7.5 operations)
> - `docs/superpowers/specs/2026-06-14-phase2-backends-environment-design.md` (existing transaction model this phase reuses)
>
> **Companion document:** `docs/superpowers/plans/2026-06-15-phase3-probes-runner.md` (the executable plan that maps AC1–AC9 to Task 14–Task 20).
>
> **Implementation status:** **none**. This spec exists to be approved; code follows in the plan. Where examples are required to validate the design (e.g. fixture-runner round-trips), the design says "deferred to a code-handoff document" rather than writing code in the spec.

## 1. Objective

Deliver the unified measurement runner. Concretely:

1. A `ProbeAdapter` protocol with three concrete adapters (`ChasePmuAdapter`, `EvictSlcAdapter`, `ChaseMigrateAdapter`) that wrap the existing C probes and produce a `Sample` per call.
2. A `Runner` that drives the planner's `Plan` through one `EnvironmentCoordinator.execute` invocation per environment phase, accumulating `Sample` records into a `RunResult`.
3. A `RunResultStore` for atomic, schema-valid `RunResult` persistence under `results/runs/` (git-ignored) with optional promotion to `results/baselines/<version>/`.
4. Two new public commands — `probe run` and `probe resume` — wired through the existing `arm64_probe.cli` surface with the same exit-code contract as Phase 2.
5. Two new `ExitCode` constants (`15`, `16`) contract-tested against the schema and CLI examples in §3.
6. A `make smoke` target and a `make phase3-check` target, both uv-managed and contract-tested.
7. Characterization tests that pin the current `chase_pmu` / `evict_slc` / `chase_migrate` textual output, run before any normalization changes, so the normalization is provably behavior-preserving.

`probe analyze`, `probe report`, and full v1.0 baseline measurements are
explicitly out of scope (Phase 4). The handoff fixed
`probe run` and `probe resume` as the only Phase 3 additions; the
spec and plan do not introduce `probe analyze` or `probe report`.

## 2. Locked architecture decisions (from the handoff)

These are quoted from the architect handoff and are not open for
re-decision. Where the implementation must commit to a detail
that the handoff left open, this spec states it explicitly and
cites the constraint.

### 2.1 Transaction boundary

> One transaction per environment phase, not per case. Cases
> sharing identical host requirements run under one transaction;
> restoration occurs before the next phase.

Consequence: the runner groups cases by `phase.host_requirements`
and invokes `EnvironmentCoordinator.execute(backend, platform_id,
requests, work, allow_mutation)` once per group. The `work`
callback inside each `execute` invocation iterates the cases in
the phase, calls the appropriate `ProbeAdapter` for each, and
assembles `Sample` records. Cases that share a phase share one
host-mutation cycle.

### 2.2 Resume source

> `probe resume` reads a prior structured `RunResult`.
> Environment journals remain exclusively for environment recovery.

Consequence: `probe resume --run <path>` opens a prior
`RunResult`, computes the set of cases that did not produce a
`status: "ok"` `Sample`, and re-runs only those cases. The
journal from the prior run is *not* consulted; if the prior
host was left in a mutated state, `probe doctor`/`probe restore`
handle that. This is a deliberate separation of concerns:
journals describe the *host* state; results describe the
*measurement* state.

### 2.3 Execution boundary

> A platform-independent runner invokes injectable probe/process
> adapters. It contains no GB10/M4 branches, sysfs paths, or
> experiment-specific parsing.

Consequence: the runner and adapters import only from
`arm64_probe.platforms`, `arm64_probe.domain`, and the standard
library. They never read `/sys/`, `/proc/`, `runner/`, or any
config under `configs/platforms/`. Probe output parsing lives in
each adapter, never in the runner. Adapter selection is by
`scenario.id` and the adapter registry, not by `platform_id`.

### 2.4 Legacy boundary

> Frozen `runner/run_pmu*.sh`, `data/`, `analysis/`, `baseline/`,
> and `runner/cache_info_*` remain unchanged. New adapters may
> preserve their behavior but must not call frozen runners as
> the new public control surface.

Consequence: a future "legacy wrapper" adapter may call
`runner/run_pmu_v2.7.7.sh` to preserve behavior, but that adapter
is *not* on the `probe run` happy path. Phase 3 ships only the
three direct C-probe adapters; the legacy-wrapper adapter is a
non-goal for this phase.

### 2.5 Mutation boundary

> `probe run` is the only new public mutation entry point and
> must use the existing coordinator, lock, journal, restoration,
> and `--allow-mutation` contract. No automatic `sudo`.

Consequence: the CLI does not invoke `sudo`. Public mutation
requires both `--allow-mutation` and caller privilege. The
runner and the `EnvironmentCoordinator` together enforce the
`11`/`12`/`13`/`14` matrix from Phase 2; `probe run` adds `15`
on probe-execution failure and `16` on `RunResult` persistence
failure (see §3).

### 2.6 Result boundary

> Local runs write under ignored `results/runs/`. Promotion into
> `results/baselines/<version>/` is a separate reviewed action.

Consequence: `RunResultStore.write_local(result)` writes to
`results/runs/<run_id>.json` (git-ignored). There is **no**
Phase 3 CLI that writes under `results/baselines/`. Promotion is
left for the user to perform via filesystem copy (or via
`probe promote`, which is a Phase 4 command).

## 3. Public contract additions

### 3.1 New `ExitCode` values (frozen by the handoff)

| Code | Name | Meaning |
|---|---|---|
| `15` | `PROBE_EXECUTION` | probe launch failure, timeout, signal, nonzero exit, malformed/partial/empty machine-readable output, or any other per-case failure that is not a transaction failure |
| `16` | `RUN_RESULT` | `RunResult` read, validation, schema-compatibility, or atomic-persistence failure |

Both values are added to `arm64_probe/errors.py` alongside the
Phase 2 enum, are referenced by name in the runner, and are
asserted by `tests/contract/test_exit_codes.py` (new contract
test, see §6).

### 3.2 New `probe run` CLI surface

```text
probe run [--platform <id>] [--profile <id>] [--select <id> ...]
          [--cluster <id>] [--core-group <id>]
          [--cpu <int>] [--src-cpu <int>] [--dst-cpu <int>]
          [--samples <int>] [--working-set <size>]
          [--page-policy default|hugepage]
          [--case <stable-case-id>]
          [--case-timeout <seconds>] [--no-case-timeout]
          [--output-dir <path>]
          [--allow-mutation]
          [-o table|json]
          [<target> ...]
```

Rules:

- Selection and override semantics are **identical** to
  `probe plan`. The runner computes the same `Plan` via the
  existing `Planner` and then executes it. The
  `tests/contract/test_run_plan_equivalence.py` contract
  asserts that `probe plan ...` and `probe run ...` (with
  `--output table`) produce the same set of case IDs and
  parameters.
- At least one target or `--profile` is required; otherwise
  argparse raises `usage error (2)`.
- `--case <stable-case-id>` selects exactly one case by its
  stable ID; the runner validates that the ID is a substring
  match for a case in the resolved `Plan`. Mismatch → `usage
  error (2)`.
- `--allow-mutation` is required when the plan contains any
  `host`-scoped environment requirement (i.e. any controller
  request). Missing → `11` before host writes. This is the
  Phase 2 contract re-applied; see
  `tests/contract/test_run_authorization.py`.
- `--output-dir` defaults to `results/runs/` (git-ignored). The
  store creates the directory if missing with mode `0o755` and  ownership `os.geteuid()`.
- **Case timeout:** the default is `60` seconds per case
  (see §5.4 for the rationale). `--case-timeout <seconds>`
  overrides; `--no-case-timeout` disables the timeout
  entirely. A timeout produces a `Sample` with
  `status: "error"` and a `ProbeFailure(stage="timeout")`,
  and the runner records the per-case failure without
  aborting the surrounding phase; the next case in the
  phase continues. The exit code on timeout is `15` (probe
  execution) — see §5.4.
- Short options are limited to `-h`/`--help` and `-o`/`--output`
  (Phase 1 contract). `--allow-mutation`, `--case`,
  `--case-timeout`, `--output-dir`, `--cpu`, etc. all
  require their long form.
- Exit code is `0` only when every case produced `status:
  "ok"` samples and the `RunResult` was written successfully.
  Otherwise `15` (case failure) or `16` (persistence failure),
  with environment restore priority `13` over `15`/`16`.

### 3.3 New `probe resume` CLI surface

```text
probe resume --run <path-to-run-result-json>
             [--output-dir <path>]
             [--case-timeout <seconds>] [--no-case-timeout]
             [--allow-mutation]
             [-o table|json]
```

Rules:

- `--run` is required and must point to a schema-valid
  `RunResult` JSON file.
- The CLI validates compatibility (see AC5 and §5.6): same
  `schema_version`, same `platform_id`, same `repository_id`,
  same `repository_commit`, same `case_definitions_signature`
  (see §4.5). Any mismatch → `RUN_RESULT` exit `16` with a
  structured error.
- The runner computes the diff between the prior `RunResult`'s
  `samples` and the set of case IDs in the current `Plan` (which
  is reconstructed from the prior `Plan` plus any fresh
  `selections` on the CLI). Cases already `status: "ok"` are
  carried over; cases that failed are re-executed; cases
  marked `status: "skipped"` are **not re-executed and not
  carried over** (see §5.5 for the rationale). The new
  `RunResult` records `prior_run_id` and `resume_kind`
  (`"missing"`, `"failed"`, or `"no-op"`) in its `summary`
  map. The previous `RunResult` is not mutated.
- Repeated `probe resume` on a fully successful `RunResult` is
  a successful no-op that returns `0` and writes a new
  `RunResult` with `resume_kind: "no-op"`.
- **`schema_version` mismatch (e.g. `1` vs `2`):** the
  compatibility check returns `ProbeError(16)` and the
  resume aborts before any case is re-executed. There is
  **no** auto-conversion path in Phase 3; the user is
  expected to either re-run the original `probe run` from
  scratch, or wait for a future `probe convert` command
  (which is a Phase 4 deliverable). See §5.6 for the
  rationale.

### 3.4 Invariants preserved from earlier phases

- `probe --help` and `probe help <topic>` enumerate `run` and
  `resume` alongside the existing commands. The handoff
  requires `probe help run` and `probe help resume` to be
  contract-tested.
- `--output table|json` works for both `run` and `resume`. JSON
  output emits a `to_data(RunResult)` object (see §4.4).
- `probe run` and `probe resume` accept no `python3`/state-root
  override; they cannot bypass `EnvironmentCoordinator`,
  `MutationLock`, `JournalStore`, or `EnvironmentRecovery`.
- No `if platform == "gb10"` / `if platform == "m4"` branches
  appear in `arm64_probe/`. The Phase 2 acceptance test
  extends to cover `arm64_probe/execution/`, `arm64_probe/runner/`,
  and `arm64_probe/backends/adapters/`.
- Every Python invocation in the new modules goes through `uv
  run --no-sync python` from the Makefile; the `probe` shebang
  is unchanged from the Phase 2 toolchain pin.

## 4. Module layout (additive, no removals)

New modules (all under `arm64_probe/`):

```
arm64_probe/
  execution/
    __init__.py
    adapters/
      __init__.py
      base.py            # ProbeAdapter Protocol + ProbeOutcome dataclass
      chase_pmu.py       # ChasePmuAdapter
      evict_slc.py       # EvictSlcAdapter
      chase_migrate.py   # ChaseMigrateAdapter
      legacy_wrapper.py  # Stub; documents the non-goal for Phase 3
    runner.py           # Runner (plan -> samples -> RunResult)
    result_store.py     # RunResultStore (atomic write, read, validate)
    resume.py           # ResumeService (diff prior -> plan -> runner)
  diagnostics/
    doctor.py           # existing; unchanged
```

All new modules follow the Phase 2 conventions:

- frozen `@dataclass(frozen=True)` records;
- `JsonScalar` mappings (sorted-unique keys);
- `tuple`-based public models;
- `unittest` tests under `tests/unit/`, contract tests under
  `tests/contract/`, integration tests under
  `tests/integration/`;
- no platform-name branches, no `python3` literals, no
  `subprocess.run(shell=True)`.

### 4.1 `ProbeAdapter` protocol

```python
# arm64_probe/execution/adapters/base.py
class ProbeFailure(Protocol):
    @property
    def stage(self) -> str: ...          # "ok" | "error" | "skipped"
    @property
    def metrics(self) -> tuple[tuple[str, JsonScalar], ...]: ...
    @property
    def evidence(self) -> tuple[str, ...]: ...
    @property
    def failure(self) -> ProbeFailure | None: ...


class ProbeAdapter(Protocol):
    adapter_id: str                          # "chase_pmu.v2.7.3"
    scenario_id: str                         # "cache-latency.l1-latency"
    schema_version: int                      # 1
    @property
    def supported_cpu_modes(self) -> tuple[str, ...]: ...

    def build_argv(self, request: RunRequest) -> tuple[str, ...]: ...
    def parse_output(
        self, *, stdout: str, stderr: str, exit_code: int, timed_out: bool
    ) -> ProbeOutcome: ...
    def known_failure_modes(self) -> tuple[ProbeFailureMode, ...]: ...
```

Each concrete adapter is a `@dataclass(frozen=True)` that takes
its argv-builder arguments via a typed dataclass (e.g.
`ChasePmuArgs(size_kb, warm, force_rounds, seed, clflush,
hugepage, cpu)`) and the `build_argv` method renders to a
`tuple[str, ...]`. The `parse_output` method is a pure function
of `(stdout, stderr, exit_code, timed_out)` and returns a
`ProbeOutcome`. This is testable in isolation from
`subprocess`.

Adapter selection is by `scenario.id`:

- `cache-latency.l1-latency` / `.l2-latency` / `.l3-latency` /
  `.slc-latency` → `ChasePmuAdapter`
- `cache-latency.dram-latency` → `ChasePmuAdapter` (cold DRAM uses
  the same probe with `warm=0`, `force_rounds=1` and a `[COLD]`
  marker that the existing probe already emits)
- `migration-latency.*` → `ChaseMigrateAdapter`
- `evict_slc` is **not a scenario**; it is a setup tool used by
  `ChasePmuAdapter` for the cold DRAM case. The
  `EvictSlcAdapter` exists in `adapters/evict_slc.py` for
  completeness and is registered against a synthetic
  `evict-slc.setup` scenario so that future scenarios can
  invoke it; for Phase 3 it has no `probe run` exposure.

The `Runner` resolves the adapter from a frozen
`ADAPTER_REGISTRY: dict[str, ProbeAdapter]` keyed by
`scenario_id`. The registry is populated at module import
time. There is no platform-name lookup inside the registry.

### 4.2 `Runner` (plan -> samples -> RunResult)

```python
# arm64_probe/execution/runner.py
@dataclass(frozen=True)
class RunRequest:
    case: Case
    platform_id: str
    backend: HostBackend
    allow_mutation: bool


class Runner:
    def __init__(self, adapter_registry: AdapterRegistry, store: RunResultStore): ...

    def run(
        self,
        plan: Plan,
        *,
        platform_id: str,
        backend: HostBackend,
        allow_mutation: bool,
        output_dir: Path,
        run_id: str | None = None,
        toolchain_evidence: ToolchainEvidence | None = None,
        started_at: datetime | None = None,
    ) -> RunResult: ...
```

Algorithm (dependency order, not commit order):

1. Validate `platform_id` against `Plan.platform_id`; if the
   user passed `--platform auto`, resolve via the existing
   `_resolve_platform` helper in `arm64_probe/cli/main.py`.
2. Group `plan.cases` by `phase.host_requirements` (one
   `EnvironmentPhase` → one `execute` call). The
   `_environment_phases` static method on
   `arm64_probe.planning.planner.Planner` already produces
   these groupings; the runner re-uses it (no new planner
   code).
3. For each phase, call
   `EnvironmentCoordinator.execute(backend, platform_id,
   requests, work, allow_mutation)` where `work()` iterates
   the cases in the phase, calls `adapter.build_argv` and
   then `subprocess.run(adapter.build_argv, ...,
   timeout=case_timeout, text=True, capture_output=True)`,
   then `adapter.parse_output`, and accumulates `Sample`
   records. The subprocess is the only place a probe is
   invoked; the runner itself never parses probe output.
4. After every phase, if the phase failed and the
   `EnvironmentCoordinator` raised, the runner:
   - persists the partial `RunResult` (samples collected up
     to and including this phase) with
     `result.complete = False`;
   - re-raises the original `ProbeError` (or wraps it in a
     new `ProbeError` with `code: 15` if the underlying
     failure was a per-case execution issue, never masking
     `12` / `13` / `14`).
5. On full success, the runner:
   - builds a `RunResult` with `samples: tuple[Sample, ...]`,
     `summary` (case counts, status histogram, toolchain
     evidence, repo commit, dirty-tree status), and
     `environment` (controller list + final observed state);
   - persists the `RunResult` via `RunResultStore.write_local`;
   - returns the `RunResult`.

The runner does **not** itself import `subprocess` with
`shell=True`; it uses `subprocess.run(argv, ..., shell=False)`
exactly as the existing `CommandExecutor` protocol in
`arm64_probe/backends/io.py:19` already enforces. The
`CommandExecutor` protocol is re-used; the runner's
constructor accepts an injected `CommandExecutor` so tests
can pass a recording fake (e.g.
`tests/support/executor_recorder.py` — new, see §6).

### 4.3 `RunResultStore`

```python
# arm64_probe/execution/result_store.py
class RunResultStore:
    def __init__(self, root: Path, *, schema_version: int = 1): ...
    def write_local(self, result: RunResult) -> Path: ...
    def read(self, path: Path) -> RunResult: ...
    def validate_compatibility(
        self, prior: RunResult, current_plan: Plan
    ) -> None: ...   # raises ProbeError(16) on mismatch
```

Rules (AC4):

- The on-disk file is `<run_id>.json` written under `root`.
  `write_local` uses the same atomic-replace pattern as
  `JournalStore._atomic_write` (cf. `arm64_probe/environment/journal.py:338`):
  write to `.<run_id>.<uuid>.tmp`, `fsync`, `os.replace`,
  parent `fsync`. An interrupted write never replaces the last
  valid result.
- `read` uses the same `O_NOFOLLOW` + owner-check + size-cap
  pattern as `JournalStore.read`. The store rejects paths
  outside `root/`, symlinks, and files whose parent directory
  is unsafe.
- `validate_compatibility` (used by `probe resume`): same
  `schema_version`, same `platform_id`, same `repository_id`,
  same `repository_commit` (extracted from
  `summary["repository_commit"]`), and a `case_definitions_signature`
  (a stable hash over the sorted `Case.id` set + scenario
  parameter schemas). Mismatch → `ProbeError(code: 16)`.
- `to_data(result)` and `from_data(payload)` (in
  `arm64_probe/serialization/model_json.py`) handle the
  `Sample` and `RunResult` schemas in `schemas/`.

### 4.4 Public dataclass changes

- `RunResult` (existing in `arm64_probe/domain/models.py:142`)
  gains one optional field, `prior_run_id: str | None = None`
  and `resume_kind: str | None = None`. Both default to `None`
  on the non-resume path. The dataclass remains frozen.
- `Sample` is unchanged.
- A new `ToolchainEvidence` dataclass records `python_version`
  (e.g. `"3.13.13"`), `uv_version` (e.g. `"0.11.18"`), `cc`
  (e.g. `"cc"`), and the discovered `host_os` (e.g. `"Darwin"`).
  The runner records this in `RunResult.summary`.

### 4.5 Case definitions signature

```python
# arm64_probe/execution/result_store.py
def case_definitions_signature(plan: Plan) -> str:
    """Stable hash of the resolved cases that determines
    cross-version compatibility for `probe resume`."""
```

Implementation: SHA-256 of
`"\\n".join(f"{c.id}\\t{c.scenario_id}\\t{...sorted(c.parameters...)}" for c in sorted(plan.cases, key=lambda c: c.id))`.
Stored in `RunResult.summary["case_definitions_signature"]`.
`probe resume` compares it to the signature of the plan it
reconstructs; mismatch → `16`.

## 5. Result lifecycle (sequence diagram in prose)

Successful `probe run` for one case in one phase:

1. CLI parses arguments; resolves `Plan` via the existing
   `Planner`. AC2 equivalence with `probe plan` is asserted
   by `test_run_plan_equivalence`.
2. Runner groups the plan into `EnvironmentPhase`s; for each
   phase, calls `EnvironmentCoordinator.execute` with:
   - `requests` = the `ControllerRequest`s for the phase's
     `host_requirements`;
   - `work` = a closure that iterates the cases in the phase,
     runs each via its `ProbeAdapter`, and appends `Sample`s
     to a per-run list captured in the closure.
3. `EnvironmentCoordinator` produces a finalized journal
   (`state: "restored"`, `restoration_status: "succeeded"`)
   and the runner's `work` callback returns. The runner
   converts the journal's `effective` and `after` states into
   `RunResult.environment` entries.
4. Runner assembles `RunResult`; calls
   `RunResultStore.write_local(result)`; returns the result.
5. CLI prints either a table view (case ID, status, samples,
   metrics) or a JSON view (`to_data(result)`).

Failure of one case (probe returns nonzero exit):

1. `work` callback catches the `ProbeError(code: 15)` raised
   by the adapter; marks the case's samples as
   `status: "error"`; continues with the next case in the
   phase (so a single case failure does not abort the phase).
2. After the phase ends, the runner still goes through
   restoration. The partial `RunResult` is written with
   `complete: False`.
3. CLI prints the partial `RunResult` and exits `15`.

### 5.4 Per-case timeout (rationale: 60s default)

The default case timeout is **60 seconds**. The reasoning:

- `chase_pmu` warm pass with the GB10 smoke profile
  (L1-Latency at 32 KiB, 7 samples) is expected to take
  well under 1 second per sample; the 4 KiB cold DRAM
  variant takes longer but still under 10 seconds.
- `chase_migrate` warm + measure is expected to take under
  5 seconds for the GB10 migration matrix.
- `evict_slc --quiet` with 64 MiB and a `posix_memalign`
  working set is bounded by memory bandwidth; on GB10
  this is under 2 seconds.
- 60s is **6×** the worst expected wall time across the
  three probes; it is the safety margin for unexpected
  page-table walks, NUMA cold paths, and contention.
- The 30s alternative is 3× the worst expected; 60s is
  cheaper than a 30s spurious timeout. The 120s
  alternative is wasteful and would mask real hangs.

When a timeout fires, `subprocess.run(..., timeout=N)`
raises `subprocess.TimeoutExpired`. The adapter's
`parse_output(timed_out=True, exit_code=-1, stdout="",
stderr="")` returns `status: "error", failure:
ProbeFailure(stage="timeout", category="case_timeout",
message=f"exceeded {N}s")`. The runner maps this to
`ProbeError(code: 15)`; the case is recorded in the
`RunResult` with `status: "error"` and the surrounding
phase continues. The exit code on timeout is `15` (probe
execution).

### 5.5 Resume sample state machine (rationale: re-record only)

`probe resume`'s `ResumeService` produces a new `RunResult`.
The mapping from the prior `RunResult.samples` to the new
`RunResult.samples` is:

| Prior case status | Action in new `RunResult` |
|---|---|
| `ok` | Carry over the prior `Sample` (preserves its original `run_id`, `sample_index`, `metrics`, `evidence`) |
| `error` | Re-execute the case; record the new `Sample` (with the new run's `run_id` and a new `sample_index`) |
| `skipped` | **Do not re-execute; do not carry over.** The new `RunResult` does not include a sample for this case. |

Rationale:

- `ok` carry-over preserves the user's prior result;
  re-executing an `ok` case would be wasteful and could
  introduce non-determinism if the probe has any noise.
- `error` re-execution is the whole point of `probe resume`.
- `skipped` is **not re-executed and not carried over**
  because a `skipped` sample is not a measurement; it is a
  "this case did not run" record. Carrying it over would
  mislead a future reader of the `RunResult` into
  believing the case was measured in the new run. The
  `ResumeService` records `summary["skipped_cases"]` so
  the user can see which cases were intentionally not
  re-executed.

The new `RunResult` records
`summary["prior_run_id"] = prior.run_id` and
`summary["resume_kind"]` ∈ `{"missing", "failed",
"no-op"}`. (`"missing"` covers the case where a case is
in the new `Plan` but absent from the prior `RunResult`;
`"failed"` covers a case that was present in the prior
`RunResult` with `status: "error"`.)

### 5.6 Schema-version compatibility on resume (rationale: strict reject)

When `probe resume` reads a prior `RunResult` and the
prior's `schema_version` does not match the current
`RunResult` schema version (which is `2` in Phase 3),
the resume aborts with `ProbeError(code: 16)` and the
following structured message:

```text
probe resume: prior RunResult schema_version=1 is not
compatible with the current schema_version=2. Re-run the
original `probe run` from scratch, or wait for a future
`probe convert` command (out of scope for Phase 3).
```

Rationale:

- The Phase 3 schema adds `summary.case_definitions_signature`,
  `summary.repository_commit`, `summary.dirty_tree`,
  `summary.toolchain`, `summary.prior_run_id`,
  `summary.resume_kind`, and `environment.toolchain`.
- A `schema_version=1` prior `RunResult` has **none** of
  these fields. The `case_definitions_signature` in
  particular is the primary defense against resuming
  against a Plan that has been silently mutated; without
  it, a resume against a changed codebase would silently
  succeed and produce a `RunResult` whose sample cases
  are not the same as the recorded ones.
- An "accept but warn" path would leave the `case_definitions_signature`
  as `None` and silently weaken the defense. The cost
  of a strict reject is one re-run for the user; the
  cost of a silent accept is a measurement that does not
  correspond to the recorded cases.
- A "convert" path is a Phase 4 deliverable that requires
  a `probe convert <path>` command. Phase 3 explicitly
  excludes it (per the handoff).

`probe resume` flow:

1. CLI reads the prior `RunResult`; calls
   `RunResultStore.validate_compatibility`.
2. Runner diffs the prior `samples` against the reconstructed
   plan; carries over `status: "ok"` cases; re-runs the rest.
3. The new `RunResult` records `prior_run_id` and
   `resume_kind`. `complete: True` only if every remaining
   case is now `status: "ok"`.

## 6. Test taxonomy (additive; the Phase 2 pyramid stays)

### 6.1 Unit tests (new under `tests/unit/`)

- `test_chase_pmu_adapter.py` — argv builder, `parse_output`
  on captured fixture strings (forwarded to the adapter
  without spawning), `parse_output` on missing/nonzero
  output, `parse_output` with `timed_out=True`.
- `test_evict_slc_adapter.py` — argv builder, default
  `--quiet` (no stdout), `--verbose` parsing.
- `test_chase_migrate_adapter.py` — argv builder, stdout
  parsing across the three `>>>` markers
  (`src_latency`, `migrate_latency`, `migrate_penalty`),
  affinity and hugepage-failure handling.
- `test_runner.py` — groups `Plan` into phases, calls a
  fake `EnvironmentCoordinator` (or a recording fake via
  `tests/support/fake_coordinator.py` — new), assembles
  `RunResult`, propagates exit codes 12/13/14 untouched.
- `test_result_store.py` — atomic write, parent fsync, symlink
  rejection, size cap, `validate_compatibility` table.
- `test_resume.py` — diff logic, repeated-resume idempotency,
  compat rejection (each of the four compat fields).
- `test_characterization_probes.py` — **must be added first**
  (see plan Task 14). Captures current `chase_pmu`,
  `evict_slc`, `chase_migrate` textual output as fixtures and
  asserts the adapters' `parse_output` reproduces the
  expected `metrics`. This is the behavior-pinning layer that
  the handoff requires.

### 6.2 Contract tests (new under `tests/contract/`)

- `test_cli_run.py` — every example in §3.2 (positional
  target list, `--profile`, `--case`, `--allow-mutation`
  absent, output table, output JSON, exit code 11/15/16).
- `test_cli_resume.py` — happy path, prior `RunResult` read
  error (`16`), compat rejection (`16`), no-op
  (resume_kind: "no-op"), repeated resume idempotency.
- `test_run_plan_equivalence.py` — `probe plan` and
  `probe run --output table` produce the same case IDs and
  parameter values for the same selection.
- `test_exit_codes.py` — asserts the existence and integer
  values of `PROBE_EXECUTION (15)` and `RUN_RESULT (16)` in
  `arm64_probe.errors`, and that the contract test table
  matches.
- `test_probe_adapters.py` — the public contract
  (`build_argv`, `parse_output`, `schema_version`,
  `supported_cpu_modes`) is satisfied by every concrete
  adapter. `legacy_wrapper.py` is registered only for
  documentation, not for execution.
- Updates to existing: `test_public_schemas.py` adds
  `sample.schema.json` and `run-result.schema.json` to the
  required-keys table; `test_phase2_acceptance.py` is
  extended to forbid platform-name branches in the new
  `arm64_probe/execution/` and `arm64_probe/execution/adapters/`
  packages.

### 6.3 Integration tests (new under `tests/integration/`)

- `test_phase3_smoke_workflow.py` — boots the runner against
  a fake `Backend` + a recording fake `CommandExecutor`
  + a recording fake `EnvironmentCoordinator`; runs a
  reduced version of the smoke profile; asserts a
  schema-valid `RunResult` lands under a temp
  `results/runs/`.
- `test_phase3_resume_workflow.py` — runs a fixture
  workflow, deletes one of the per-case samples from the
  prior `RunResult`, calls `probe resume`, asserts the new
  `RunResult` has the same run IDs for the carried-over
  cases and new samples for the re-run case.
- `test_phase3_signal_restore.py` — mid-run SIGTERM during
  the runner's `work` callback; the `EnvironmentCoordinator`
  restores the host and the partial `RunResult` is written.
- `test_phase3_fixture_workflow.py` — equivalent of the
  Phase 2 fixture workflow, but for `probe run` against
  `FakeBackend` + `FakeController` + `FakeAdapter` (the last
  one new — see §6.4).

### 6.4 New test infrastructure

- `tests/support/fake_coordinator.py` — records
  `EnvironmentCoordinator.execute` invocations and returns a
  recorded `EnvironmentJournal`. Mirrors the role of
  `fake_controllers.FakeController`.
- `tests/support/fake_adapter.py` — implements
  `ProbeAdapter` with a configurable `parse_output` stub
  and argv recorder. Mirrors the role of
  `fake_controllers.FakeController` for the probe layer.
- `tests/support/executor_recorder.py` — implements
  `CommandExecutor` from `arm64_probe/backends/io.py:19`
  with a queue of recorded `argv` and scripted
  `CompletedProcess` responses. Used to drive the runner
  without spawning real probes.
- `tests/fixtures/probe_output/` — captured stdout/stderr
  fixtures from the current C probes, used by
  `test_characterization_probes.py` and the per-adapter unit
  tests.

### 6.5 Makefile contract tests (new under `tests/`)

- `tests/test_makefile_contract.py` is extended with:
  - `test_phase3_wrappers_are_thin` — asserts `make smoke`
    and `make phase3-check` exist; `smoke` calls
    `uv run --no-sync python` (or the same `$(UV_RUN) python`
    pattern the existing wrappers use) and `phase3-check`
    calls `unittest discover` + `legacy_manifest.py verify` +
    an additional Phase-3-specific contract invocation.
  - `test_phase3_targets_have_no_parsing_or_mutation_logic` —
    the `smoke` and `phase3-check` recipes contain no
    `if/else` on platform, no `/sys/`, no `python3` literal,
    no probe output parser.

## 7. Makefile targets (additive; the Phase 2 targets stay)

```makefile
phase3-check:
	$(UV_RUN) python -m unittest discover -s tests -p 'test_*.py' -v
	$(UV_RUN) python scripts/legacy_manifest.py verify
	$(UV_RUN) python -m unittest tests.contract.test_exit_codes -v
	$(UV_RUN) python -m unittest tests.contract.test_run_plan_equivalence -v
	$(UV_RUN) python -m unittest tests.contract.test_cli_run -v
	$(UV_RUN) python -m unittest tests.contract.test_cli_resume -v

smoke:
	$(UV_RUN) python ./probe plan --platform gb10 --profile smoke -o json > $(BUILD_DIR)/smoke-plan.json
	$(UV_RUN) python ./probe run --platform gb10 --profile smoke --allow-mutation \
	    --output-dir $(BUILD_DIR)/smoke-runs
```

`phase3-check` reuses the existing `unittest discover` and
`legacy-check` bodies; it adds three Phase-3-specific
contract invocations so the per-AC evidence is explicit.
`smoke` invokes the actual CLI in dry-run fixture mode (see
§8.1).

`smoke` does **not** mutate the host. The
`--allow-mutation` flag is present in the dry-run recipe
solely to exercise the authorization code path; the runner
itself, when given a fake `Backend` that exposes no
controllers, never invokes `EnvironmentCoordinator.execute`
with non-empty `requests`, so the mutation lock is never
touched. AC8 is satisfied by the dry-run form.

## 8. Open questions (deferred to the implementation plan)

These are not blockers for the spec. The implementation plan
either resolves them or documents the decision explicitly.

1. **Probe stdin / output capture.** The existing C probes
   write to stdout; `evict_slc --quiet` writes only to
   stderr. The `CommandExecutor` protocol captures both.
   The adapters use `subprocess.run(..., capture_output=True)`
   via the injected `CommandExecutor`. No new decision.
2. **CPU pinning.** `chase_migrate` takes `--src-cpu` and
   `--dst-cpu` via argv; `chase_pmu` requires an external
   `taskset -c`. The runner's argv builder for `chase_pmu`
   emits `taskset -c <cpu>` only when the user passed
   `--cpu`; the argv passed to `subprocess.run` is
   `("taskset", "-c", str(cpu), probe_binary, *args)`. The
   runner does not import `taskset` as a library; it
   `CommandExecutor.run(argv)` it.
3. **Resume of multi-phase runs.** A prior `RunResult` may
   span multiple environment phases. `probe resume` must
   re-execute every case that produced a non-`"ok"`
   sample, in the order they appear in the plan, and must
   re-open the prior phase groups so the journal
   transaction sequence matches. The runner does this
   by iterating `plan.environment_phases` and re-running
   only the cases that are not already `status: "ok"`.
4. **Characterization fixture capture method.** Phase 3
   ships characterization fixtures as **hand-rolled
   byte-for-byte snapshots** in
   `tests/fixtures/probe_output/`. The capture procedure
   is documented in a code-handoff document
   `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md`
   (added in Task 14), not in a `tests/support/capture.py`
   script. The rationale is that an in-tree capture script
   would need to spawn the C probes and is out of scope
   for Phase 3. The handoff document lists, for each
   fixture file, the exact `subprocess.run` argv and
   capture flags needed to populate the fixture on a
   future developer machine.

## 9. What this design explicitly does NOT do

- It does not introduce `probe analyze` or `probe report`.
  These are Phase 4 (per the handoff §1).
- It does not introduce a "v1.0 baseline" command. The
  baseline promotion is a filesystem copy (or a Phase 4
  `probe promote`).
- It does not declare GB10 Gate 1 readiness. The
  announcement gate is owned by the user; the spec
  defines the runbook (see the plan §Phase Completion
  Gate).
- It does not modify `runner/run_pmu*.sh`, `data/`,
  `analysis/`, `baseline/`, or `runner/cache_info_*.sh`.
- It does not relax the `requires-python = "==3.13.13"`
  toolchain pin.
- It does not introduce any new `subprocess` shell command
  or `sudo` invocation.
- It does **not** add a `probe convert` command for
  `schema_version=1 → 2` upgrade. That is a Phase 4
  deliverable. Phase 3 strict-rejects incompatible
  schemas.

## 10. Schema additions (additive)

`schemas/sample.schema.json` and `schemas/run-result.schema.json`
already exist (see Phase 2). They are extended with the
following optional fields (additive; no breaking change):

- `sample.schema.json`:
  - `toolchain` (object): `python_version`, `uv_version`.
- `run-result.schema.json`:
  - `summary.case_definitions_signature` (string, 64 hex).
  - `summary.repository_commit` (string, 40 hex).
  - `summary.dirty_tree` (boolean).
  - `summary.toolchain` (object, same as above).
  - `summary.prior_run_id` (string, optional).
  - `summary.resume_kind` (one of `null`, `"missing"`,
    `"failed"`, `"no-op"`).
  - `environment.toolchain` (object).

These additions are required by AC4 ("results record
… repository commit, dirty-tree status, toolchain/compiler
evidence"). The schemas are versioned; `schema_version` is
already in `RunResult` and bumped to `2` for these additions.
The handoff's compatibility rule for `probe resume` (§3.3
above) explicitly checks `schema_version` first, so the
`1 → 2` bump is gated; see §5.6 for the rationale.

## 11. Cross-references

| Section | Reads |
|---|---|
| §2 | `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §2 (locked architecture) |
| §3 | `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §3 (required public behavior), `docs/superpowers/specs/2026-06-12-arm64-uarch-probe-v1.0-design.md` §7.4–§7.5 |
| §4 | `arm64_probe/domain/models.py`, `arm64_probe/environment/coordinator.py`, `arm64_probe/backends/base.py`, `arm64_probe/backends/io.py` |
| §5 | same as §4 plus `arm64_probe/environment/journal.py:338` (atomic-write pattern) |
| §5.4 | `src/chase_pmu/chase_pmu_v2.7.3.c` (warm pass timing), `src/chase_migrate/chase_migrate_v1.0.c` (warm + measure timing), `src/evict_slc/evict_slc_v1.2.c` (default `--quiet` runtime) |
| §5.5 | the prior `RunResult` sample status enum (`"ok" | "error" | "skipped"`) |
| §5.6 | the schema-version compatibility rule in `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §AC5 |
| §6 | `tests/support/host_fixture.py`, `tests/support/fake_controllers.py`, `tests/contract/test_phase2_acceptance.py` (the AC source of truth) |
| §7 | `Makefile` (existing `UV`, `UV_RUN`, `phase1-check`, `phase2-check` definitions) |
| §10 | `schemas/sample.schema.json`, `schemas/run-result.schema.json` |

The companion `plans/2026-06-15-phase3-probes-runner.md`
translates this design into Task 14–Task 20, each with
file map, test map, commit boundary, and verification
command, and maps each task back to the AC1–AC9 criteria
the handoff fixed.

## 12. Architecture Decision Rationale (consolidated)

This section consolidates the explicit decision rationales
for the 9 architectural decisions the brainstorming flow
captured, so the reader can audit the design without
re-reading the dialogue.

| # | Decision | Rationale | Locked by |
|---|---|---|---|
| 1 | Transaction granularity: per environment phase, not per case | Handoff §2.1; reduces lock overhead and groups `host` mutations atomically | handoff |
| 2 | Resume data source: prior structured `RunResult` (not journal) | Handoff §2.2; journals describe host state, results describe measurement state | handoff |
| 3 | ProbeAdapter boundary: `EvictSlcAdapter` registered against synthetic `evict-slc.setup`, not in `probe run` happy path | Cold-DRAM case uses `ChasePmuAdapter` directly; `evict_slc` is a future setup tool, not Phase 3 surface | design (low risk, handoff-compatible) |
| 4 | Schema `1 → 2` upgrade on resume: **strict reject** (exit `16`) | `case_definitions_signature` is the primary defense against silent case-set drift; auto-conversion would weaken it. Cost of reject: one re-run. | brainstorming (high-leverage) |
| 5 | Resume sample state machine: re-record only (don't carry error → ok; don't carry `skipped`; carry `ok`) | Carrying `ok` preserves user result; re-recording `error` is the resume point; `skipped` is "did not run" — carrying it misleads | brainstorming (high-leverage) |
| 6 | Default case timeout: `60` seconds (override via `--case-timeout` / `--no-case-timeout`) | 6× the worst expected wall time across the three probes; cheaper than spurious 30s timeouts; 120s is wasteful | brainstorming (high-leverage) |
| 7 | Characterization fixture capture: hand-rolled byte-for-byte snapshots, documented in a code-handoff (no `tests/support/capture.py`) | An in-tree capture script would need to spawn the C probes; hand-rolled fixtures are reproducible from any developer machine | brainstorming (high-leverage) |
| 8 | Mutation-vs-non-mutation boundary: enforced by Phase 2 contract (missing `--allow-mutation` → `11` before host writes) | The `--allow-mutation` flag is required when the plan contains any `host` requirement; not a new decision | handoff |
| 9 | GB10 Gate 1 runbook commit: included in the Phase 3 acceptance commit; user reviews the runbook at Gate 1 time | The runbook is a deliverable, not code; bundling it with the acceptance evidence keeps the handoff chain complete | design (low risk) |

The first two are architect-locked; the next seven are
implementer-asserted under the brainstorming flow.
