# Phase 0 Repository Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish an accurate, testable repository contract before implementing the v1.0 domain model and unified runner.

**Architecture:** Preserve all current source, runner, and data history in place while adding a verifiable legacy manifest, explicit result-retention policy, corrected platform-aware Makefile, and contributor/GitHub workflow documentation. Phase 0 deliberately does not create the final Python package or move legacy scripts; later phases can migrate them after compatibility adapters exist.

**Tech Stack:** Git, Make, C compiler, Python 3 standard library (`unittest`, `hashlib`, `json`, `subprocess`), Bash syntax checks, Markdown.

---

## File Map

- Create `docs/design/repository-contract.md`: authoritative collaboration, platform, dependency, build, result, and legacy policies.
- Create `.github/pull_request_template.md`: require scope, verification, GB10 evidence, and environment-restoration reporting.
- Create `legacy/README.md`: explain frozen historical evidence and supported verification command.
- Create `legacy/manifest.json`: SHA-256 inventory of versioned runner scripts and tracked raw data.
- Create `scripts/legacy_manifest.py`: generate and verify the legacy integrity manifest.
- Create `tests/test_legacy_manifest.py`: verify manifest behavior and mutation detection.
- Modify `.gitignore`: ignore temporary runs, build products, recovery state, and local Python state without ignoring release evidence.
- Create `results/README.md`: explain temporary-run versus committed-baseline policy.
- Create `results/baselines/v1.0/README.md`: define the future v1.0 evidence boundary.
- Create `docs/assets/v1.0/README.md`: define generated publication-figure policy.
- Create `tests/test_repository_policy.py`: test ignore rules and required policy paths.
- Replace `Makefile`: build from `src/`, use `build/bin/`, expose accurate help/check targets, and separate Darwin/Linux probe support.
- Create `tests/test_makefile_contract.py`: test Makefile help, target discovery, and platform behavior.
- Create or update `AGENTS.md`: align contributor guidance with the new repository contract.
- Modify `README.md`: add project-status, stable/legacy boundary, and Phase 0 command navigation.

### Task 1: Point the Local Clone at the Authoritative Repository

**Files:**
- Modify local Git configuration only; no tracked files.

- [ ] **Step 1: Verify the current branch and remote before mutation**

Run:

```bash
git status --short --branch
git remote -v
git rev-parse HEAD
```

Expected: current branch is the Phase 0 implementation branch; the old renamed
remote may still appear as `gb10-cpu-arch-probe`.

- [ ] **Step 2: Update `origin` to the authoritative repository**

Run:

```bash
git remote set-url origin git@github.com:michaelyaoxxx/arm64-uarch-probe.git
```

- [ ] **Step 3: Verify remote identity and history continuity**

Run:

```bash
git remote -v
git ls-remote --symref origin HEAD
git merge-base --is-ancestor bc6c1ef1e6187ddd239b6d3b78298d6fbe7a4bff HEAD
```

Expected: fetch/push URLs use `arm64-uarch-probe`; remote HEAD is `main`; the
historical pre-v1.0 baseline commit remains an ancestor.

### Task 2: Document the Repository and GitHub Collaboration Contract

**Files:**
- Create: `docs/design/repository-contract.md`
- Create: `.github/pull_request_template.md`
- Test: manual Markdown and content checks in this task

- [ ] **Step 1: Create the repository contract**

Create `docs/design/repository-contract.md` with this content:

```markdown
# Repository Contract

## Authority and Collaboration

`michaelyaoxxx/arm64-uarch-probe` is the only authoritative repository.
Mac and GB10 exchange code, configuration, selected results, and documents
through branches, pull requests, commits, and tags. Do not maintain divergent
copies or develop directly on `main`.

## Platform Responsibilities

- Mac: development, unit/contract tests, offline analysis, figures, and docs.
- Linux ARM64: Linux build and backend behavior checks.
- GB10: authoritative hardware measurements and release gates.

Mac measurements validate software behavior only; they are not GB10 baselines.

## Runtime and Development Dependencies

GB10 runtime code may depend on compiled probes, Bash/system utilities, and the
Python standard library. Third-party Python packages are development or
analysis dependencies and must be installed through repository-owned metadata.

## Build and Verification Contract

- `make help`: list accurate supported targets.
- `make show-targets`: show source-to-binary mappings and platform support.
- `make build`: build probes supported on the current host.
- `make build-linux`: build all Linux probes; reject non-Linux hosts.
- `make check`: run repository policy, legacy integrity, Makefile contract, and
  shell-syntax checks.

## Legacy Evidence

Current versioned runner scripts and tracked `data/` files are frozen historical
evidence. Verify them with `make legacy-check`. Do not change them for v1.0
features. Later migration requires an explicit compatibility plan.

## Result Retention

`results/runs/` and recovery state are temporary and ignored. Commit only
reviewed release evidence under `results/baselines/<version>/` and publication
figures under `docs/assets/<version>/`.

## GB10 Handoff

Every GB10 run records the exact Git commit or tag. GB10 result branches include
the selected profile/scenarios, environment state, commands, failures, and
restoration status. Release-candidate runs use immutable RC tags.
```

- [ ] **Step 2: Create the pull-request template**

Create `.github/pull_request_template.md`:

```markdown
## Scope

- What changed:
- Why:
- Explicitly out of scope:

## Verification

- [ ] `make check`
- [ ] Current-host build or documented reason it was not run
- [ ] No unrelated legacy evidence changed

## Hardware Evidence

- GB10 required: no / Gate 1 / Gate 2 / Gate 3
- Git commit or tag used:
- Scenarios/profile:
- Result paths:

## Environment Safety

- Environment mutation required:
- Restoration verified:
- Recovery journal or known limitation:
```

- [ ] **Step 3: Verify required policy language**

Run:

```bash
python3 - <<'PY'
from pathlib import Path

contract = Path("docs/design/repository-contract.md").read_text()
template = Path(".github/pull_request_template.md").read_text()

for phrase in (
    "michaelyaoxxx/arm64-uarch-probe",
    "make legacy-check",
    "results/baselines/<version>/",
    "Every GB10 run records the exact Git commit or tag",
):
    assert phrase in contract, phrase

for phrase in ("GB10 required", "Restoration verified", "make check"):
    assert phrase in template, phrase
PY
```

Expected: exit 0 with no output.

- [ ] **Step 4: Commit the collaboration contract**

Run:

```bash
git add docs/design/repository-contract.md .github/pull_request_template.md
git commit -m "Document repository collaboration contract"
```

### Task 3: Freeze Historical Runner and Data Evidence

**Files:**
- Create: `legacy/README.md`
- Create: `scripts/legacy_manifest.py`
- Create: `tests/test_legacy_manifest.py`
- Generate: `legacy/manifest.json`

- [ ] **Step 1: Write the failing legacy-manifest tests**

Create `tests/test_legacy_manifest.py`:

```python
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "legacy_manifest.py"
MANIFEST = ROOT / "legacy" / "manifest.json"


class LegacyManifestTests(unittest.TestCase):
    def test_committed_manifest_verifies(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "verify", "--manifest", str(MANIFEST)],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("legacy manifest verified", result.stdout)

    def test_manifest_inventory_matches_tracked_legacy_files(self):
        payload = json.loads(MANIFEST.read_text())
        output = subprocess.check_output(
            ["git", "ls-files", "runner/run_pmu*.sh", "data/**/*.txt"],
            cwd=ROOT,
            text=True,
        )
        tracked = {line for line in output.splitlines() if line}
        self.assertEqual(set(payload["files"]), tracked)

    def test_mutation_is_detected(self):
        source = ROOT / "runner" / "run_pmu_v2.7.3.sh"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            changed = tmp_root / "changed.sh"
            changed.write_bytes(source.read_bytes() + b"\n# mutation\n")
            manifest = {
                "source_commit": "test",
                "files": {str(changed): "0" * 64},
            }
            manifest_path = tmp_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(manifest_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("digest mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_legacy_manifest -v
```

Expected: FAIL because `scripts/legacy_manifest.py` and
`legacy/manifest.json` do not exist.

- [ ] **Step 3: Implement the legacy manifest tool**

Create `scripts/legacy_manifest.py`:

```python
#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "legacy" / "manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tracked_legacy_paths() -> list[Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "runner/run_pmu*.sh", "data/**/*.txt"],
        cwd=ROOT,
        text=True,
    )
    return [ROOT / line for line in output.splitlines() if line]


def generate(manifest_path: Path, source_commit: str) -> None:
    files = {
        str(path.relative_to(ROOT)): digest(path)
        for path in sorted(tracked_legacy_paths())
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"source_commit": source_commit, "files": files},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"wrote {manifest_path} ({len(files)} files)")


def verify(manifest_path: Path) -> int:
    payload = json.loads(manifest_path.read_text())
    failures: list[str] = []
    for raw_path, expected in payload["files"].items():
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file():
            failures.append(f"missing file: {raw_path}")
        elif digest(path) != expected:
            failures.append(f"digest mismatch: {raw_path}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"legacy manifest verified ({len(payload['files'])} files)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    write = sub.add_parser("write")
    write.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    write.add_argument("--source-commit", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    if args.command == "write":
        generate(args.manifest, args.source_commit)
        return 0
    return verify(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the initial manifest from the frozen baseline**

Run:

```bash
python3 scripts/legacy_manifest.py write \
  --source-commit bc6c1ef1e6187ddd239b6d3b78298d6fbe7a4bff
```

Expected: reports a manifest containing all tracked `runner/run_pmu*.sh` and
`data/**/*.txt` files.

- [ ] **Step 5: Document the legacy boundary**

Create `legacy/README.md`:

```markdown
# Legacy Evidence

The versioned `runner/run_pmu*.sh` scripts and tracked `data/**/*.txt` files
are frozen evidence from the pre-v1.0 GB10 investigation.

- Do not modify them for v1.0 features.
- Verify integrity with `python3 scripts/legacy_manifest.py verify`.
- Keep files in their historical paths until a reviewed compatibility migration
  can preserve traceability.
- New runs belong under ignored `results/runs/`; reviewed release evidence
  belongs under `results/baselines/<version>/`.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_legacy_manifest -v
python3 scripts/legacy_manifest.py verify
```

Expected: 3 tests pass and the manifest verifies.

- [ ] **Step 7: Commit the legacy freeze**

Run:

```bash
git add legacy scripts/legacy_manifest.py tests/test_legacy_manifest.py
git commit -m "Freeze legacy runner and data evidence"
```

### Task 4: Establish Temporary-Run and Release-Evidence Policy

**Files:**
- Modify: `.gitignore`
- Create: `results/README.md`
- Create: `results/baselines/v1.0/README.md`
- Create: `docs/assets/v1.0/README.md`
- Create: `tests/test_repository_policy.py`

- [ ] **Step 1: Write failing repository-policy tests**

Create `tests/test_repository_policy.py`:

```python
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path],
        cwd=ROOT,
    )
    return result.returncode == 0


class RepositoryPolicyTests(unittest.TestCase):
    def test_temporary_paths_are_ignored(self):
        for path in (
            "build/bin/chase_pmu",
            "results/runs/example/manifest.json",
            "results/.locks/active.lock",
            "results/.recovery/session.json",
            ".venv/bin/python",
            "arm64_probe/__pycache__/module.pyc",
        ):
            with self.subTest(path=path):
                self.assertTrue(ignored(path))

    def test_release_evidence_is_not_ignored(self):
        for path in (
            "results/baselines/v1.0/manifest.json",
            "docs/assets/v1.0/cache-latency.svg",
        ):
            with self.subTest(path=path):
                self.assertFalse(ignored(path))

    def test_policy_documents_exist(self):
        for path in (
            "results/README.md",
            "results/baselines/v1.0/README.md",
            "docs/assets/v1.0/README.md",
        ):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_repository_policy -v
```

Expected: FAIL because ignore rules and policy files do not exist.

- [ ] **Step 3: Replace `.gitignore` with explicit policy**

Set `.gitignore` to:

```gitignore
*.o
build/
tools/bin/
bin/
backup/
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
results/runs/
results/.locks/
results/.recovery/
```

- [ ] **Step 4: Create result-policy documents**

Create `results/README.md`:

```markdown
# Results

- `runs/` contains temporary local executions and is ignored by Git.
- `.locks/` and `.recovery/` contain runtime coordination and recovery state.
- `baselines/<version>/` contains reviewed evidence committed for a release.

Do not promote a run by copying every generated file. Select the manifest,
structured results, raw logs needed for traceability, anomalies, and limitations
during review.
```

Create `results/baselines/v1.0/README.md`:

```markdown
# v1.0 Baseline Evidence

This directory will contain the reviewed GB10 v1.0 release manifest, structured
case results, selected raw logs, anomaly evidence, and traceability notes.
Temporary and failed exploratory runs remain under ignored `results/runs/`.
```

Create `docs/assets/v1.0/README.md`:

```markdown
# v1.0 Publication Figures

Commit final figures referenced by v1.0 result documents here. Every figure
must identify its structured baseline input and regeneration command.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest tests.test_repository_policy -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit result-retention policy**

Run:

```bash
git add .gitignore results docs/assets/v1.0 tests/test_repository_policy.py
git commit -m "Define result retention policy"
```

### Task 5: Replace the Broken Makefile Contract

**Files:**
- Modify: `Makefile`
- Create: `tests/test_makefile_contract.py`

- [ ] **Step 1: Write failing Makefile contract tests**

Create `tests/test_makefile_contract.py`:

```python
import platform
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def make(*targets: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *targets],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


class MakefileContractTests(unittest.TestCase):
    def test_help_lists_stable_phase0_targets(self):
        result = make("help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for target in ("build", "build-linux", "check", "legacy-check", "show-targets"):
            self.assertIn(target, result.stdout)

    def test_show_targets_uses_src_and_build_bin(self):
        result = make("show-targets")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("src/chase_pmu/chase_pmu_v2.7.3.c -> build/bin/chase_pmu", result.stdout)
        self.assertIn("src/evict_slc/evict_slc_v1.2.c -> build/bin/evict_slc", result.stdout)
        self.assertIn("src/chase_migrate/chase_migrate_v1.0.c -> build/bin/chase_migrate", result.stdout)

    def test_build_linux_rejects_non_linux(self):
        if platform.system() == "Linux":
            self.skipTest("non-Linux contract")
        result = make("build-linux")
        self.assertEqual(result.returncode, 2)
        self.assertIn("build-linux requires Linux", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_makefile_contract -v
```

Expected: FAIL because the current Makefile discovers nonexistent `tools/`
sources and does not expose the Phase 0 contract.

- [ ] **Step 3: Replace `Makefile` with an explicit platform-aware build**

Replace `Makefile` with:

```make
CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -g

BUILD_DIR := build
BIN_DIR := $(BUILD_DIR)/bin
UNAME_S := $(shell uname -s)

CHASE_PMU_SRC := src/chase_pmu/chase_pmu_v2.7.3.c
EVICT_SLC_SRC := src/evict_slc/evict_slc_v1.2.c
CHASE_MIGRATE_SRC := src/chase_migrate/chase_migrate_v1.0.c

CHASE_PMU_BIN := $(BIN_DIR)/chase_pmu
EVICT_SLC_BIN := $(BIN_DIR)/evict_slc
CHASE_MIGRATE_BIN := $(BIN_DIR)/chase_migrate

LINUX_BINS := $(CHASE_PMU_BIN) $(EVICT_SLC_BIN) $(CHASE_MIGRATE_BIN)

ifeq ($(UNAME_S),Linux)
HOST_BINS := $(LINUX_BINS)
else
HOST_BINS := $(EVICT_SLC_BIN)
endif

.PHONY: all build build-linux check legacy-check shell-check show-targets clean help

all: build

build: $(HOST_BINS)
	@echo "[OK] Built probes supported on $(UNAME_S)"

build-linux:
	@if [ "$(UNAME_S)" != "Linux" ]; then \
		echo "[ERROR] build-linux requires Linux" >&2; \
		exit 2; \
	fi
	@$(MAKE) $(LINUX_BINS)

$(BIN_DIR):
	@mkdir -p $@

$(CHASE_PMU_BIN): $(CHASE_PMU_SRC) | $(BIN_DIR)
	$(CC) $(CFLAGS) -o $@ $<

$(EVICT_SLC_BIN): $(EVICT_SLC_SRC) | $(BIN_DIR)
	$(CC) $(CFLAGS) -o $@ $<

$(CHASE_MIGRATE_BIN): $(CHASE_MIGRATE_SRC) | $(BIN_DIR)
	$(CC) $(CFLAGS) -o $@ $<

check:
	python3 -m unittest discover -s tests -p 'test_*.py' -v
	$(MAKE) shell-check

legacy-check:
	python3 scripts/legacy_manifest.py verify

shell-check:
	@for script in runner/*.sh; do \
		echo "[CHECK] bash -n $$script"; \
		bash -n "$$script" || exit 1; \
	done

show-targets:
	@echo "$(CHASE_PMU_SRC) -> $(CHASE_PMU_BIN) [Linux]"
	@echo "$(EVICT_SLC_SRC) -> $(EVICT_SLC_BIN) [Linux,Darwin]"
	@echo "$(CHASE_MIGRATE_SRC) -> $(CHASE_MIGRATE_BIN) [Linux]"

clean:
	rm -rf $(BUILD_DIR)

help:
	@echo "Usage: make <target>"
	@echo "  build         Build probes supported on the current host"
	@echo "  build-linux   Build all Linux ARM64 probes; rejects non-Linux"
	@echo "  check         Run unit/contract and shell-syntax checks"
	@echo "  legacy-check  Verify frozen runner and data evidence"
	@echo "  show-targets  Show source, output, and platform support"
	@echo "  clean         Remove build products"
```

- [ ] **Step 4: Run focused Makefile tests**

Run:

```bash
python3 -m unittest tests.test_makefile_contract -v
make show-targets
make build
```

Expected on Mac: 3 Makefile tests pass; `show-targets` lists all three mappings;
`make build` builds `build/bin/evict_slc` only.

Expected on Linux ARM64: tests pass with the non-Linux test skipped; the
`make build` command builds all three probes.

- [ ] **Step 5: Run repository checks**

Run:

```bash
make legacy-check
make check
```

Expected: legacy manifest verifies; all Python tests and Bash syntax checks
pass.

- [ ] **Step 6: Commit the Makefile contract**

Run:

```bash
git add Makefile tests/test_makefile_contract.py
git commit -m "Fix repository build contract"
```

### Task 6: Align Contributor and Entry-Point Documentation

**Files:**
- Create or modify: `AGENTS.md`
- Modify: `README.md`
- Test: `tests/test_repository_policy.py`

- [ ] **Step 1: Extend the policy test with documentation assertions**

Add this method to `RepositoryPolicyTests` in
`tests/test_repository_policy.py`:

```python
    def test_entry_documents_describe_current_contract(self):
        agents = (ROOT / "AGENTS.md").read_text()
        readme = (ROOT / "README.md").read_text()
        for phrase in ("make build", "make check", "build/bin", "legacy"):
            with self.subTest(document="AGENTS.md", phrase=phrase):
                self.assertIn(phrase, agents)
        for phrase in ("arm64-uarch-probe", "GB10", "make help", "legacy"):
            with self.subTest(document="README.md", phrase=phrase):
                self.assertIn(phrase, readme)
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_repository_policy.RepositoryPolicyTests.test_entry_documents_describe_current_contract -v
```

Expected: FAIL because current entry documents do not describe the Phase 0
contract.

- [ ] **Step 3: Create or update `AGENTS.md`**

Ensure `AGENTS.md` contains these concise repository-specific sections:

```markdown
# Repository Guidelines

## Repository Boundaries

GB10 is the only supported v1.0 measurement platform. Mac validates software
behavior and generates offline analysis; Mac measurements are not GB10
baselines. Versioned `runner/run_pmu*.sh` scripts and tracked `data/` are frozen
legacy evidence.

## Build and Verification

- `make help`: show accurate repository targets.
- `make show-targets`: show source-to-`build/bin` mappings and platform support.
- `make build`: build probes supported by the current host.
- `make build-linux`: build all probes on Linux.
- `make check`: run repository tests and shell syntax checks.
- `make legacy-check`: verify frozen legacy evidence.

## Change Rules

Keep C probes in `src/<probe>/`, temporary output in ignored `results/runs/`,
reviewed release evidence in `results/baselines/<version>/`, and publication
figures in `docs/assets/<version>/`. Do not modify legacy evidence for new
features. Record exact commands, Git commit, environment state, and restoration
status for GB10 runs.

## Commits and Pull Requests

Use focused imperative commits. Pull requests must state scope, verification,
whether GB10 evidence is required, and whether environment restoration was
verified.
```

- [ ] **Step 4: Add a current-contract introduction to `README.md`**

Insert this section immediately after the top-level title:

````markdown
## Project Status

`arm64-uarch-probe` is being prepared as a reproducible and extensible v1.0
GB10 microarchitecture research baseline. GB10 is the authoritative measurement
platform; Mac and Linux ARM64 environments validate engineering behavior.

Current versioned `runner/run_pmu*.sh` scripts and tracked `data/` are frozen
legacy evidence. The stable v1.0 runner will be introduced in later phases.

Start with:

```sh
make help
make show-targets
make build
make check
```

See `docs/design/repository-contract.md` for collaboration, result-retention,
and hardware-handoff rules.
````

- [ ] **Step 5: Run the focused and full checks**

Run:

```bash
python3 -m unittest tests.test_repository_policy -v
make check
git diff --check
```

Expected: repository-policy tests and full checks pass; no whitespace errors.

- [ ] **Step 6: Commit contributor documentation**

Run:

```bash
git add AGENTS.md README.md tests/test_repository_policy.py
git commit -m "Align contributor guidance with repository contract"
```

### Task 7: Verify Phase 0 Acceptance

**Files:**
- No new files; verification only.

- [ ] **Step 1: Verify only intended legacy files are covered**

Run:

```bash
python3 scripts/legacy_manifest.py verify
python3 - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("legacy/manifest.json").read_text())
paths = set(payload["files"])
assert paths
assert all(p.startswith("runner/run_pmu") or p.startswith("data/") for p in paths)
assert not any(p.startswith("runner/cache_info") for p in paths)
PY
```

Expected: manifest verifies and contains only historical experiment runners and
tracked raw data.

- [ ] **Step 2: Verify build and test contracts**

Run:

```bash
make clean
make help
make show-targets
make build
make check
git diff --check
```

Expected: commands match the current host contract and all checks pass.

- [ ] **Step 3: Verify repository state and history**

Run:

```bash
git status --short --branch
git remote -v
git log --oneline --decorate -8
git diff main...HEAD --stat
```

Expected: only intentional pre-existing untracked files, if any, remain;
`origin` uses `arm64-uarch-probe`; Phase 0 commits are focused; existing history
is preserved.

- [ ] **Step 4: Review Phase 0 before planning Phase 1**

Confirm:

- Repository contract is accurate.
- Legacy evidence is unchanged and verifiable.
- Makefile describes actual paths and platform support.
- Mac checks pass without claiming GB10 performance validity.
- No final CLI/domain/backend implementation was pulled into Phase 0.

Do not begin Phase 1 until this review is accepted.
