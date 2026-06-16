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

## Artifact Directory Convention

All Gate 1 artifacts land under a single date-stamped directory:

```
results/gate1-YYYYMMDD/
```

**Before starting, run the preamble once:**

```sh
RESULTS="results/gate1-$(date +%Y%m%d)"
mkdir -p "$RESULTS"
echo "Artifacts will be written to: $RESULTS"
```

Every step below uses `$RESULTS/` so commands can be copied and pasted
verbatim.  If you resume a run across shell sessions re-export `RESULTS`.

---

## Step 1: Record Commit and Clean-Tree Evidence

```sh
{
  echo "commit: $(git rev-parse HEAD)"
  echo "branch: $(git branch --show-current)"
  echo "--- git status ---"
  git status --short
} > "$RESULTS/gate1-commit.txt"
cat "$RESULTS/gate1-commit.txt"
```

**Expected:** exactly one commit SHA; `git status` reports no modified or
untracked files (or only intentionally unstaged files).

---

## Step 2: Capture Toolchain Evidence

```sh
{
  echo "python: $(uv run --no-sync python -V 2>&1)"
  echo "uv: $(uv --version)"
  echo "cc: $(cc --version 2>&1 | head -1)"
  echo "uname: $(uname -srm)"
} > "$RESULTS/gate1-toolchain.txt"
cat "$RESULTS/gate1-toolchain.txt"
```

---

## Step 3: Build Probes

```sh
make build

for bin in chase_pmu evict_slc chase_migrate; do
  file "build/bin/$bin"
done > "$RESULTS/gate1-build.txt"
cat "$RESULTS/gate1-build.txt"
```

**Expected:** all three probe binaries built and reported as ELF executables.

---

## Step 4: Run Phase 3 Acceptance Checks

```sh
make phase3-check 2>&1 | tee "$RESULTS/gate1-phase3-check.txt"
```

**Expected:** all tests pass; output ends with `OK`.  Expect ~350 tests on a
current checkout (the exact count is recorded in the artifact).

---

## Step 5: Run Doctor (Pre-Run Environment Snapshot)

```sh
./probe doctor -o json > "$RESULTS/gate1-doctor.json"
echo "--- doctor ---"
python3 -c "
import json
d = json.load(open('$RESULTS/gate1-doctor.json'))
print('backend_id:', d.get('backend_id'))
print('journals:', len(d.get('journals', [])))
print('observations:', len(d.get('observations', [])))
for o in d.get('observations', []):
    print(f'  {o[\"capability_id\"]:40s} {o[\"status\"]}')
"
```

**Expected:** exit `0`; `journals` is `[]` (empty); `host.pmu` reports
`available` (PMU detection fix is in place).

---

## Step 6: Generate a Plan

```sh
./probe plan --platform gb10 --profile smoke -o json > "$RESULTS/gate1-plan.json"
echo "--- plan ---"
python3 -c "
import json
p = json.load(open('$RESULTS/gate1-plan.json'))
print('platform:', p.get('platform_id'))
print('profile:', p.get('profile_id'))
print('cases:', len(p.get('cases', [])))
print('phases:', len(p.get('environment_phases', [])))
for c in p.get('cases', []):
    print(f'  {c[\"id\"]}  [{c[\"status\"]}]')
"
```

**Expected:** exit `0`; 2 cases both `status: "ready"`.

---

## Step 7: Execute the Smoke Run ★

```sh
./probe run --platform gb10 --profile smoke --allow-mutation \
    --output-dir "$RESULTS/runs"

# Record the produced RunResult path
RUNFILE=$(ls -1 "$RESULTS/runs"/*.json 2>/dev/null | head -1)
echo "run-result: $RUNFILE" > "$RESULTS/gate1-run-path.txt"

echo "--- run result ---"
if [ -n "$RUNFILE" ]; then
  python3 -c "
import json
r = json.load(open('$RUNFILE'))
print('run_id:', r.get('run_id'))
print('schema_version:', r.get('schema_version'))
for s in r.get('samples', []):
    print(f'  {s[\"case_id\"][:60]}  [{s[\"status\"]}]')
    if s['status'] != 'ok':
        m = dict(s.get('metrics', {}))
        print(f'    -> {m}')
"
else
  echo "ERROR: no RunResult file produced"
fi
```

**Expected:** exit `0`; all samples `status: "ok"`; a schema-valid v2
`RunResult` JSON is written under `$RESULTS/runs/`.

---

## Step 8: Verify Environment Restoration

```sh
./probe doctor -o json > "$RESULTS/gate1-doctor-after.json"

echo "--- journals before ---"
python3 -c "
import json
d = json.load(open('$RESULTS/gate1-doctor.json'))
print('journals:', json.dumps(d.get('journals', [])))
"
echo "--- journals after ---"
python3 -c "
import json
d = json.load(open('$RESULTS/gate1-doctor-after.json'))
print('journals:', json.dumps(d.get('journals', [])))
"
```

**Expected:** exit `0`; the `journals` array is empty (`[]`) in **both** files.
No unfinished journal remains.

---

## Step 9: Do Not Expand

Do **not** add resume / rerun invocations on GB10 merely for Gate 1.
The AC5 fixture evidence on Mac already proves `probe resume`.
Do **not** run broad exploratory measurements; Gate 1 is intentionally the
minimal smoke profile only.

---

## Artifact Checklist

After a successful run, `ls -R "$RESULTS"` should show:

```
results/gate1-YYYYMMDD/
├── gate1-build.txt
├── gate1-commit.txt
├── gate1-doctor-after.json
├── gate1-doctor.json
├── gate1-phase3-check.txt
├── gate1-plan.json
├── gate1-run-path.txt
├── gate1-toolchain.txt
└── runs/
    └── <run-id>.json
```

| # | Artifact | Path |
|---|----------|------|
| 1 | Commit SHA + clean-tree | `$RESULTS/gate1-commit.txt` |
| 2 | Toolchain evidence | `$RESULTS/gate1-toolchain.txt` |
| 3 | Build evidence | `$RESULTS/gate1-build.txt` |
| 4 | Phase 3 check output | `$RESULTS/gate1-phase3-check.txt` |
| 5 | Doctor (before) | `$RESULTS/gate1-doctor.json` |
| 6 | Smoke plan | `$RESULTS/gate1-plan.json` |
| 7 | Smoke run result | `$RESULTS/runs/<run-id>.json` |
| 8 | Doctor (after) | `$RESULTS/gate1-doctor-after.json` |

## Collecting Results for Feedback

When all steps succeed, package the archive directory and commit on a results
branch:

```sh
# Review what was collected
ls -R "$RESULTS"

# Create a results branch and commit
BRANCH="results/gate1-$(date +%Y%m%d)"
git checkout -b "$BRANCH"
git add "$RESULTS/"
git commit -m "GB10 Gate 1 results $(date +%Y-%m-%d)

Artifacts: commit + toolchain + build + phase3-check + doctor + plan +
run result + doctor-after.

Co-Authored-By: Claude <noreply@anthropic.com>"
git push origin "$BRANCH"
```

After pushing, open a **Draft PR** on GitHub (`results/gate1-YYYYMMDD` →
`codex/phase3-implementation`) so the Mac-side developer can review the
artifacts.

## Gate Decision

Only the user announces:

```text
GB10 Gate 1 is ready to run
```

Any Gate 1 failure is fixed and revalidated first on Mac/fixture or Linux
ARM64 where possible. Do not iterate on GB10 directly.
