# Phase 1 Core Domain and CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement immutable v1.0 domain contracts, strict JSON registries, deterministic planning, and the side-effect-free `probe help/list/show/plan` CLI on Mac without requiring GB10 access.

**Architecture:** A Python-standard-library package owns immutable tuple-based domain models, strict registry loaders, a generic configured-platform adapter, and a pure planner. The CLI is a thin consumer of those APIs; declarative JSON contains platform, experiment, scenario, and profile facts, while public JSON schemas and contract tests freeze machine-readable behavior.

**Tech Stack:** Python 3.10+ standard library (`argparse`, `dataclasses`, `enum`, `json`, `pathlib`, `unittest`), strict JSON, JSON Schema documents, Make, Git.

---

## Delivery Boundaries

- Run all Phase 1 work and verification on the Mac.
- Do not read live `/sys` or `/proc`, execute C probes, mutate the environment,
  or modify frozen/transitional paths.
- Keep `runner/run_pmu*.sh`, `data/`, `analysis/`, `baseline/`, and
  `runner/cache_info_*` unchanged.
- Do not claim Apple M4 measurement support; its definition is contract-only.
- GB10 is not required in Phase 1 or Phase 2. At Phase 3 start, issue the
  advance GB10 preparation reminder. Issue the explicit Gate 1 ready notice
  only after the unified runner, environment recovery, and smoke workflow pass.

## File Map

### Runtime Package

- Create `probe`, `arm64_probe/__init__.py`, `arm64_probe/__main__.py`: immediate
  checkout entry point plus its equivalent `python3 -m arm64_probe` entry.
- Create `arm64_probe/errors.py`: stable exit-code enum and structured errors.
- Create `arm64_probe/domain/ids.py`: canonical ID validation and case-ID
  construction.
- Create `arm64_probe/domain/models.py`: immutable domain records.
- Create `arm64_probe/serialization/json_io.py`: strict JSON loading and
  deterministic JSON output.
- Create `arm64_probe/serialization/model_json.py`: model-to-public-data
  conversion.
- Create `arm64_probe/registry/validation.py`: strict configuration validators.
- Create `arm64_probe/registry/catalog.py`: load and index all registry files.
- Create `arm64_probe/platforms/base.py`: platform-adapter protocol.
- Create `arm64_probe/platforms/configured.py`: generic semantic CPU resolver.
- Create `arm64_probe/planning/request.py`: immutable planning request.
- Create `arm64_probe/planning/planner.py`: pure selection, merge, gate, and
  case-generation pipeline.
- Create `arm64_probe/cli/parser.py`, `arm64_probe/cli/render.py`,
  `arm64_probe/cli/main.py`: argument contract, table/JSON rendering, dispatch.

### Declarative Inputs and Public Contracts

- Create `configs/platforms/gb10.json`, `configs/platforms/m4.json`.
- Create `configs/capabilities.json`.
- Create `configs/experiments/cache-latency.json`,
  `configs/experiments/migration-latency.json`.
- Create `configs/profiles/smoke.json`, `configs/profiles/baseline.json`.
- Create `schemas/capability.schema.json`, `schemas/platform.schema.json`,
  `schemas/experiment.schema.json`, `schemas/profile.schema.json`,
  `schemas/case.schema.json`,
  `schemas/plan.schema.json`, `schemas/manifest.schema.json`,
  `schemas/environment.schema.json`, `schemas/sample.schema.json`,
  `schemas/run-result.schema.json`, `schemas/error.schema.json`.
- Create `docs/design/cli-contract.md`: commands, options, exit codes, and
  no-side-effect guarantees.

### Tests and Integration

- Create package markers under `tests/unit/`, `tests/contract/`,
  `tests/integration/`.
- Create focused tests in those directories plus JSON fixtures under
  `tests/fixtures/`.
- Modify `Makefile`: add thin `probe`, `probe-help`, and `phase1-check` targets.
- Modify `README.md`, `AGENTS.md`, and ownership README files only to document
  the implemented Phase 1 interface.

## Public Type Contract

Use these immutable records consistently across all tasks:

```python
JsonScalar = str | int | float | bool | None

@dataclass(frozen=True)
class NamedCpuSet:
    id: str
    cpus: tuple[int, ...]

@dataclass(frozen=True)
class Capability:
    id: str
    description: str

@dataclass(frozen=True)
class ParameterSpec:
    id: str
    kind: str
    choices: tuple[JsonScalar, ...] = ()

@dataclass(frozen=True)
class ResolvedValue:
    value: JsonScalar
    source: str

@dataclass(frozen=True)
class Platform:
    id: str
    display_name: str
    description: str
    measurement_support: str
    capabilities: tuple[str, ...]
    clusters: tuple[NamedCpuSet, ...]
    core_groups: tuple[NamedCpuSet, ...]
    representative_cpus: tuple[tuple[str, int], ...]
    defaults: tuple[tuple[str, JsonScalar], ...]

@dataclass(frozen=True)
class Scenario:
    id: str
    display_name: str
    cpu_mode: str
    required_capabilities: tuple[str, ...]
    parameters: tuple[ParameterSpec, ...]

@dataclass(frozen=True)
class Experiment:
    id: str
    display_name: str
    scenarios: tuple[Scenario, ...]

@dataclass(frozen=True)
class Profile:
    id: str
    display_name: str
    selections: tuple[str, ...]
    overrides: tuple[tuple[str, JsonScalar], ...]
    environment: tuple[tuple[str, JsonScalar], ...]

@dataclass(frozen=True)
class Case:
    id: str
    scenario_id: str
    platform_id: str
    status: str
    reason: str | None
    cpu: int | None
    src_cpu: int | None
    dst_cpu: int | None
    selectors: tuple[tuple[str, ResolvedValue], ...]
    parameters: tuple[tuple[str, ResolvedValue], ...]

@dataclass(frozen=True)
class EnvironmentPhase:
    id: str
    case_ids: tuple[str, ...]
    requirements: tuple[tuple[str, JsonScalar], ...]

@dataclass(frozen=True)
class Plan:
    platform_id: str
    profile_id: str | None
    selections: tuple[str, ...]
    cases: tuple[Case, ...]
    environment_phases: tuple[EnvironmentPhase, ...]
    skip_unavailable: bool
```

`Sample` and `RunResult` use the same tuple-based immutability rule and are
specified in Task 9.

## Batch 1: Public Foundations and Immutable Domain

### Task 1: Establish the Python Package, CLI Error Contract, and Test Discovery

**Files:**
- Create: `probe`
- Create: `arm64_probe/__init__.py`
- Create: `arm64_probe/__main__.py`
- Create: `arm64_probe/errors.py`
- Create: `arm64_probe/cli/__init__.py`
- Create: `arm64_probe/cli/main.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/contract/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/contract/test_cli_foundation.py`
- Create: `docs/design/cli-contract.md`

- [ ] **Step 1: Write failing entry-point and exit-code tests**

Create `tests/contract/test_cli_foundation.py` with subprocess helpers that run
`[sys.executable, "-m", "arm64_probe", ...]`, then assert:

```python
def test_top_level_help_is_side_effect_free(self):
    result = run_probe("--help")
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("usage: probe", result.stdout)
    self.assertIn("list", result.stdout)
    self.assertIn("show", result.stdout)
    self.assertIn("plan", result.stdout)

def test_unknown_command_uses_cli_usage_exit_code(self):
    result = run_probe("unknown-command")
    self.assertEqual(result.returncode, 2)
    self.assertIn("error:", result.stderr)
    self.assertNotIn("Traceback", result.stderr)
```

Also assert that importing `ExitCode` yields `SUCCESS=0`, `USAGE=2`,
`CONFIG=3`, `CAPABILITY=4`, and `PLANNING=5`.
Run the same help assertion through `./probe --help`.

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```sh
python3 -m unittest tests.contract.test_cli_foundation -v
```

Expected: FAIL because the package entry point and error contract do not exist.

- [ ] **Step 3: Implement the minimal package and structured errors**

Implement `arm64_probe/errors.py` with:

```python
class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    CONFIG = 3
    CAPABILITY = 4
    PLANNING = 5


@dataclass(frozen=True)
class ProbeError(Exception):
    code: ExitCode
    category: str
    message: str
    context: tuple[tuple[str, str], ...] = ()
    hint: str | None = None
```

Make both `probe` and `arm64_probe/__main__.py` call `cli.main.main()`. Set the
root script executable with `chmod +x probe`. Implement a minimal `argparse`
parser in `cli/main.py`; until later tasks connect each operation, `list`,
`show`, and `plan` return the same structured planning error. Catch
`ProbeError` and `SystemExit` so no traceback reaches users.

- [ ] **Step 4: Freeze the initial CLI contract document**

Create `docs/design/cli-contract.md` containing:

- the five stable Phase 1 exit codes and the `10+` Phase 3 reservation;
- `./probe` as the immediate-checkout entry point and
  `python3 -m arm64_probe` as its equivalent module entry;
- the `probe --help`, `probe help plan`, `list`, `show`, and `plan` commands;
- `-h/--help` and `-o/--output` as the only Phase 1 short options;
- a statement that every Phase 1 command is side-effect free.

- [ ] **Step 5: Run tests and commit**

Run:

```sh
python3 -m unittest tests.contract.test_cli_foundation -v
git diff --check
git add probe arm64_probe tests/contract tests/unit/__init__.py \
  tests/integration/__init__.py docs/design/cli-contract.md
git commit -m "Establish Phase 1 CLI contract"
```

Expected: focused tests PASS; commit contains no configuration or planner code.

### Task 2: Implement Canonical IDs and Immutable Core Models

**Files:**
- Create: `arm64_probe/domain/__init__.py`
- Create: `arm64_probe/domain/ids.py`
- Create: `arm64_probe/domain/models.py`
- Create: `tests/unit/test_domain_ids.py`
- Create: `tests/unit/test_domain_models.py`

- [ ] **Step 1: Write failing canonical-ID tests**

Cover these exact behaviors:

```python
self.assertEqual(validate_id("cache-latency"), "cache-latency")
self.assertEqual(
    validate_scenario_id("cache-latency.l2-latency"),
    "cache-latency.l2-latency",
)
self.assertEqual(
    build_case_id(
        "cache-latency.l2-latency",
        "gb10",
        ("x925", "c0", "warm", "default-page"),
    ),
    "cache-latency.l2-latency@gb10.x925.c0.warm.default-page",
)
```

Reject uppercase, underscores, empty components, and repeated separators.
Planner tests, rather than `build_case_id`, enforce semantic dimension order.

- [ ] **Step 2: Write failing immutability tests**

Instantiate every record in the Public Type Contract. Assert assignment raises
`dataclasses.FrozenInstanceError`, CPU collections are tuples, and the same
logical inputs compare equal.

- [ ] **Step 3: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.unit.test_domain_ids tests.unit.test_domain_models -v
```

Expected: FAIL because `domain.ids` and `domain.models` do not exist.

- [ ] **Step 4: Implement IDs and models**

In `ids.py`, use compiled ASCII-only regular expressions:

```python
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCENARIO_RE = re.compile(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*\.[a-z0-9]+(?:-[a-z0-9]+)*$"
)
```

Implement `validate_id`, `validate_scenario_id`, and `build_case_id`. Implement
the Public Type Contract in `models.py` with `@dataclass(frozen=True)`.
Normalize all caller-provided sequences to tuples in explicit factory
functions; do not retain mutable dictionaries or lists.

- [ ] **Step 5: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_domain_ids tests.unit.test_domain_models -v
git diff --check
git add arm64_probe/domain tests/unit/test_domain_ids.py \
  tests/unit/test_domain_models.py
git commit -m "Add immutable Phase 1 domain models"
```

Expected: all domain tests PASS.

### Task 3: Add Deterministic JSON I/O and Public Model Serialization

**Files:**
- Create: `arm64_probe/serialization/__init__.py`
- Create: `arm64_probe/serialization/json_io.py`
- Create: `arm64_probe/serialization/model_json.py`
- Create: `tests/unit/test_json_io.py`
- Create: `tests/unit/test_model_json.py`
- Create: `tests/fixtures/json/duplicate-key.json`

- [ ] **Step 1: Write failing strict-JSON tests**

Assert `load_json()` rejects duplicate object keys, malformed UTF-8, invalid
JSON, and non-object roots using `ProbeError(code=ExitCode.CONFIG)`. Assert
`dump_json()`:

```python
self.assertEqual(
    dump_json({"z": 1, "a": {"b": 2}}),
    '{\n  "a": {\n    "b": 2\n  },\n  "z": 1\n}\n',
)
```

- [ ] **Step 2: Write failing model serialization tests**

Construct a `Case` and `Plan`; assert `to_data()` emits lists and dictionaries,
sorts parameter keys, includes every resolved-value source, and contains no
timestamp or run ID.

- [ ] **Step 3: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.unit.test_json_io tests.unit.test_model_json -v
```

Expected: FAIL because serialization modules do not exist.

- [ ] **Step 4: Implement strict loading and deterministic output**

Use `json.loads(text, object_pairs_hook=reject_duplicate_keys)` and wrap
decode/shape errors as `ProbeError(CONFIG, "configuration", ...)`. Implement
`dump_json()` with `indent=2`, `sort_keys=True`, `ensure_ascii=True`, and a
single trailing newline. Implement explicit `to_data()` dispatch for every
domain record; do not use `dataclasses.asdict()` because it loses control of
public field order and tuple normalization.

- [ ] **Step 5: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_json_io tests.unit.test_model_json -v
git diff --check
git add arm64_probe/serialization tests/unit/test_json_io.py \
  tests/unit/test_model_json.py tests/fixtures/json
git commit -m "Add deterministic domain serialization"
```

Expected: serialization tests PASS.

## Batch 2: Strict Registries and Pure Planning

### Task 4: Implement Strict Registry Validation and Platform Definitions

**Files:**
- Create: `arm64_probe/registry/__init__.py`
- Create: `arm64_probe/registry/validation.py`
- Create: `arm64_probe/platforms/__init__.py`
- Create: `arm64_probe/platforms/base.py`
- Create: `arm64_probe/platforms/configured.py`
- Create: `configs/platforms/gb10.json`
- Create: `configs/platforms/m4.json`
- Create: `configs/capabilities.json`
- Create: `tests/fixtures/platforms/invalid-extra-field.json`
- Create: `tests/unit/test_registry_validation.py`
- Create: `tests/contract/test_platform_contract.py`

- [ ] **Step 1: Write failing platform-validation tests**

Assert valid files load into immutable `Platform` and `Capability` records.
Assert unknown fields, duplicate IDs, negative CPUs, overlapping
clusters, representative CPUs outside their named intersection, and unsupported
`measurement_support` values fail with exit code `3`.

- [ ] **Step 2: Write the shared platform contract**

Define one test mixin and run it against both files. It must assert:

- IDs and all selector IDs are canonical;
- CPU sets are sorted and duplicate-free;
- `resolve_single(cluster, core_group, cpu_override)` is deterministic;
- explicit CPU overrides are recorded as `cli`;
- GB10 is `supported`, M4 is `contract-only`;
- M4 reports missing measurement capabilities instead of simulating them.

- [ ] **Step 3: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest \
  tests.unit.test_registry_validation \
  tests.contract.test_platform_contract -v
```

Expected: FAIL because validators, adapters, and platform definitions do not
exist.

- [ ] **Step 4: Create exact platform facts**

Encode GB10 with clusters `c0=0..9`, `c1=10..19`; core groups
`a725=0..4,10..14`, `x925=5..9,15..19`; representative CPUs
`c0.a725=0`, `c0.x925=5`, `c1.a725=10`, `c1.x925=15`; and capabilities
`arm64`, `cpu-binding`, `linux.hugepage`, `linux.cpufreq`, `pmu.armv9`.

Encode M4 as `contract-only` with fixture selector sets and capabilities
limited to `arm64`; its description must explicitly say fixture topology is
not performance evidence. Use fixture clusters `p-cluster=0,1` and
`e-cluster=2,3`, core groups `performance=0,2` and `efficiency=1,3`, and
representative CPUs `p-cluster.performance=0`, `p-cluster.efficiency=1`,
`e-cluster.performance=2`, and `e-cluster.efficiency=3`. These are synthetic
contract facts, not claims about live M4 topology.

Define the five capability IDs and concise descriptions in
`configs/capabilities.json`. Both platform files provide common defaults for
`samples` and `page-policy` plus scoped `working-set` defaults for all eight
scenarios. Scoped default keys use `<scenario-id>.<parameter-id>`, for example
`cache-latency.l1-latency.working-set`. This keeps the approved precedence
rooted at platform defaults.

Capability descriptions are:

```text
arm64: ARM64 instruction-set execution
cpu-binding: bind a measurement to selected logical CPUs
linux.hugepage: inspect and request Linux hugepages
linux.cpufreq: inspect and control Linux CPU-frequency policy
pmu.armv9: access the required ARMv9 PMU events
```

- [ ] **Step 5: Implement strict validators and the generic adapter**

`validation.py` must use explicit allowed/required field sets and type checks.
`base.py` defines a `Protocol` for:

```python
def resolve_single(
    platform: Platform,
    cluster: str | None,
    core_group: str | None,
    cpu_override: int | None,
) -> tuple[int | None, str]: ...

def resolve_pair(
    platform: Platform,
    cpu_mode: str,
    cluster: str | None,
    core_group: str | None,
    src_override: int | None,
    dst_override: int | None,
) -> tuple[int | None, int | None, str]: ...
```

`configured.py` resolves intersections and representative CPUs without
branching on `platform.id`.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest \
  tests.unit.test_registry_validation \
  tests.contract.test_platform_contract -v
git diff --check
git add arm64_probe/registry arm64_probe/platforms configs/capabilities.json \
  configs/platforms \
  tests/unit/test_registry_validation.py tests/contract/test_platform_contract.py \
  tests/fixtures/platforms
git commit -m "Add configured platform contracts"
```

Expected: both platform definitions pass the same contract.

### Task 5: Add Experiment, Scenario, Profile Definitions and Catalog Loading

**Files:**
- Create: `arm64_probe/registry/catalog.py`
- Create: `configs/experiments/cache-latency.json`
- Create: `configs/experiments/migration-latency.json`
- Create: `configs/profiles/smoke.json`
- Create: `configs/profiles/baseline.json`
- Create: `tests/unit/test_catalog.py`
- Create: `tests/contract/test_scenario_catalog.py`

- [ ] **Step 1: Write failing catalog tests**

Assert `Catalog.load(ROOT)` returns exactly:

```python
expected = (
    "cache-latency.l1-latency",
    "cache-latency.l2-latency",
    "cache-latency.l3-latency",
    "cache-latency.slc-latency",
    "cache-latency.dram-latency",
    "migration-latency.same-core",
    "migration-latency.same-cluster",
    "migration-latency.cross-cluster",
)
```

Assert experiment selection expands in this order, profiles reference existing
targets, duplicate IDs fail, and lookup of an unknown ID returns a structured
configuration error. Reject unknown profile environment keys and invalid
environment values.

- [ ] **Step 2: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.unit.test_catalog \
  tests.contract.test_scenario_catalog -v
```

Expected: FAIL because the catalog and definitions do not exist.

- [ ] **Step 3: Create experiment and scenario definitions**

Use `cpu_mode="single"` for all cache scenarios. Use `pair-same-core`,
`pair-same-cluster`, and `pair-cross-cluster` for migration scenarios. Every
scenario declares:

- `samples`: positive integer;
- `working-set`: size string;
- `page-policy`: string choices `default|hugepage`;
- `required_capabilities`: at least `cpu-binding`.

Platform definitions set representative working sets to `32KiB`, `256KiB`,
`4MiB`, `12MiB`, `64MiB` for L1 through DRAM and `4MiB` for migration. These
are planning defaults, not published performance conclusions.

- [ ] **Step 4: Create profiles**

`smoke` selects `cache-latency.l1-latency` and
`migration-latency.cross-cluster` with `samples=1` and
`page-policy=default` and no requested environment mutation. `baseline` selects
both experiments with `samples=7` and requests `cpu-governor=performance`.
Allowed Profile environment keys are `cpu-governor`,
`cpu-frequency-policy`, and `hugepages`. Page policy remains a resolved
scenario parameter and is copied into each environment phase. Phase 1 records
and gates these requirements but never applies them. Governor and frequency
policy values are nonempty canonical strings; `hugepages` is a nonnegative
integer.

- [ ] **Step 5: Implement catalog loading**

`Catalog` stores sorted tuples, loads the capability registry, and exposes:

```python
def experiments(self) -> tuple[Experiment, ...]: ...
def scenarios(self) -> tuple[Scenario, ...]: ...
def profiles(self) -> tuple[Profile, ...]: ...
def platforms(self) -> tuple[Platform, ...]: ...
def capabilities(self) -> tuple[Capability, ...]: ...
def expand_selection(self, target_id: str) -> tuple[Scenario, ...]: ...
def get_profile(self, profile_id: str) -> Profile: ...
def get_platform(self, platform_id: str) -> Platform: ...
```

Load only known `.json` files from the three configuration directories. Reject
unknown fields and cross-reference errors, including unknown capabilities and
scoped platform defaults, before returning the catalog.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_catalog \
  tests.contract.test_scenario_catalog -v
git diff --check
git add arm64_probe/registry/catalog.py configs/experiments configs/profiles \
  tests/unit/test_catalog.py tests/contract/test_scenario_catalog.py
git commit -m "Add Phase 1 scenario catalog"
```

Expected: the catalog exposes two experiments, eight scenarios, two profiles,
and two platforms in deterministic order.

### Task 6: Implement Selection Expansion and Parameter Resolution

**Files:**
- Create: `arm64_probe/planning/__init__.py`
- Create: `arm64_probe/planning/request.py`
- Create: `arm64_probe/planning/planner.py`
- Create: `tests/unit/test_planner_selection.py`
- Create: `tests/unit/test_planner_parameters.py`

- [ ] **Step 1: Write failing selection tests**

Build requests directly, without invoking CLI. Assert:

- selecting `cache-latency` expands five ordered scenarios;
- repeated selections form a deduplicated union;
- profile selections and explicit selections form a union;
- no selection and no profile returns exit code `5`;
- unknown selection returns exit code `5` with an actionable hint.

- [ ] **Step 2: Write failing precedence and applicability tests**

Assert:

```text
platform defaults < profile overrides < explicit request overrides
```

Each `ResolvedValue.source` must be exactly `platform-default`, `profile`, or
`cli`. Reject `samples=0`, unknown page policies, malformed working-set values,
and overrides not declared by every selected scenario.

Resolve scoped platform defaults before common platform defaults; both retain
source `platform-default`.

- [ ] **Step 3: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.unit.test_planner_selection \
  tests.unit.test_planner_parameters -v
```

Expected: FAIL because planning modules do not exist.

- [ ] **Step 4: Implement immutable requests and pure resolution**

Define:

```python
@dataclass(frozen=True)
class PlanRequest:
    platform_id: str = "auto"
    profile_id: str | None = None
    selections: tuple[str, ...] = ()
    cluster: str | None = None
    core_group: str | None = None
    cpu: int | None = None
    src_cpu: int | None = None
    dst_cpu: int | None = None
    overrides: tuple[tuple[str, JsonScalar], ...] = ()
    skip_unavailable: bool = False
```

Implement planner functions for selection expansion and parameter merging.
Validate positive integer samples, the working-set grammar
`^[1-9][0-9]*(KiB|MiB|GiB)$`, declared choices, and parameter applicability.
Do not inspect the host or mutate input records.

- [ ] **Step 5: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_planner_selection \
  tests.unit.test_planner_parameters -v
git diff --check
git add arm64_probe/planning tests/unit/test_planner_selection.py \
  tests/unit/test_planner_parameters.py
git commit -m "Add deterministic plan resolution"
```

Expected: selection and precedence tests PASS.

### Task 7: Complete CPU Resolution, Capability Gates, Case IDs, and Environment Phases

**Files:**
- Modify: `arm64_probe/planning/planner.py`
- Create: `tests/unit/test_planner_cases.py`
- Create: `tests/contract/test_plan_contract.py`

- [ ] **Step 1: Write failing case-generation tests**

Assert semantic GB10 selection `cluster=c0, core_group=x925` resolves CPU `5`.
Assert explicit `cpu=7` overrides it and records source `cli` in
`Case.selectors`. For migration, assert deterministic pairs for same-core,
same-cluster, and cross-cluster, and assert explicit source/destination
overrides win and are recorded in `Case.selectors`.

For pair resolution, same-core uses the same representative CPU twice;
same-cluster uses the first two selected CPUs in one cluster; cross-cluster
uses one representative CPU from each of the first two clusters while
preserving the selected core group. Missing required CPUs produce a blocked
case with a stable reason.

- [ ] **Step 2: Write failing capability and deterministic-plan tests**

Assert:

- GB10 cases requiring `cpu-binding` are `ready`;
- M4 cases are `unsupported` with the missing capability in `reason`;
- a deterministic M4 plan containing unsupported cases still returns success;
- `skip_unavailable` changes `Plan.skip_unavailable`, not case availability;
- conflicting selectors return exit code `5`;
- reversed input selection order yields byte-identical JSON;
- plan JSON contains no timestamp, random ID, or host inspection output.

- [ ] **Step 3: Write failing environment-phase tests**

Assert `page-policy=hugepage` creates a stable `EnvironmentPhase` and capability
requirement, while `default` creates a distinct no-mutation phase. Phase and
case order must be deterministic and no environment mutation function may be
imported by the planning package.

Use a synthetic profile fixture to assert conflicting environment requirements
split into separate phases. Assert `cpu-governor` requires `linux.cpufreq` and
hugepage requirements require `linux.hugepage`.

- [ ] **Step 4: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.unit.test_planner_cases \
  tests.contract.test_plan_contract -v
```

Expected: FAIL because full case generation and gates are not implemented.

- [ ] **Step 5: Implement case generation**

Use `ConfiguredPlatformAdapter` for all CPU resolution. Canonical case-ID
dimensions are:

```text
single: <core-group-or-cpu>.<cluster-or-any>.<working-set>.<page-policy>
pair:   src-<cpu>.dst-<cpu>.<working-set>.<page-policy>
```

Normalize dimensions to lowercase kebab-case before calling `build_case_id`.
Sort cases by `(scenario_id, platform_id, cpu, src_cpu, dst_cpu, id)`. Mark a
case `unsupported` for missing capabilities and `blocked` for a resolvable
platform policy conflict. Group cases with identical requirements into
immutable `EnvironmentPhase` records; do not perform environment operations.

- [ ] **Step 6: Run Batch 2 checks and commit**

Run:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/legacy_manifest.py verify
git diff --check
git add arm64_probe/planning tests/unit/test_planner_cases.py \
  tests/contract/test_plan_contract.py
git commit -m "Complete deterministic case planning"
```

Expected: all tests PASS; legacy manifest verifies; no frozen or transitional
path is changed.

## Batch 3: Public Schemas, CLI, and Phase 1 Closure

### Task 8: Publish Strict JSON Schema Documents

**Files:**
- Create: all eleven files listed under `schemas/`
- Create: `tests/contract/test_public_schemas.py`

- [ ] **Step 1: Write failing public-schema tests**

For every schema, assert:

- valid JSON object root;
- `$schema` is `https://json-schema.org/draft/2020-12/schema`;
- `$id` is `https://arm64-uarch-probe.dev/schemas/<filename>`;
- top-level `type` is `object`;
- top-level `additionalProperties` is `false`;
- `required` is sorted and references declared properties.

Also assert `model_json.to_data()` keys for Capability, Platform, Experiment,
Profile, Case, Plan, Error, Sample, and RunResult are covered by their public
schemas.

- [ ] **Step 2: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.contract.test_public_schemas -v
```

Expected: FAIL because the schema documents do not exist.

- [ ] **Step 3: Create the public schemas**

Use strict object schemas with `additionalProperties: false`. Reuse local
`$defs` inside each file rather than adding a runtime schema dependency.
Required top-level fields are:

```text
capability: id, description
platform: id, display_name, description, measurement_support, capabilities,
          clusters, core_groups, representative_cpus, defaults
experiment: id, display_name, scenarios
profile: id, display_name, selections, overrides, environment
case: id, scenario_id, platform_id, status, reason, cpu, src_cpu, dst_cpu,
      selectors, parameters
plan: platform_id, profile_id, selections, cases, environment_phases,
      skip_unavailable
manifest: run_id, git_commit, platform_id, toolchain, resolved_parameters
environment: before, requested, effective, after, restoration_status
sample: run_id, case_id, sample_index, status, metrics
run-result: run_id, plan, samples, summary, environment
error: code, category, message, context, hint
```

Nullable fields must explicitly allow `null`. IDs must use the same regexes as
`domain/ids.py`.

- [ ] **Step 4: Run tests and commit**

Run:

```sh
python3 -m unittest tests.contract.test_public_schemas -v
git diff --check
git add schemas tests/contract/test_public_schemas.py
git commit -m "Publish Phase 1 JSON schemas"
```

Expected: schema contract tests PASS.

### Task 9: Define Sample and RunResult Contracts

**Files:**
- Modify: `arm64_probe/domain/models.py`
- Modify: `arm64_probe/serialization/model_json.py`
- Create: `tests/unit/test_result_contracts.py`

- [ ] **Step 1: Write failing immutable result-contract tests**

Define expected construction:

```python
sample = Sample(
    run_id="20260614T120000Z-ddc9c33",
    case_id="cache-latency.l1-latency@gb10.x925.c0.32kib.default",
    sample_index=0,
    status="ok",
    metrics=(("latency_ns", 1.5),),
)
result = RunResult(
    run_id=sample.run_id,
    plan=plan,
    samples=(sample,),
    summary=(("case_count", 1),),
    environment=(("restoration_status", "not-run"),),
)
```

Assert both records are frozen, every sample references a case in the plan,
sample indices are nonnegative, and serialization matches the public schemas.

- [ ] **Step 2: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.unit.test_result_contracts -v
```

Expected: FAIL because `Sample` and `RunResult` are not implemented.

- [ ] **Step 3: Implement result records and factories**

Add frozen `Sample` and `RunResult` records. Add factory validation functions
that reject missing plan references, duplicate `(case_id, sample_index)` pairs,
negative indices, and unsupported status values. Phase 1 must not create
result directories or generate run IDs.

- [ ] **Step 4: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_result_contracts \
  tests.contract.test_public_schemas -v
git diff --check
git add arm64_probe/domain/models.py arm64_probe/serialization/model_json.py \
  tests/unit/test_result_contracts.py
git commit -m "Define structured result contracts"
```

Expected: result-contract and schema tests PASS.

### Task 10: Implement `list`, `show`, and `plan` CLI Rendering

**Files:**
- Create: `arm64_probe/cli/parser.py`
- Create: `arm64_probe/cli/render.py`
- Modify: `arm64_probe/cli/main.py`
- Create: `tests/contract/test_cli_discovery.py`
- Create: `tests/contract/test_cli_plan.py`
- Create: `tests/integration/test_phase1_cli_workflow.py`

- [ ] **Step 1: Write failing discovery CLI tests**

Assert:

```sh
python3 -m arm64_probe list targets
python3 -m arm64_probe list profiles
python3 -m arm64_probe list platforms
python3 -m arm64_probe show cache-latency.l2-latency
python3 -m arm64_probe show gb10 -o json
python3 -m arm64_probe help plan
python3 -m arm64_probe plan --help
```

return `0`, use deterministic order, and expose IDs, capability requirements,
defaults, and measurement-support status. Unknown IDs return `3` without a
traceback. An ambiguous ID returns `3` and lists qualified alternatives.

- [ ] **Step 2: Write failing plan CLI tests**

Cover single, combined, and experiment selections; semantic selectors; CPU
overrides; profiles; `--samples`; `--working-set`; `--page-policy`;
`--skip-unavailable`; table output; and JSON output. Assert `-o json` works and
that `-p`, `-s`, and other unapproved short aliases fail with exit code `2`.

- [ ] **Step 3: Write the no-side-effect integration test**

Run every Phase 1 command in a temporary working directory with an environment
containing only `PATH` and `PYTHONPATH=<repository-root>`. Assert no files are
created, no command attempts privilege escalation, and no output contains
`/sys/`, `/proc/`, `taskset`, or probe execution.

- [ ] **Step 4: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.contract.test_cli_discovery \
  tests.contract.test_cli_plan tests.integration.test_phase1_cli_workflow -v
```

Expected: FAIL because CLI dispatch and rendering are incomplete.

- [ ] **Step 5: Implement parser, dispatch, and renderers**

The parser exposes only:

```text
list [targets|profiles|platforms|capabilities] [-o table|json]
show <id> [-o table|json]
plan [--platform auto|gb10|m4] [--profile <id>] [--select <id> ...]
     [--cluster <id>] [--core-group <id>] [--cpu <int>]
     [--src-cpu <int>] [--dst-cpu <int>] [--samples <int>]
     [--working-set <size>] [--page-policy default|hugepage]
     [--skip-unavailable] [-o table|json]
```

Default platform is `auto`. It resolves to `m4` only when the host is Darwin
ARM64. On other hosts, `auto` returns exit code `4` until Phase 2 adds
capability-driven platform detection. Auto resolution may read
`platform.system()` and `platform.machine()` only; it must not probe hardware
state.

Render tables with fixed headers and stable rows. Render JSON exclusively with
`dump_json(to_data(...))`. Render structured JSON errors when `-o json` is
present; otherwise print concise errors to `stderr`.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.contract.test_cli_discovery \
  tests.contract.test_cli_plan tests.integration.test_phase1_cli_workflow -v
git diff --check
git add arm64_probe/cli tests/contract/test_cli_discovery.py \
  tests/contract/test_cli_plan.py tests/integration/test_phase1_cli_workflow.py
git commit -m "Implement read-only Phase 1 CLI"
```

Expected: discovery, planning, and no-side-effect tests PASS.

### Task 11: Integrate Makefile, Documentation, and Phase 1 Acceptance

**Files:**
- Modify: `Makefile`
- Modify: `tests/test_makefile_contract.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `arm64_probe/README.md`
- Modify: `configs/README.md`
- Modify: `configs/platforms/README.md`
- Modify: `configs/experiments/README.md`
- Modify: `configs/profiles/README.md`
- Modify: `tests/unit/README.md`
- Modify: `tests/contract/README.md`
- Modify: `tests/fixtures/README.md`
- Modify: `tests/integration/README.md`
- Create: `tests/contract/test_phase1_acceptance.py`

- [ ] **Step 1: Write failing Makefile and acceptance tests**

Extend Makefile tests to require:

```text
probe         run ./probe with PROBE_ARGS
probe-help    run ./probe --help
phase1-check  run all Python tests and legacy verification without building
```

Acceptance tests assert:

- all eleven public schemas and seven registry JSON files load;
- canonical eight-scenario order is unchanged;
- GB10 and M4 pass shared platform contracts;
- representative `smoke` and combined plans are byte-deterministic;
- CLI contract exit codes match `ExitCode`;
- frozen and transitional paths are absent from the Phase 1 branch diff.

- [ ] **Step 2: Run tests and verify expected failures**

Run:

```sh
python3 -m unittest tests.test_makefile_contract \
  tests.contract.test_phase1_acceptance -v
```

Expected: FAIL because Makefile targets and acceptance documentation are not
integrated.

- [ ] **Step 3: Add thin Makefile wrappers**

Add phony targets that contain no experiment matrix logic:

```make
probe:
	./probe $(PROBE_ARGS)

probe-help:
	./probe --help

phase1-check:
	python3 -m unittest discover -s tests -p 'test_*.py' -v
	python3 scripts/legacy_manifest.py verify
```

Document `make probe PROBE_ARGS='plan --platform gb10 --profile smoke -o json'`
as a convenience wrapper; canonical scripts and docs continue to show long CLI
options.

- [ ] **Step 4: Update contributor-facing documentation**

Update README and AGENTS with:

- the implemented Phase 1 package/config/test ownership;
- `./probe --help`, `list`, `show`, and `plan` examples, plus the equivalent
  module invocation for debugging;
- stable exit-code reference link;
- Mac-only Phase 1 verification commands;
- explicit statements that Phase 1 does not execute measurements and GB10 is
  first required at Phase 3 Gate 1.

Replace skeleton wording in ownership README files with concise implemented
ownership rules. Do not change frozen or transitional documentation.

- [ ] **Step 5: Run full Mac acceptance**

Run:

```sh
make phase1-check
make check
make build
./probe --help
./probe list targets
./probe show cache-latency.l2-latency -o json
./probe plan --platform gb10 --profile smoke -o json
./probe plan --platform m4 --profile smoke -o json
git diff --check
git diff --name-only main -- runner data analysis baseline
git status --short
```

Expected:

- all Python, shell, legacy, Makefile, CLI, and current-host build checks pass;
- GB10 plan is deterministic and ready where capabilities permit;
- M4 plan reports unsupported measurement cases without pretending support;
- no frozen/transitional path is listed;
- only intentional Phase 1 files are modified.

- [ ] **Step 6: Commit Phase 1 integration**

Run:

```sh
git add Makefile README.md AGENTS.md probe arm64_probe/README.md configs \
  tests docs/design/cli-contract.md
git commit -m "Complete Phase 1 core domain and CLI"
```

- [ ] **Step 7: Record the Phase 1 review checkpoint**

Run:

```sh
git log --oneline main..HEAD
git status --short --branch
```

Review the complete branch diff before merge. The review report must state:

```text
GB10 required: no
Environment mutation: none
Next hardware reminder: at Phase 3 start
First allowed measurement: Phase 3 Gate 1 after explicit ready notice
```

Do not start Phase 2 until the Phase 1 public interfaces, schemas, and Mac
acceptance evidence are reviewed.
