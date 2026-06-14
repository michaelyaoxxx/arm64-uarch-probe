# Phase 2 Backends and Environment Transactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement live ARM64 host diagnostics, capability-driven Linux environment controllers, deterministic environment previews, durable host-wide transactions, and explicit recovery without requiring GB10 access.

**Architecture:** Static platform facts and semantic CPU resolution remain separate from live OS backends. Small Linux controllers implement one mutation capability each behind injectable host-I/O protocols, while a platform-independent coordinator owns locking, versioned journals, deterministic apply order, reverse restoration, and signal-safe recovery. `probe doctor` is read-only, `probe restore` only replays managed journals, and `probe plan` remains deterministic.

**Tech Stack:** Python 3.10+ standard library (`argparse`, `dataclasses`, `enum`, `fcntl`, `json`, `os`, `pathlib`, `signal`, `subprocess`, `unittest`), Linux sysfs/procfs, strict JSON schemas, Make, Git.

---

## Delivery Boundaries

- Execute all continuous development and acceptance checks on the Mac.
- Use temporary Linux sysfs/procfs fixture trees and fake controllers; do not
  access or mutate a real Mac or GB10 environment.
- Do not execute C probes or cases, add a public environment-apply command, or
  claim Apple M4 measurement support.
- Do not modify CPU online state, NUMA hugepage pools, PMU permissions, system
  load, frozen legacy runners, historical `data/`, or transitional paths.
- Public mutation requires both `--allow-mutation` and sufficient caller
  privileges. The CLI never invokes `sudo`.
- The production Linux state root is fixed at
  `/var/lib/arm64-uarch-probe`; only internal APIs accept a temporary test root.
- Phase 2 requires no GB10 access. At Phase 3 start, issue the advance GB10
  preparation reminder. Do not announce Gate 1 readiness until the unified
  runner, transaction/recovery flow, and minimal smoke workflow pass.

## File Map

### Static Planning and Public Contracts

- Rename `arm64_probe/platforms/base.py` to
  `arm64_probe/platforms/resolver.py`: static semantic CPU resolver protocol.
- Rename `arm64_probe/platforms/configured.py` to
  `arm64_probe/platforms/configured_resolver.py`: configured platform resolver.
- Modify `arm64_probe/domain/models.py`: add explicit environment requirements
  to cases and phases; add platform environment defaults.
- Create `arm64_probe/environment/models.py`: immutable live observations,
  controller requests/states, journals, failures, and doctor reports.
- Create `arm64_probe/environment/requests.py`: generic conversion from planned
  host requirements to controller requests.
- Modify `arm64_probe/planning/planner.py`: distinguish host mutations from
  case-local execution requirements.
- Modify `configs/capabilities.json`, platform/profile configuration, registry
  validation, serializers, renderers, and public schemas together.

### Host Backends and Controllers

- Create `arm64_probe/backends/base.py`: `HostBackend` and
  `MutationController` protocols.
- Create `arm64_probe/backends/io.py`: injectable filesystem, command, and host
  runtime boundaries.
- Create `arm64_probe/backends/select.py`: explicit OS/architecture backend
  selection.
- Create `arm64_probe/backends/linux_arm64/backend.py`: Linux backend assembly.
- Create `arm64_probe/backends/linux_arm64/inspector.py`: read-only online CPU,
  topology, cache, PMU, kernel-interface, and load observations.
- Create `arm64_probe/backends/linux_arm64/cpu_frequency.py`: Linux policy-domain
  frequency controller.
- Create `arm64_probe/backends/linux_arm64/hugepage.py`: global explicit
  hugepage-pool controller and NUMA observation.
- Create `arm64_probe/backends/linux_arm64/transparent_hugepage.py`: THP policy
  controller.
- Create `arm64_probe/backends/darwin_arm64/backend.py`: real read-only Darwin
  facts plus explicit unsupported mutation observations.

### Transactions, Diagnostics, and CLI

- Create `arm64_probe/environment/constants.py`: authoritative repository ID,
  state root, lifecycle states, and controller ordering.
- Create `arm64_probe/environment/journal.py`: strict managed-journal parsing,
  atomic writes, and recovery discovery.
- Create `arm64_probe/environment/locking.py`: host-wide advisory mutation lock.
- Create `arm64_probe/environment/signals.py`: scoped common-signal conversion.
- Create `arm64_probe/environment/coordinator.py`: transaction lifecycle and
  reverse restoration.
- Create `arm64_probe/environment/recovery.py`: managed journal recovery.
- Create `arm64_probe/diagnostics/doctor.py`: live read-only diagnostic report.
- Modify `arm64_probe/cli/parser.py`, `main.py`, and `render.py`: add `doctor`
  and `restore`.
- Modify `arm64_probe/errors.py`: add fixed Phase 2 runtime exit codes.

### Tests, Fixtures, and Documentation

- Create `tests/support/host_fixture.py`: temporary Linux host tree builder and
  fake controllers.
- Add focused unit tests for every new module.
- Add contract tests for schemas, plan previews, CLI, exit codes, and backend
  boundaries.
- Add integration tests for read-only diagnostics, transaction failure,
  signal restoration, and recovery.
- Modify `Makefile`, `docs/design/cli-contract.md`,
  `docs/design/repository-contract.md`, `arm64_probe/README.md`, and `AGENTS.md`
  only after behavior exists.

## Public Type Contract

Define deterministic planning requirements in `arm64_probe/domain/models.py`:

```python
@dataclass(frozen=True)
class EnvironmentRequirement:
    id: str
    capability_id: str
    scope: str
    values: tuple[tuple[str, JsonScalar], ...]
    mutation: bool
    requires_privilege: bool
```

Define live-host and transaction records in
`arm64_probe/environment/models.py`:

```python
@dataclass(frozen=True)
class CapabilityObservation:
    capability_id: str
    status: str
    values: tuple[tuple[str, JsonScalar], ...]
    evidence: tuple[str, ...]
    hint: str | None
    permits_formal_measurement: bool


@dataclass(frozen=True)
class ControllerRequest:
    controller_id: str
    values: tuple[tuple[str, JsonScalar], ...]


@dataclass(frozen=True)
class ControllerState:
    controller_id: str
    status: str
    values: tuple[tuple[str, JsonScalar], ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class JournalFailure:
    stage: str
    category: str
    message: str


@dataclass(frozen=True)
class EnvironmentJournal:
    schema_version: int
    transaction_id: str
    repository_id: str
    backend_id: str
    platform_id: str
    state: str
    created_at: str
    updated_at: str
    requested: tuple[ControllerRequest, ...]
    before: tuple[ControllerState, ...]
    applied: tuple[str, ...]
    active_controller: str | None
    effective: tuple[ControllerState, ...]
    after: tuple[ControllerState, ...]
    restoration_status: str
    failures: tuple[JournalFailure, ...]


@dataclass(frozen=True)
class DoctorReport:
    backend_id: str
    platform_id: str | None
    observations: tuple[CapabilityObservation, ...]
    journals: tuple[EnvironmentJournal, ...]
```

Extend the existing Phase 1 records as follows:

```python
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
    environment_defaults: tuple[tuple[str, JsonScalar], ...]


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
    execution_requirements: tuple[EnvironmentRequirement, ...]


@dataclass(frozen=True)
class EnvironmentPhase:
    id: str
    case_ids: tuple[str, ...]
    host_requirements: tuple[EnvironmentRequirement, ...]
```

Controller IDs and deterministic apply order are:

```text
linux.cpufreq
linux.hugepage
linux.transparent-hugepage
```

Journal lifecycle states are exactly:

```text
created applying prepared restoring restored restore-failed
```

## Batch 1: Separate Static Resolution and Freeze Public Contracts

### Task 1: Rename the Static Platform Adapter and Add Runtime Exit Codes

**Files:**
- Rename: `arm64_probe/platforms/base.py` to `arm64_probe/platforms/resolver.py`
- Rename: `arm64_probe/platforms/configured.py` to
  `arm64_probe/platforms/configured_resolver.py`
- Modify: `arm64_probe/platforms/__init__.py`
- Modify: `arm64_probe/planning/planner.py`
- Modify: `arm64_probe/errors.py`
- Modify: `docs/design/cli-contract.md`
- Modify: `tests/contract/test_platform_contract.py`
- Modify: `tests/contract/test_cli_foundation.py`

- [ ] **Step 1: Write failing resolver-name and exit-code contract tests**

Update imports in `tests/contract/test_platform_contract.py` to require:

```python
from arm64_probe.platforms.configured_resolver import ConfiguredPlatformResolver
from arm64_probe.platforms.resolver import PlatformResolver
```

Add assertions in `tests/contract/test_cli_foundation.py`:

```python
self.assertEqual(ExitCode.HOST_INSPECTION, 10)
self.assertEqual(ExitCode.MUTATION_AUTHORIZATION, 11)
self.assertEqual(ExitCode.ENVIRONMENT_APPLY, 12)
self.assertEqual(ExitCode.ENVIRONMENT_RESTORE, 13)
self.assertEqual(ExitCode.ENVIRONMENT_BUSY, 14)
```

Add a source-boundary assertion that `arm64_probe.platforms` contains neither
`HostBackend` nor `/sys/`.

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.contract.test_platform_contract \
  tests.contract.test_cli_foundation -v
```

Expected: FAIL because the renamed resolver modules and runtime exit codes do
not exist.

- [ ] **Step 3: Rename the modules and identifiers**

Use `git mv` for both files. Rename the protocol and implementation:

```python
class PlatformResolver(Protocol):
    def resolve_single(...): ...
    def resolve_pair(...): ...


class ConfiguredPlatformResolver:
    def resolve_single(...): ...
    def resolve_pair(...): ...
```

Update `Planner` to instantiate `ConfiguredPlatformResolver`. Do not change
selection behavior.

- [ ] **Step 4: Add the fixed Phase 2 exit codes and documentation**

Extend `ExitCode`:

```python
HOST_INSPECTION = 10
MUTATION_AUTHORIZATION = 11
ENVIRONMENT_APPLY = 12
ENVIRONMENT_RESTORE = 13
ENVIRONMENT_BUSY = 14
```

Add the same meanings to `docs/design/cli-contract.md`, retaining codes `0`
through `5` unchanged.

- [ ] **Step 5: Run tests and commit**

Run:

```sh
python3 -m unittest tests.contract.test_platform_contract \
  tests.contract.test_cli_foundation -v
make phase1-check
git diff --check
git add arm64_probe/platforms arm64_probe/planning/planner.py \
  arm64_probe/errors.py docs/design/cli-contract.md tests/contract
git commit -m "Separate platform resolution from host backends"
```

Expected: focused tests and the Phase 1 suite PASS; the commit contains no live
host inspection.

### Task 2: Add Immutable Environment Models, Serialization, and Schemas

**Files:**
- Create: `arm64_probe/environment/__init__.py`
- Create: `arm64_probe/environment/constants.py`
- Create: `arm64_probe/environment/models.py`
- Create: `arm64_probe/environment/requests.py`
- Modify: `arm64_probe/domain/models.py`
- Modify: `arm64_probe/domain/__init__.py`
- Modify: `arm64_probe/serialization/model_json.py`
- Create: `schemas/environment-requirement.schema.json`
- Modify: `schemas/environment.schema.json`
- Create: `schemas/capability-observation.schema.json`
- Create: `schemas/doctor-report.schema.json`
- Modify: `schemas/case.schema.json`
- Modify: `schemas/plan.schema.json`
- Modify: `tests/unit/test_domain_models.py`
- Create: `tests/unit/test_environment_models.py`
- Create: `tests/unit/test_environment_requests.py`
- Modify: `tests/unit/test_model_json.py`
- Modify: `tests/contract/test_public_schemas.py`

- [ ] **Step 1: Write failing immutable-model and serialization tests**

In `tests/unit/test_environment_models.py`, instantiate every record from the
Public Type Contract and assert:

```python
self.assertRaises(dataclasses.FrozenInstanceError, setattr, journal, "state", "restored")
self.assertEqual(to_data(request)["controller_id"], "linux.cpufreq")
self.assertEqual(to_data(observation)["status"], "available")
self.assertEqual(to_data(journal)["applied"], ["linux.cpufreq"])
```

Update `build_models()` so `Platform`, `Case`, and `EnvironmentPhase` use the
new fields. Assert all public records retain tuples rather than mutable
collections.

In `tests/unit/test_environment_requests.py`, require the generic bridge:

```python
requests = requests_from_requirements(phase.host_requirements)
self.assertEqual(
    requests,
    (ControllerRequest("linux.cpufreq", (("governor", "performance"),)),),
)
```

Reject case-scoped, non-mutation, duplicate-controller, or capability IDs not
listed in `CONTROLLER_ORDER`.

- [ ] **Step 2: Write failing public-schema key tests**

Extend `SCHEMA_REQUIRED` with exact required fields:

```python
"environment-requirement.schema.json": (
    "capability_id", "id", "mutation", "requires_privilege", "scope", "values"
),
"capability-observation.schema.json": (
    "capability_id", "evidence", "hint", "permits_formal_measurement",
    "status", "values"
),
"doctor-report.schema.json": (
    "backend_id", "journals", "observations", "platform_id"
),
"environment.schema.json": (
    "active_controller", "after", "applied", "backend_id", "before",
    "created_at", "effective", "failures", "platform_id", "repository_id",
    "requested", "restoration_status", "schema_version", "state",
    "transaction_id", "updated_at"
),
```

Update case and plan required-key tuples for `execution_requirements` and
`host_requirements`. Add representative `EnvironmentJournal`,
`CapabilityObservation`, `DoctorReport`, and `EnvironmentRequirement` objects
to `test_current_model_keys_match_public_schemas`.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_domain_models \
  tests.unit.test_environment_models tests.unit.test_environment_requests \
  tests.unit.test_model_json \
  tests.contract.test_public_schemas -v
```

Expected: FAIL because models, serialization, and schemas are missing.

- [ ] **Step 4: Implement the immutable records and serializers**

Implement `EnvironmentRequirement` in `arm64_probe/domain/models.py` and the
remaining exact Public Type Contract in `arm64_probe/environment/models.py`.
Validate live records in `__post_init__`:

```python
OBSERVATION_STATUSES = {
    "available", "unsupported", "permission-denied", "degraded", "unavailable"
}
JOURNAL_STATES = {
    "created", "applying", "prepared", "restoring", "restored", "restore-failed"
}

if self.status not in OBSERVATION_STATUSES:
    raise ValueError(f"unsupported observation status: {self.status}")
if self.schema_version != 1:
    raise ValueError(f"unsupported journal schema version: {self.schema_version}")
if self.state not in JOURNAL_STATES:
    raise ValueError(f"unsupported journal state: {self.state}")
```

Also validate requirement scope is `host` or `case`, mapping-like tuples have
unique sorted keys, observation/controller IDs are unique where collected, and
the journal's `applied` IDs are a subset of its requested/before controller
IDs.

`active_controller` is either `None` or one requested controller not already
listed in `applied`. It is durably set immediately before that controller's
first possible write, then cleared only after the controller is added to
`applied`. Recovery restores `active_controller` first, if present, followed
by completed controllers in reverse order.

Extend `to_data()` for every new type. Serialize mappings in sorted order and
tuples as arrays. Update Phase 1 models with the new fields without introducing
backend imports into `domain`.

Implement `requests_from_requirements()` as a pure conversion that accepts only
host-scoped mutation requirements, uses `capability_id` as the controller ID,
preserves normalized values, rejects duplicates, and sorts requests by the
fixed controller order without importing a backend.

Define the fixed non-backend constants used by that conversion and later
transaction modules:

```python
REPOSITORY_ID = "github.com/michaelyaoxxx/arm64-uarch-probe"
STATE_ROOT = Path("/var/lib/arm64-uarch-probe")
CONTROLLER_ORDER = (
    "linux.cpufreq", "linux.hugepage", "linux.transparent-hugepage"
)
```

- [ ] **Step 5: Implement strict schema documents**

Create or update the listed schemas with draft 2020-12 IDs, strict
`additionalProperties: false`, exact required keys, stable status/lifecycle
enums, and references between plan/case/environment types. Journals must not
contain path or command fields.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_domain_models \
  tests.unit.test_environment_models tests.unit.test_environment_requests \
  tests.unit.test_model_json \
  tests.contract.test_public_schemas -v
make phase1-check
git diff --check
git add arm64_probe/domain arm64_probe/environment arm64_probe/serialization \
  schemas tests/unit tests/contract/test_public_schemas.py
git commit -m "Define Phase 2 environment contracts"
```

Expected: model, serialization, schema, and Phase 1 tests PASS.

### Task 3: Make Plan Previews Distinguish Host and Case Requirements

**Files:**
- Modify: `configs/capabilities.json`
- Modify: `configs/platforms/gb10.json`
- Modify: `configs/platforms/m4.json`
- Modify: `configs/profiles/baseline.json`
- Modify: `configs/platforms/README.md`
- Modify: `configs/profiles/README.md`
- Modify: `schemas/platform.schema.json`
- Modify: `arm64_probe/registry/validation.py`
- Modify: `arm64_probe/planning/planner.py`
- Modify: `arm64_probe/cli/render.py`
- Modify: `tests/unit/test_registry_validation.py`
- Modify: `tests/unit/test_planner_parameters.py`
- Modify: `tests/contract/test_plan_contract.py`
- Modify: `tests/contract/test_cli_plan.py`
- Modify: `tests/contract/test_platform_contract.py`

- [ ] **Step 1: Write failing platform-policy and profile-validation tests**

Require platform files to contain `environment_defaults`. Add validation cases
for these exact keys and types:

```text
cpu-governor                  nonempty string
cpu-min-frequency-khz         positive integer
cpu-max-frequency-khz         positive integer
hugepages                     nonnegative integer
hugepage-size-kb              positive integer
transparent-hugepage          nonempty string
```

Reject the ambiguous unused `cpu-frequency-policy` key. Require GB10 to declare
`hugepage-size-kb: 2048`; M4 declares an empty object.

Reject `hugepage-size-kb` in a profile unless `hugepages` is also requested,
and reject a profile whose explicit minimum frequency exceeds its explicit
maximum frequency.

- [ ] **Step 2: Write failing deterministic-preview tests**

Replace the old page-policy phase assertion with:

```python
default = planner.plan(default_request)
hugepage = planner.plan(hugepage_request)
self.assertEqual(
    tuple(req.id for req in default.cases[0].execution_requirements),
    ("cpu-affinity", "page-policy"),
)
self.assertEqual(
    default.environment_phases[0].host_requirements,
    hugepage.environment_phases[0].host_requirements,
)
self.assertNotEqual(
    default.cases[0].execution_requirements,
    hugepage.cases[0].execution_requirements,
)
```

For `baseline`, assert its host requirement is `cpu-frequency`, uses capability
`linux.cpufreq`, requires mutation and privilege, and does not contain
`page-policy`.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_registry_validation \
  tests.unit.test_planner_parameters tests.contract.test_plan_contract \
  tests.contract.test_cli_plan tests.contract.test_platform_contract -v
```

Expected: FAIL because platform policies and split previews are not
implemented.

- [ ] **Step 4: Add configuration and validation**

Add capability `linux.transparent-hugepage`. Add
`environment_defaults` to `Platform`, validation, schema, and both platform
files. Update profile validation to the exact keys and types above. Keep the
baseline profile requesting only:

```json
"environment": {
  "cpu-governor": "performance"
}
```

- [ ] **Step 5: Implement explicit preview construction**

Add pure helpers in `planner.py`:

```python
def _case_requirements(case_cpu_text: str, page_policy: JsonScalar) -> tuple[EnvironmentRequirement, ...]:
    page_capability = "linux.hugepage" if page_policy == "hugepage" else "arm64"
    return (
        EnvironmentRequirement(
            "cpu-affinity", "cpu-binding", "case",
            (("selection", case_cpu_text),), False, False,
        ),
        EnvironmentRequirement(
            "page-policy", page_capability, "case",
            (("policy", page_policy),), False, False,
        ),
    )


def _host_requirements(environment, defaults) -> tuple[EnvironmentRequirement, ...]:
    requested = dict(environment)
    platform_defaults = dict(defaults)
    result = []
    frequency_values = tuple(
        (request_id, requested[profile_id])
        for profile_id, request_id in (
            ("cpu-governor", "governor"),
            ("cpu-min-frequency-khz", "min-khz"),
            ("cpu-max-frequency-khz", "max-khz"),
        )
        if profile_id in requested
    )
    if frequency_values:
        result.append(EnvironmentRequirement(
            "cpu-frequency", "linux.cpufreq", "host",
            frequency_values, True, True,
        ))
    if "hugepages" in requested:
        result.append(EnvironmentRequirement(
            "hugepage-pool", "linux.hugepage", "host",
            (
                ("count", requested["hugepages"]),
                ("size-kb", requested.get(
                    "hugepage-size-kb",
                    platform_defaults["hugepage-size-kb"],
                )),
            ),
            True, True,
        ))
    if "transparent-hugepage" in requested:
        result.append(EnvironmentRequirement(
            "transparent-hugepage", "linux.transparent-hugepage", "host",
            (("policy", requested["transparent-hugepage"]),), True, True,
        ))
    return tuple(sorted(result, key=lambda item: item.id))
```

Group environment phases by `host_requirements` only. Preserve deterministic
case and phase ordering. Enhance table rendering to list each host requirement
with capability, requested values, mutation flag, and privilege flag, plus
each case's execution requirements, without reading the host.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_registry_validation \
  tests.unit.test_planner_parameters tests.contract.test_plan_contract \
  tests.contract.test_cli_plan tests.contract.test_platform_contract -v
make phase1-check
git diff --check
git add configs schemas/platform.schema.json arm64_probe/domain \
  arm64_probe/registry arm64_probe/planning arm64_probe/cli/render.py tests
git commit -m "Separate host and case environment requirements"
```

Expected: previews remain byte-deterministic; page-policy changes do not split
host transaction phases.

## Batch 2: Host Backend and Read-Only Diagnostics

### Task 4: Add Injectable Host I/O and Backend Protocols

**Files:**
- Create: `arm64_probe/backends/__init__.py`
- Create: `arm64_probe/backends/base.py`
- Create: `arm64_probe/backends/io.py`
- Create: `arm64_probe/backends/select.py`
- Create: `tests/support/__init__.py`
- Create: `tests/support/host_fixture.py`
- Create: `tests/unit/test_backend_io.py`
- Create: `tests/unit/test_backend_selection.py`

- [ ] **Step 1: Write failing filesystem-boundary and backend-selection tests**

Create a temporary fixture root and assert:

```python
fixture.write("/sys/example/value", "powersave\n")
host = PathHostFilesystem(root)
host.write_text("/sys/example/value", "performance\n")
self.assertEqual(host.read_text("/sys/example/value"), "performance\n")
self.assertEqual(host.glob("/sys/example/*"), ("/sys/example/value",))
```

Assert virtual paths must be absolute and cannot escape the fixture root.
Assert `write_text()` refuses missing files and symlinks rather than creating
new host interfaces.
Assert backend selection accepts only:

```text
Linux + aarch64/arm64 -> linux-arm64
Darwin + arm64/aarch64 -> darwin-arm64
```

Other combinations raise `ProbeError(ExitCode.HOST_INSPECTION, ...)`.

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_backend_io \
  tests.unit.test_backend_selection -v
```

Expected: FAIL because backend protocols and I/O boundaries do not exist.

- [ ] **Step 3: Implement exact host-I/O protocols**

Define:

```python
class HostFilesystem(Protocol):
    def exists(self, path: str) -> bool: ...
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, value: str) -> None: ...
    def glob(self, pattern: str) -> tuple[str, ...]: ...
    def is_writable(self, path: str) -> bool: ...


class CommandExecutor(Protocol):
    def run(self, argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]: ...


class HostRuntime(Protocol):
    def load_average(self) -> tuple[float, float, float]: ...
```

`PathHostFilesystem` maps an absolute virtual host path beneath an injected
root, rejects `..`, refuses symlink and missing-file writes, and sorts glob
results. `is_writable()` supports permission preflight without changing the
host. `LocalCommandExecutor` always uses an argument tuple with `shell=False`.
`LocalHostRuntime` wraps `os.getloadavg`.

- [ ] **Step 4: Implement backend and controller protocols**

Define:

```python
class MutationController(Protocol):
    id: str
    capability_id: str
    def inspect(self) -> ControllerState: ...
    def validate_request(self, request: ControllerRequest) -> None: ...
    def apply(self, request: ControllerRequest) -> None: ...
    def verify(self, request: ControllerRequest) -> ControllerState: ...
    def restore(self, before: ControllerState) -> None: ...
    def verify_restored(self, before: ControllerState) -> ControllerState: ...


class HostBackend(Protocol):
    id: str
    def inspect(self) -> tuple[CapabilityObservation, ...]: ...
    def controllers(self) -> tuple[MutationController, ...]: ...
```

- [ ] **Step 5: Add the reusable test fixture builder**

Implement `HostFixture` with methods that create parent directories and write
virtual-host files beneath a `TemporaryDirectory`. It must expose a
`PathHostFilesystem` and make write assertions easy; it must never use real
`/sys`, `/proc`, or `/var/lib`.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_backend_io \
  tests.unit.test_backend_selection -v
make phase1-check
git diff --check
git add arm64_probe/backends arm64_probe/environment/constants.py tests/support \
  tests/unit/test_backend_io.py tests/unit/test_backend_selection.py
git commit -m "Add host backend and IO boundaries"
```

Expected: backend-boundary tests and Phase 1 tests PASS.

### Task 5: Implement Linux and Darwin Read-Only Backends

**Files:**
- Create: `arm64_probe/backends/linux_arm64/__init__.py`
- Create: `arm64_probe/backends/linux_arm64/backend.py`
- Create: `arm64_probe/backends/linux_arm64/inspector.py`
- Create: `arm64_probe/backends/darwin_arm64/__init__.py`
- Create: `arm64_probe/backends/darwin_arm64/backend.py`
- Modify: `arm64_probe/backends/select.py`
- Create: `tests/unit/test_linux_inspector.py`
- Create: `tests/contract/test_host_backend_contract.py`

- [ ] **Step 1: Write failing Linux inspection tests**

Build a fixture containing:

```text
/sys/devices/system/cpu/online                         0-3
/sys/devices/system/cpu/cpu0/topology/cluster_id      0
/sys/devices/system/cpu/cpu0/cache/index0/level       1
/sys/devices/system/cpu/cpu0/cache/index0/type        Data
/sys/devices/system/cpu/cpu0/cache/index0/size        64K
/proc/sys/kernel/perf_event_paranoid                   2
/sys/bus/event_source/devices/armv8_pmuv3/type         5
```

Require observations for `host.cpu-online`, `host.topology`, `host.cache`,
`host.pmu`, `host.kernel-interfaces`, and `host.load`. Test missing, unreadable,
and malformed files map to explicit `degraded` or `unavailable` observations
without tracebacks.

- [ ] **Step 2: Write failing shared-backend contract tests**

Assert every backend:

- returns observations sorted by capability ID;
- uses only the five approved observation statuses;
- returns unique controller IDs;
- contains no experiment or GB10-specific import;
- Darwin controllers are empty and its mutation capabilities report
  `unsupported`;
- expected Darwin unsupported observations do not imply an inspection failure.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_linux_inspector \
  tests.contract.test_host_backend_contract -v
```

Expected: FAIL because live backend implementations do not exist.

- [ ] **Step 4: Implement read-only Linux inspection**

Implement pure parsers for Linux CPU-list syntax and bracketed kernel-policy
syntax. The inspector reads only through `HostFilesystem` and `HostRuntime`.
Bound evidence strings to the exact inspected interface and normalized value;
do not include unbounded command output.

Return `permission-denied` for `PermissionError`, `unavailable` for a required
missing interface, and `degraded` when partial topology/cache data is usable.
Never write from the inspector.

- [ ] **Step 5: Implement Darwin minimal backend and backend selection**

Darwin reports basic OS/architecture/load observations and explicit
`unsupported` observations for:

```text
cpu-binding
linux.cpufreq
linux.hugepage
linux.transparent-hugepage
pmu.armv9
```

It exposes no mutation controllers. Wire `select_backend()` to construct the
Linux or Darwin backend using injected I/O/runtime dependencies.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_linux_inspector \
  tests.contract.test_host_backend_contract -v
make phase1-check
git diff --check
git add arm64_probe/backends tests/unit/test_linux_inspector.py \
  tests/contract/test_host_backend_contract.py
git commit -m "Implement read-only ARM64 host backends"
```

Expected: Linux fixture and Darwin boundary tests PASS without touching the
real host.

### Task 6: Add the Read-Only `probe doctor` Workflow

**Files:**
- Create: `arm64_probe/diagnostics/__init__.py`
- Create: `arm64_probe/diagnostics/doctor.py`
- Modify: `arm64_probe/cli/parser.py`
- Modify: `arm64_probe/cli/main.py`
- Modify: `arm64_probe/cli/render.py`
- Create: `tests/unit/test_doctor.py`
- Create: `tests/contract/test_cli_doctor.py`
- Create: `tests/integration/test_phase2_doctor_workflow.py`

- [ ] **Step 1: Write failing doctor service tests**

Using a fake backend and a fake journal reader, assert:

```python
report = Doctor(backend, journal_reader).inspect(platform_id="gb10")
self.assertEqual(report.backend_id, "linux-arm64")
self.assertEqual(report.platform_id, "gb10")
self.assertEqual(report.observations, tuple(sorted(observations, key=...)))
self.assertEqual(report.journals, unfinished_and_failed_only)
```

Expected unsupported observations remain a successful report. A backend
inspection exception becomes exit code `10`.

- [ ] **Step 2: Write failing CLI and no-side-effect tests**

Require:

```bash
probe doctor
probe doctor --platform m4
probe doctor -o json
probe help doctor
```

On Darwin, JSON output must identify `darwin-arm64`, report unsupported Linux
mutation capabilities, return `0`, and create no files in a temporary working
directory. `doctor` must not accept `--allow-mutation`.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_doctor \
  tests.contract.test_cli_doctor tests.integration.test_phase2_doctor_workflow -v
```

Expected: FAIL because doctor service and CLI do not exist.

- [ ] **Step 4: Implement doctor service and rendering**

Implement:

```python
class JournalReader(Protocol):
    def unfinished(self) -> tuple[EnvironmentJournal, ...]: ...


class Doctor:
    def inspect(self, platform_id: str | None) -> DoctorReport: ...
```

Until the journal store exists, production CLI injects a read-only
`EmptyJournalReader`; Task 9 replaces it. Render table sections for backend,
observations, and recovery journals. JSON uses `to_data(DoctorReport)`.

- [ ] **Step 5: Wire the CLI without changing `plan`**

Add `doctor` to parser help topics. Resolve the backend from the actual OS and
architecture. Treat `--platform` as an optional reviewed context label; do not
auto-identify a Linux host as GB10.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_doctor \
  tests.contract.test_cli_doctor tests.integration.test_phase2_doctor_workflow -v
make check
git diff --check
git add arm64_probe/diagnostics arm64_probe/cli tests/unit/test_doctor.py \
  tests/contract/test_cli_doctor.py tests/integration/test_phase2_doctor_workflow.py
git commit -m "Add read-only host doctor command"
```

Expected: doctor tests and repository checks PASS; no mutation code is public.

## Batch 3: Linux Mutation Controllers

### Task 7: Implement the Linux CPU-Frequency Policy Controller

**Files:**
- Create: `arm64_probe/backends/linux_arm64/cpu_frequency.py`
- Modify: `arm64_probe/backends/linux_arm64/backend.py`
- Create: `tests/unit/test_cpu_frequency_controller.py`
- Modify: `tests/contract/test_host_backend_contract.py`

- [ ] **Step 1: Write failing inspection and request-validation tests**

Build two policy domains with:

```text
/sys/devices/system/cpu/cpufreq/policy0/related_cpus
/sys/devices/system/cpu/cpufreq/policy0/scaling_governor
/sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors
/sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq
/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq
```

Assert inspection flattens deterministic keys such as
`policy0.governor`, `policy0.related-cpus`, `policy0.min-khz`, and
`policy0.max-khz`. Reject unknown governors, nonpositive frequencies,
`min-khz > max-khz`, missing policy files, and malformed related CPU sets
before any write. Unwritable required interfaces fail permission preflight
without attempting mutation.

- [ ] **Step 2: Write failing apply, verify, and restore-order tests**

Use a recording filesystem. Require:

- governor-only requests write each policy in sorted order;
- apply writes governor first, then bounds; restore writes bounds first, then
  the original governor;
- if target maximum is below current minimum, bounds write minimum then
  maximum; otherwise bounds write maximum then minimum, so no intermediate
  interval has minimum greater than maximum;
- `verify()` rereads state and fails if effective values differ;
- `restore(before)` restores every policy and `verify_restored()` compares the
  full normalized state;
- partial write failure is observable to the transaction coordinator.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_cpu_frequency_controller -v
```

Expected: FAIL because the controller does not exist.

- [ ] **Step 4: Implement the controller**

Implement:

```python
class CpuFrequencyController:
    id = "linux.cpufreq"
    capability_id = "linux.cpufreq"
```

Map controller request values:

```text
governor
min-khz
max-khz
```

Enumerate `policy*` directories through `HostFilesystem.glob()`. Read and write
only the approved files. Never issue shell commands. Convert host I/O and
verification failures to structured `ProbeError` values appropriate for the
coordinator.

- [ ] **Step 5: Register the controller and run tests**

Have `LinuxArm64Backend.controllers()` return the controller when its interface
is inspectable. Keep controller order deterministic. Map its inspected state to
a `linux.cpufreq` capability observation so `doctor` reports current live
support and permission status.

Run:

```sh
python3 -m unittest tests.unit.test_cpu_frequency_controller \
  tests.contract.test_host_backend_contract -v
git diff --check
git add arm64_probe/backends/linux_arm64 tests/unit/test_cpu_frequency_controller.py \
  tests/contract/test_host_backend_contract.py
git commit -m "Add Linux CPU frequency controller"
```

Expected: frequency controller and backend contract tests PASS.

### Task 8: Implement Explicit and Transparent Hugepage Controllers

**Files:**
- Create: `arm64_probe/backends/linux_arm64/hugepage.py`
- Create: `arm64_probe/backends/linux_arm64/transparent_hugepage.py`
- Modify: `arm64_probe/backends/linux_arm64/backend.py`
- Create: `tests/unit/test_hugepage_controller.py`
- Create: `tests/unit/test_transparent_hugepage_controller.py`
- Modify: `tests/contract/test_host_backend_contract.py`

- [ ] **Step 1: Write failing explicit-hugepage tests**

Build:

```text
/sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages
/sys/devices/system/node/node0/hugepages/hugepages-2048kB/nr_hugepages
```

Assert the controller:

- inspects global pool size and reports NUMA-node pool evidence;
- accepts only `size-kb` positive integer and `count` nonnegative integer;
- writes only the global `nr_hugepages`;
- verifies exact effective count and treats allocation shortfall as failure;
- restores and verifies the original global count;
- never writes a NUMA node path;
- rejects an unwritable global pool before mutation.

- [ ] **Step 2: Write failing transparent-hugepage tests**

Build:

```text
/sys/kernel/mm/transparent_hugepage/enabled
```

with value:

```text
always [madvise] never
```

Require exact parsing of the selected value and available choices. Accept only
an available `policy`; reject an unwritable policy interface before mutation;
verify and restore by rereading the bracketed selection.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_hugepage_controller \
  tests.unit.test_transparent_hugepage_controller -v
```

Expected: FAIL because the controllers do not exist.

- [ ] **Step 4: Implement both focused controllers**

Implement:

```python
class HugepageController:
    id = "linux.hugepage"
    capability_id = "linux.hugepage"


class TransparentHugepageController:
    id = "linux.transparent-hugepage"
    capability_id = "linux.transparent-hugepage"
```

Both use only `HostFilesystem`, reject malformed state before writing, and
reread for verification. Explicit hugepages derive the approved global path
from validated `size-kb`; THP derives no path from untrusted request values.

- [ ] **Step 5: Register controllers and run tests**

Register both controllers in deterministic order and map their inspected states
to `linux.hugepage` and `linux.transparent-hugepage` capability observations.

Run:

```sh
python3 -m unittest tests.unit.test_hugepage_controller \
  tests.unit.test_transparent_hugepage_controller \
  tests.contract.test_host_backend_contract -v
make phase1-check
git diff --check
git add arm64_probe/backends/linux_arm64 tests/unit/test_hugepage_controller.py \
  tests/unit/test_transparent_hugepage_controller.py \
  tests/contract/test_host_backend_contract.py
git commit -m "Add Linux hugepage controllers"
```

Expected: all three Linux controllers satisfy the shared backend contract.

## Batch 4: Durable Host-Wide Transactions and Recovery

### Task 9: Implement Strict Managed Journals and Recovery Discovery

**Files:**
- Create: `arm64_probe/environment/journal.py`
- Create: `tests/unit/test_environment_journal.py`
- Create: `tests/contract/test_journal_security.py`
- Modify: `arm64_probe/diagnostics/doctor.py`
- Modify: `tests/unit/test_doctor.py`

- [ ] **Step 1: Write failing journal round-trip and lifecycle tests**

Require:

```python
store = JournalStore(root, repository_id=REPOSITORY_ID, required_owner_uid=os.getuid())
path = store.create(journal)
self.assertEqual(store.read(path), journal)
self.assertEqual(store.unfinished(), (journal,))
```

Test valid transitions only:

```text
created -> applying -> prepared -> restoring -> restored
created/applying/prepared/restoring -> restoring
restoring -> restore-failed
restore-failed -> restoring
```

Reject unsupported schema versions, duplicate controller IDs, invalid
transitions, duplicate JSON keys, and unknown fields. Reject an
`active_controller` that is unknown or already listed in `applied`.

Generate transaction IDs internally with `uuid.uuid4().hex`. Generate UTC
timestamps with one shared injected clock and serialize them as bounded ISO
8601 strings; tests use a fixed clock.

- [ ] **Step 2: Write failing atomic-write and path-security tests**

Require:

- a journal is written through a same-directory temporary file, flushed,
  atomically replaced, and parent-directory flushed;
- failed replacement preserves the last valid journal;
- production-mode root/journal ownership and modes are checked before mutation;
- root/journals use mode `0755`; lock/journal files use mode `0644`;
- unsafe existing permissions are rejected, never relaxed;
- symlink roots, symlink journals, path traversal, nested paths, paths outside
  `journals/`, arbitrary path fields, and command fields are rejected;
- read-only discovery does not create a missing root.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_environment_journal \
  tests.contract.test_journal_security -v
```

Expected: FAIL because `JournalStore` does not exist.

- [ ] **Step 4: Implement strict journal parsing and state transitions**

Implement:

```python
class JournalStore:
    def create(self, journal: EnvironmentJournal) -> Path: ...
    def read(self, path: Path) -> EnvironmentJournal: ...
    def update(self, journal: EnvironmentJournal) -> Path: ...
    def unfinished(self) -> tuple[EnvironmentJournal, ...]: ...
    def validate_managed_path(self, path: Path) -> Path: ...
```

Use an exact-field parser rather than accepting arbitrary dictionaries. Journal
IDs are canonical lowercase IDs generated internally. `repository_id` must
equal the normalized authoritative repository identity; checkout path and Git
commit are not part of recovery identity. Production construction requires
owner UID `0`; tests inject the current test-process UID.

- [ ] **Step 5: Implement atomic persistence and doctor discovery**

Use `os.open`, `os.fsync`, and `os.replace`; write temporary files only inside
the journal directory. Validate each existing path component with `lstat` and
reject symlinks before reading or writing. `unfinished()` returns only
`created`, `applying`, `prepared`, `restoring`, and `restore-failed`, sorted by
transaction ID. Replace `EmptyJournalReader` in doctor with read-only
`JournalStore` discovery.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_environment_journal \
  tests.contract.test_journal_security tests.unit.test_doctor \
  tests.contract.test_cli_doctor -v
make check
git diff --check
git add arm64_probe/environment/journal.py arm64_probe/diagnostics \
  tests/unit/test_environment_journal.py tests/contract/test_journal_security.py \
  tests/unit/test_doctor.py
git commit -m "Add durable managed environment journals"
```

Expected: journal and doctor tests PASS; read-only doctor creates no state.

### Task 10: Implement the Host-Wide Mutation Lock

**Files:**
- Create: `arm64_probe/environment/locking.py`
- Create: `tests/unit/test_environment_locking.py`
- Create: `tests/integration/test_environment_locking_processes.py`

- [ ] **Step 1: Write failing lock ownership and contention tests**

With an internal temporary state root, assert:

```python
with MutationLock(root, required_owner_uid=os.getuid()) as lock:
    self.assertTrue(lock.held)
    self.assertIn("pid", lock.metadata)
```

A second process must fail immediately with exit category `environment-busy`.
After the first process exits normally or crashes, a new process can acquire
the OS lock even if stale metadata remains.

- [ ] **Step 2: Write failing permission and safety tests**

Require the lock:

- creates the state root only after an authorized mutation path calls it;
- validates root ownership/mode before opening the lock;
- opens one fixed `mutation.lock` path without following symlinks;
- uses mode `0644`;
- writes bounded diagnostic owner metadata only after acquiring the lock;
- releases on context exit without deleting the lock file.

An inability to create or open the authoritative state root because of caller
permissions maps to exit code `11`; unsafe ownership, modes, or symlinks map to
a recovery-safety failure and are never repaired automatically.

Production construction requires owner UID `0`; process tests inject the
current test-process UID and a temporary state root.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_environment_locking \
  tests.integration.test_environment_locking_processes -v
```

Expected: FAIL because `MutationLock` does not exist.

- [ ] **Step 4: Implement advisory locking**

Use:

```python
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
```

Keep the file descriptor open for the context lifetime. Convert contention to
`ProbeError(ExitCode.ENVIRONMENT_BUSY, "environment-busy", ...)`. Metadata
includes only PID, bounded hostname, backend ID, repository ID, and acquisition
timestamp. The held OS lock is authoritative; metadata is diagnostic.

- [ ] **Step 5: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_environment_locking \
  tests.integration.test_environment_locking_processes -v
git diff --check
git add arm64_probe/environment/locking.py tests/unit/test_environment_locking.py \
  tests/integration/test_environment_locking_processes.py
git commit -m "Add host-wide environment mutation lock"
```

Expected: process-contention and crash-release tests PASS.

### Task 11: Implement Transaction Coordination, Failure Restoration, and Signals

**Files:**
- Create: `arm64_probe/environment/signals.py`
- Create: `arm64_probe/environment/coordinator.py`
- Create: `tests/support/fake_controllers.py`
- Create: `tests/unit/test_environment_coordinator.py`
- Create: `tests/integration/test_environment_signal_restore.py`

- [ ] **Step 1: Write failing successful-lifecycle tests**

Use recording fake controllers and assert the exact event sequence:

```text
lock
rediscover-journals
inspect:a
inspect:b
validate:a
validate:b
journal:created
journal:applying
journal:active:a
apply:a
journal:applied:a,active:none
journal:active:b
apply:b
journal:applied:b,active:none
verify:a
verify:b
journal:prepared
work
journal:restoring
restore:b
restore:a
verify-restored:b
verify-restored:a
journal:restored
unlock
```

Assert controller apply order follows `CONTROLLER_ORDER`, restoration is
reverse order, and the final journal contains before/requested/effective/after
states.

- [ ] **Step 2: Write failing exhaustive fault-injection tests**

Parameterize failure at every inspect, journal persistence, apply, verify,
work, restore, and restore-verification point. Require:

- successfully applied controllers are restored in reverse order;
- a controller recorded as `active_controller` is restored first even when its
  apply call failed or the process stopped before it could be marked applied;
- apply/verify/work failure with successful restoration returns exit code `12`
  and records the original failure;
- restore or restore-verification failure returns exit code `13`, records
  `restore-failed`, and retains the original failure;
- an active lock or unfinished journal prevents a new transaction with code
  `14`;
- missing `allow_mutation` fails before lock creation with code `11`;
- permission preflight fails with code `11` before journal creation or host
  writes;
- unsupported, unavailable, or degraded required controller state fails host
  preflight with code `10` before journal creation or host writes;
- coordinator contains no Linux path, platform name, or experiment import.

- [ ] **Step 3: Write failing signal-integration test**

Run a child process with a fake controller and a blocking work callback. Send
`SIGTERM`. Require the child to enter restoration, restore the fixture state,
persist a finalized failed transaction, release the lock, and exit nonzero
without leaving an active mutation.

- [ ] **Step 4: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_environment_coordinator \
  tests.integration.test_environment_signal_restore -v
```

Expected: FAIL because coordinator and signal scope do not exist.

- [ ] **Step 5: Implement scoped signal conversion**

Implement a context manager that, only on the main thread, temporarily converts
`SIGINT` and `SIGTERM` into a private `TransactionInterrupted(signum)`
exception. Restore previous handlers on exit. The coordinator catches this
inside the transaction boundary, restores, records the interruption, then
returns a structured environment-apply failure.

- [ ] **Step 6: Implement the coordinator**

Implement:

```python
class EnvironmentCoordinator:
    def execute(
        self,
        backend: HostBackend,
        platform_id: str,
        requests: tuple[ControllerRequest, ...],
        work: Callable[[], None],
        allow_mutation: bool,
    ) -> EnvironmentJournal: ...
```

Acquire the lock before authoritative inspection and journal creation.
Rediscover unfinished journals while holding the lock. Persist the journal
before the first write, immediately before each controller apply by setting
`active_controller`, and after every successful controller apply by moving it
to `applied`. Validate requests and write permissions after authoritative
inspection but before journal creation or mutation. If `requests` is empty,
call `work` without creating state or requiring authorization.

- [ ] **Step 7: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_environment_coordinator \
  tests.integration.test_environment_signal_restore -v
make check
git diff --check
git add arm64_probe/environment tests/support/fake_controllers.py \
  tests/unit/test_environment_coordinator.py \
  tests/integration/test_environment_signal_restore.py
git commit -m "Add recoverable environment transaction coordinator"
```

Expected: lifecycle, fault-injection, signal, and repository checks PASS.

### Task 12: Implement Managed Journal Recovery and `probe restore`

**Files:**
- Create: `arm64_probe/environment/recovery.py`
- Modify: `arm64_probe/cli/parser.py`
- Modify: `arm64_probe/cli/main.py`
- Modify: `arm64_probe/cli/render.py`
- Create: `tests/unit/test_environment_recovery.py`
- Create: `tests/contract/test_cli_restore.py`
- Create: `tests/integration/test_phase2_restore_workflow.py`

- [ ] **Step 1: Write failing recovery-service tests**

Require this order:

```text
preflight-managed-path
acquire-lock
reread-journal
authoritative-validation
restore-active-controller-if-present
restore-applied-controllers-in-reverse
verify-restored
persist-restored
release-lock
```

Test cross-checkout recovery succeeds when repository identity matches even if
checkout paths and commits differ. Test backend mismatch, repository mismatch,
unsupported controller, symlink swap, journal change while waiting for lock,
and path outside the authoritative journal directory fail before host writes.
An already restored journal is a successful no-op.

- [ ] **Step 2: Write failing CLI authorization and output tests**

Require:

```bash
probe restore --journal <path> --allow-mutation
probe restore --journal <path> --allow-mutation -o json
probe help restore
```

Assert:

- missing `--allow-mutation` returns `11` before creating state;
- CLI never invokes `sudo` or prompts;
- invalid/outside journal paths return a structured recovery error;
- active lock returns `14`;
- restoration failure returns `13`;
- `restore` accepts no target settings and no public state-root override.

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```sh
python3 -m unittest tests.unit.test_environment_recovery \
  tests.contract.test_cli_restore tests.integration.test_phase2_restore_workflow -v
```

Expected: FAIL because recovery service and restore CLI do not exist.

- [ ] **Step 4: Implement recovery service**

Implement:

```python
class EnvironmentRecovery:
    def restore(
        self,
        journal_path: Path,
        backend: HostBackend,
        allow_mutation: bool,
    ) -> EnvironmentJournal: ...
```

Perform only lexical and symlink-safe managed-path preflight before the lock.
After acquiring the lock, reread and authoritatively validate the journal
before restoring. Reconstruct requests only from normalized controller IDs and
states; never execute journal-provided paths or commands. Restore a recorded
`active_controller` first, then completed controllers in reverse order, with
deduplication.

- [ ] **Step 5: Wire and render `probe restore`**

Add the exact parser contract. Production CLI injects fixed `STATE_ROOT` and
`REPOSITORY_ID`; there is no `--state-root`. Render the final journal summary
for table output and full journal for JSON output. Route errors through the
existing structured error envelope.

- [ ] **Step 6: Run tests and commit**

Run:

```sh
python3 -m unittest tests.unit.test_environment_recovery \
  tests.contract.test_cli_restore tests.integration.test_phase2_restore_workflow -v
make check
git diff --check
git add arm64_probe/environment/recovery.py arm64_probe/cli \
  tests/unit/test_environment_recovery.py tests/contract/test_cli_restore.py \
  tests/integration/test_phase2_restore_workflow.py
git commit -m "Add explicit environment recovery command"
```

Expected: recovery and CLI tests PASS; no arbitrary mutation interface exists.

## Batch 5: Acceptance, Documentation, and Phase Closure

### Task 13: Freeze Phase 2 Acceptance and Developer Workflow

**Files:**
- Create: `tests/contract/test_phase2_acceptance.py`
- Create: `tests/integration/test_phase2_fixture_workflow.py`
- Modify: `tests/integration/test_phase1_cli_workflow.py`
- Modify: `tests/test_makefile_contract.py`
- Modify: `Makefile`
- Modify: `docs/design/cli-contract.md`
- Modify: `docs/design/repository-contract.md`
- Modify: `arm64_probe/README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Write failing Phase 2 acceptance tests**

Require acceptance tests to prove:

- platform resolver source contains no live-host mechanisms;
- backend/controller/coordinator source contains no experiment or GB10-specific
  branches;
- platform JSON contains no `/sys`, `/proc`, shell command, or runner logic;
- Darwin backend is explicit read-only/minimal unsupported;
- plan remains deterministic and read-only;
- doctor remains read-only and succeeds with expected unsupported results;
- restore requires explicit authorization and only managed journals;
- transaction fixture workflow records before/requested/effective/after,
  reverse-restores, and recovers an unfinished journal;
- frozen/transitional paths remain unchanged.

- [ ] **Step 2: Write failing Makefile contract tests**

Require thin wrappers:

```make
phase2-check:
	python3 -m unittest discover -s tests -p 'test_*.py' -v
	python3 scripts/legacy_manifest.py verify

doctor:
	./probe doctor $(PROBE_ARGS)
```

Assert `Makefile` contains no environment matrix, sysfs paths, `sudo`, or
mutation logic. Require `make help` to document `phase2-check` and `doctor`.

- [ ] **Step 3: Run acceptance tests and verify they fail**

Run:

```sh
python3 -m unittest tests.contract.test_phase2_acceptance \
  tests.integration.test_phase2_fixture_workflow tests.test_makefile_contract -v
```

Expected: FAIL because acceptance contracts and Makefile targets are missing.

- [ ] **Step 4: Add thin Makefile targets and update documentation**

Implement the exact wrappers above. Update documentation with:

- `probe doctor`, enhanced `probe plan`, and managed `probe restore`;
- runtime exit codes `10` through `14`;
- explicit mutation authorization and no automatic `sudo`;
- production host state under `/var/lib/arm64-uarch-probe`;
- handled `SIGINT`/`SIGTERM` restore automatically, while unhandleable process
  termination leaves a durable journal for explicit recovery;
- Mac fixture responsibility, Linux ARM64 fixture/CI responsibility, and no
  Phase 2 GB10 requirement;
- Phase 3 advance GB10 preparation reminder and Gate 1 readiness condition.

Do not document `probe run` as implemented.

- [ ] **Step 5: Run complete verification**

Run:

```sh
make phase2-check
make check
make build
./probe --help
./probe doctor -o json
./probe plan --platform gb10 --profile baseline -o json
git diff --check
git status --short
```

Expected:

- all tests and legacy verification PASS;
- Darwin-supported probe subset builds;
- help, doctor, and plan succeed without mutation;
- no unexpected generated or frozen-path changes appear.

- [ ] **Step 6: Review the complete Phase 2 diff**

Run:

```sh
git diff --stat main...HEAD
git diff --name-status main...HEAD
git status --short
```

Confirm:

- no frozen or transitional files changed;
- no C probe or runner execution was added;
- no public environment-apply command or public state-root override exists;
- no platform-name branch appears in controllers, coordinator, or planner;
- documentation matches implemented behavior.

- [ ] **Step 7: Commit Phase 2 acceptance evidence**

Run:

```sh
git add Makefile AGENTS.md arm64_probe docs/design tests
git commit -m "Complete Phase 2 backend and environment contracts"
```

Expected: the branch is clean after the acceptance commit.

## Phase 2 Completion Gate

Before requesting merge:

1. Run `make phase2-check`, `make check`, and `make build` from a clean tree.
2. Confirm every public schema and exit code is covered by contract tests.
3. Confirm fault injection covers every transaction stage and restoration
   failure has highest severity.
4. Confirm `doctor` creates no state and `restore` cannot target arbitrary
   paths, commands, values, or state roots.
5. Confirm the production lock and journals are host-wide and cross-checkout
   recovery uses repository identity rather than checkout path.
6. Confirm Phase 2 contains no GB10 measurement evidence and makes no M4
   measurement claim.
7. Review and merge the Phase 2 implementation branch before starting Phase 3.

At Phase 3 start, explicitly remind the user to prepare GB10 access. Continue
Mac and fixture development until the unified runner, transaction/recovery
flow, and minimal smoke workflow are ready. Only then announce:

```text
GB10 Gate 1 is ready to run
```
