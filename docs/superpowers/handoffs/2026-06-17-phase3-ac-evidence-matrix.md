# Phase 3 AC1–AC9 Evidence Matrix

> **Handoff reference:** `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §4
> **Verification date:** 2026-06-17
> **Platforms:** macOS ARM64 (M4) + Linux ARM64 (GB10)

No criterion is closed by narrative assertion alone. Every entry links to a
test, command, or artifact.

---

## AC1: Normalized Probe Contract

> All three probes build on their supported hosts, expose normalized named
> arguments, produce machine-readable output that parses into `Sample`, and
> handle malformed/timeout/signal/nonzero-exit output as structured failures.

| Evidence | Path | Result |
|----------|------|--------|
| Adapter unit tests (argv + parse) | `tests/unit/test_probe_adapters.py` (30 tests) | ✅ OK |
| Characterization tests (fixture-driven) | `tests/unit/test_characterization.py` (12 tests) | ✅ OK |
| Adapter protocol contract | `tests/unit/test_adapter_contracts.py` | ✅ OK |
| CLI argv structural contract | `tests/integration/test_probe_cli_contract.py::ProbeAdapterArgvContractTests` (4 tests) | ✅ OK |
| CLI integration (probe accepts argv) | `tests/integration/test_probe_cli_contract.py::ProbeCliContractTests` (7 tests) | ✅ OK |
| Parse contract (real stdout→parse_output) | `tests/integration/test_probe_cli_contract.py::ProbeParseContractTests` (3 tests) | ✅ OK |
| Build verification (all 3 probes compile) | `make build` on GB10 — `results/gate1-20260617/gate1-build.txt` | ✅ 3/3 compiled |

---

## AC2: Selection and Composition

> Individual scenario, parent experiment, arbitrary combination, profile, and
> exact case execution work end to end. `probe run` executes exactly the cases
> shown by the corresponding `probe plan`.

| Evidence | Path | Result |
|----------|------|--------|
| Plan-run case ID equivalence | `tests/contract/test_phase3_acceptance.py::Phase3SmokeWorkflowTests.test_run_and_plan_emit_same_case_ids` | ✅ OK |
| Scenario selection | `tests/contract/test_cli_run.py::RunCommandExecutionTests` | ✅ OK |
| Profile selection (smoke) | `tests/contract/test_cli_run.py::CliRunCommandTests` | ✅ OK |
| Exact case selection (`--case`) | `tests/contract/test_cli_run.py::CliRunCommandTests` | ✅ OK |
| GB10 gate smoke run (2 cases, 0 errors) | `results/gate1-20260617/runs/20260617T012433Z-863fba80.json` | ✅ 2/2 ok |

---

## AC3: Transactional Execution

> Cases grouped by environment phase; each mutating phase runs through
> `EnvironmentCoordinator.execute`. Correct exit codes for missing auth (11),
> apply failure (12), restore failure (13), busy lock (14).

| Evidence | Path | Result |
|----------|------|--------|
| Phase grouping + coordinator routing | `tests/unit/test_runner.py::TestRunner` (8 tests) | ✅ OK |
| Runner handles empty host requirements | `tests/unit/test_runner.py::TestRunner.test_runner_handles_phase_with_no_host_requirements` | ✅ OK |
| Environment fixture workflow | `tests/integration/test_phase3_fixture_workflow.py` (2 tests) | ✅ OK |
| Mutation auth enforcement (exit 11) | `tests/contract/test_cli_run.py::RunCommandExecutionTests` | ✅ OK |
| Signal restoration | `tests/integration/test_environment_signal_restore.py` | ✅ OK |
| Environment coordinator unit tests | `tests/unit/test_environment_coordinator.py` | ✅ OK |

---

## AC4: Structured Results and Provenance

> Every case produces immutable `Sample`; every invocation produces one
> schema-valid `RunResult` (including partial failure). Records run/case ID,
> parameters, metrics, timestamps, platform/backend, repository commit,
> dirty-tree, toolchain evidence, command intent. Writes are atomic.
> JSON is deterministic and passes public schema contract.

| Evidence | Path | Result |
|----------|------|--------|
| Result store atomic write | `tests/unit/test_result_store.py` (11 tests) | ✅ OK |
| Result contracts + provenance | `tests/unit/test_result_contracts.py` (9 tests) | ✅ OK |
| Public schema validation (v2) | `tests/contract/test_public_schemas.py` (3 tests) | ✅ OK |
| Schema v2 fields present in output | `results/gate1-20260617/runs/20260617T012433Z-863fba80.json` — `schema_version: 2`, `case_definitions_signature`, `repository_commit`, `dirty_tree` | ✅ All present |
| Exit codes 15/16 defined | `tests/contract/test_cli_run.py::ExitCodeTests` | ✅ OK |

---

## AC5: Resume and Exact Rerun

> `probe resume --run <path>` executes only missing/failed cases, preserves
> successful samples. Rejects incompatible schema/platform/case-definitions/
> execution-contract changes. Repeated resume is idempotent.

| Evidence | Path | Result |
|----------|------|--------|
| Resume service unit tests | `tests/unit/test_resume.py` (17 tests) | ✅ OK |
| Resume CLI contract | `tests/contract/test_cli_resume.py` (11 tests) | ✅ OK |
| Compatibility rejection (exit 16) | `tests/contract/test_cli_resume.py::CliResumeExecutionTests` | ✅ OK |
| Resume workflow integration | `tests/integration/test_phase3_fixture_workflow.py` | ✅ OK |

---

## AC6: Stable CLI and Makefile

> `probe help run`, `probe help resume`, table/JSON output, structured errors,
> exit codes are contract-tested. Makefile adds thin `smoke` and `phase3-check`
> wrappers only.

| Evidence | Path | Result |
|----------|------|--------|
| Run CLI contract (help + flags + output) | `tests/contract/test_cli_run.py` (14 tests) | ✅ OK |
| Resume CLI contract (help + flags + output) | `tests/contract/test_cli_resume.py` (11 tests) | ✅ OK |
| Makefile contract (thin wrappers) | `tests/test_makefile_contract.py` (13 tests) | ✅ OK |
| No scenario matrix/platform branch in Makefile | `tests/test_makefile_contract.py::test_phase3_wrappers_are_thin` | ✅ OK |
| `probe help run` / `probe help resume` | Manual verification | ✅ Present |

---

## AC7: Compatibility and Boundaries

> Phase 1/2 contracts remain green. No platform-name branches in planning,
> runner, executor, coordinator, or adapters. Frozen/transitional paths
> unchanged. Mac produces validation evidence only.

| Evidence | Path | Result |
|----------|------|--------|
| Phase 2 acceptance still green | `tests/contract/test_phase2_acceptance.py` (7 tests) | ✅ OK |
| No platform-name branch in execution/ | `tests/contract/test_phase3_acceptance.py::Phase3ArchitectureBoundariesTests.test_no_platform_name_branch_in_execution_modules` | ✅ OK |
| CLI routes through Runner (not raw subprocess) | `tests/contract/test_phase3_acceptance.py::Phase3ArchitectureBoundariesTests.test_probe_run_routes_through_runner_not_raw_subprocess` | ✅ OK |
| Frozen paths unchanged | `tests/contract/test_phase3_acceptance.py::Phase3FrozenPathBoundaryTests.test_frozen_paths_remain_unchanged` | ✅ OK |
| Legacy manifest integrity | `make legacy-check` — 17 files verified | ✅ OK |
| Repository policy | `tests/test_repository_policy.py` (9 tests) | ✅ OK |
| Phase 1 acceptance | `tests/contract/test_phase1_acceptance.py` (4 tests) | ✅ OK |

---

## AC8: Minimal Smoke Workflow

> `make sync`, `make build`, `make phase3-check`, `make smoke` complete without
> host mutation and produce a schema-valid `RunResult`.

| Evidence | Path | Result |
|----------|------|--------|
| Smoke workflow integration | `tests/integration/test_phase3_smoke_workflow.py` | ✅ OK |
| Fixture workflow (fake backend) | `tests/integration/test_phase3_fixture_workflow.py` (2 tests) | ✅ OK |
| `make phase3-check` | 365 tests, 0 failures | ✅ OK |
| `make smoke` produces valid RunResult | `tests/contract/test_phase3_acceptance.py::Phase3SmokeWorkflowTests.test_smoke_run_produces_schema_valid_run_result` | ✅ OK |
| GB10 full suite | `results/gate1-20260617/gate1-phase3-check.txt` — 365 passed, 0 failed | ✅ OK |

---

## AC9: GB10 Gate 1

> Gate 1 runs once after AC1-AC8 pass. Clean GB10 checkout: commit evidence,
> toolchain, build, tests, doctor, plan, authorized run, schema-valid result,
> finalized journal, verified restoration.

| Step | Evidence | Result |
|------|----------|--------|
| 1. Commit SHA + clean tree | `results/gate1-20260617/gate1-commit.txt` — `219a91d` (codex/phase3-implementation) | ✅ |
| 2. Toolchain evidence | `results/gate1-20260617/gate1-toolchain.txt` — Python 3.13.13, uv 0.11.21, gcc 13.3.0, Linux aarch64 | ✅ |
| 3. `make build` | `results/gate1-20260617/gate1-build.txt` — 3/3 probes compiled (aarch64) | ✅ |
| 4. `make phase3-check` | `results/gate1-20260617/gate1-phase3-check.txt` — 365 passed, 0 failed | ✅ |
| 5. `probe doctor -o json` | `results/gate1-20260617/gate1-doctor.json` — 9/9 capabilities available, PMU detected | ✅ |
| 6. `probe plan --platform gb10 --profile smoke` | `results/gate1-20260617/gate1-plan.json` — 2 cases planned | ✅ |
| 7. `probe run --allow-mutation` | `results/gate1-20260617/runs/20260617T012433Z-863fba80.json` — 2/2 ok, 0 errors | ✅ |
| 8. Post-run doctor | `results/gate1-20260617/gate1-doctor-after.json` — journals clean | ✅ |

**Gate 1 runbook:** `docs/superpowers/handoffs/2026-06-15-phase3-gate1-runbook.md`

---

## Summary

```
AC1 ✅  AC2 ✅  AC3 ✅  AC4 ✅  AC5 ✅  AC6 ✅  AC7 ✅  AC8 ✅  AC9 ✅
                              ───────────────────────────────────────
                              All 9 acceptance criteria verified
                              365 tests | 0 failures | 2 platforms
```

**Verification commands:**

```sh
make phase3-check    # 365 tests + legacy manifest + Phase 3 acceptance
make check           # contract tests + bash syntax
make legacy-check    # frozen evidence integrity
make build           # compile all probes
make smoke           # end-to-end smoke workflow
```

**GB10 Gate 1 evidence:** `results/gate1-20260617/`
