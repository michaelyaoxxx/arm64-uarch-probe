# Phase 3 GB10 Gate 1 Runbook

> **Status:** user-executed runbook. The implementer does **not** run this.
> This document is the AC9 deliverable per the Phase 3 acceptance contract.

## Preconditions

- A clean GB10 checkout on the `codex/phase3-implementation` branch.
- `make sync` has completed successfully.
- Pinned CPython 3.13.13 and `uv` are available.
- A C compiler (`cc`) is available.
- The user has `root` or equivalent privilege for `--allow-mutation`.
- No prior `make check` or `make phase3-check` failure is present on Mac.

## Step 1: Record Commit and Clean-Tree Evidence

```sh
git rev-parse HEAD
git status --short
```

Expected: exactly one commit SHA; `git status` reports no modified or untracked
files (or only intentionally unstaged files such as this runbook).

Save the commit SHA as `gate1-commit.txt`.

## Step 2: Capture Toolchain Evidence

```sh
uv run --no-sync python -V
uv --version
cc --version
uname -srm
```

Save each output line into `gate1-toolchain.txt`.

## Step 3: Build Probes

```sh
make build
file build/bin/chase_pmu
file build/bin/evict_slc
file build/bin/chase_migrate
```

Expected: all three probe binaries are built and reported as ELF executables.
Record the `file` output into `gate1-build.txt`.

## Step 4: Run Phase 3 Acceptance Checks

```sh
make phase3-check
```

Expected: all tests pass; output ends with `OK`. Record the final test count
and status line into `gate1-phase3-check.txt`.

## Step 5: Run Doctor

```sh
./probe doctor -o json > results/gate1-doctor.json
```

Expected: exit `0`; JSON output contains `backend_id`, `observations`, and
`journals` keys. Save the artifact at `results/gate1-doctor.json`.

## Step 6: Generate a Plan

```sh
./probe plan --platform gb10 --profile smoke -o json > results/gate1-plan.json
```

Expected: exit `0`; JSON output contains `cases` and `environment_phases`.
Save the artifact at `results/gate1-plan.json`.

## Step 7: Execute the Smoke Run

```sh
./probe run --platform gb10 --profile smoke --allow-mutation \
    --output-dir results/gate1-runs
```

Expected: exit `0` (all cases `status: "ok"`). A schema-valid `RunResult`
JSON file is written under `results/gate1-runs/`. Record the produced file
path into `gate1-run-path.txt`.

## Step 8: Verify Restoration

```sh
./probe doctor -o json > results/gate1-doctor-after.json
```

Expected: exit `0`; the `journals` array is empty and no unfinished journal
remains. Compare `gate1-doctor.json` and `gate1-doctor-after.json` to confirm
the host state was fully restored.

## Step 9: Do Not Expand

Do **not** add resume / rerun invocations on GB10 merely for Gate 1.
The AC5 fixture evidence on Mac already proves `probe resume`.
Do **not** run broad exploratory measurements; Gate 1 is intentionally the
minimal smoke profile only.

## Artifact Checklist

| # | Artifact | Path |
|---|----------|------|
| 1 | Commit SHA | `results/gate1-commit.txt` |
| 2 | Toolchain evidence | `results/gate1-toolchain.txt` |
| 3 | Build evidence | `results/gate1-build.txt` |
| 4 | Phase 3 check output | `results/gate1-phase3-check.txt` |
| 5 | Doctor (before) | `results/gate1-doctor.json` |
| 6 | Smoke plan | `results/gate1-plan.json` |
| 7 | Smoke run result | `results/gate1-runs/<run-id>.json` |
| 8 | Doctor (after) | `results/gate1-doctor-after.json` |

## Gate Decision

Only the user announces:

```text
GB10 Gate 1 is ready to run
```

Any Gate 1 failure is fixed and revalidated first on Mac/fixture or Linux
ARM64 where possible. Do not iterate on GB10 directly.
