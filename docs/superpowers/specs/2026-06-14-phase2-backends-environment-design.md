# Phase 2 Backends and Environment Transactions Design

## Purpose

Phase 2 adds live, read-only host inspection and a recoverable environment
mutation foundation without executing measurements. It turns the declarative
capabilities and environment previews from Phase 1 into explicit OS-backend
contracts, independently testable controllers, durable journals, and recovery
operations.

Phase 2 must be fully accepted without GB10 access. Mac provides continuous
contract and fault-injection testing; Linux ARM64 fixtures and CI validate
Linux mechanisms. The first real GB10 use remains Phase 3 Gate 1.

## Scope and Boundaries

Phase 2 includes:

- a reusable host-backend protocol and Linux ARM64 backend;
- a contract-tested Darwin ARM64 read-only/minimal boundary;
- live host diagnostics through `probe doctor`;
- controlled CPU-frequency, global hugepage-pool, and transparent-hugepage
  transactions;
- durable journals, one-host mutation locking, restoration, and recovery;
- enhanced deterministic environment previews in `probe plan`;
- `probe restore` for recovery from an existing managed journal;
- Mac fake/fixture tests and Linux ARM64 fixture or CI validation.

Phase 2 does not execute probes or cases, expose a general-purpose environment
apply command, or claim Apple M4 measurement support. It does not modify CPU
online state, NUMA-node hugepage pools, PMU permissions, or system load.
CPU affinity and per-allocation page policy are Phase 3 case-execution
concerns, not global host mutations.

## Authorization and Safety Contract

The CLI never invokes `sudo`, prompts for a password, or silently elevates
privileges. Read-only operations require no mutation authorization. Any public
operation that can change the host requires both:

1. the explicit `--allow-mutation` option; and
2. sufficient privileges in the calling process.

For example:

```bash
sudo ./probe restore --journal /var/lib/arm64-uarch-probe/journals/<id>.json \
  --allow-mutation
```

Missing authorization or permissions fails before mutation. `restore` accepts
only a valid journal managed beneath the authoritative host-state journal
directory. Journals store normalized controller identities and values, never
arbitrary filesystem paths, shell commands, or executable content. Controllers
derive allowed OS paths from their own validated identities, so a journal
cannot become an arbitrary privileged write interface.

## Architecture and Ownership

```text
arm64_probe/
  platforms/
    resolver.py                 static platform facts and semantic CPU selection
  backends/
    base.py                     HostBackend and controller protocols
    linux_arm64/
      backend.py
      cpu_frequency.py
      hugepage.py
      transparent_hugepage.py
      inspector.py
    darwin_arm64/
      backend.py                read-only/minimal unsupported boundary
  environment/
    models.py                   observations, operations, and journal records
    coordinator.py              transaction lifecycle
    journal.py                  atomic persistence and recovery discovery
    locking.py                  single-host mutation lock
  diagnostics/
    doctor.py                   backend, capability, and journal diagnostics
```

The current `PlatformAdapter` is renamed to `PlatformResolver`. It continues
to resolve semantic CPU selections from reviewed platform facts and has no
live-host responsibility.

Dependencies flow in one direction:

```text
CLI
  -> diagnostics / environment coordinator / planner
  -> backend protocols
  -> OS-specific mechanisms
```

Platform definitions contain topology facts, expected capabilities,
recommended policies, and scenario defaults. They contain no OS paths,
commands, controller logic, or runner logic. Experiments and the planner name
capability and environment requirements without importing a backend.
The coordinator contains no Linux path, GB10 name, or experiment behavior.

All host access passes through injectable filesystem and command-execution
boundaries. Production Linux implementations use the real host; tests use
temporary fixtures and fakes.

## Declared Capabilities and Live Observations

Phase 1 platform capabilities describe what a selected hardware platform is
expected to support. Phase 2 live observations describe what the current host
actually exposes. Neither substitutes for the other.

`probe plan` remains deterministic and side-effect free. It uses reviewed
configuration to show declared requirements, expected host mutations, and
privilege needs. It never reads live `/sys` or `/proc` state.

`probe doctor` performs live read-only inspection. Phase 3 `run` will repeat
the required inspection immediately before starting a transaction rather than
trusting an earlier doctor report.

Every capability observation has:

- a stable capability ID;
- one status: `available`, `unsupported`, `permission-denied`, `degraded`, or
  `unavailable`;
- normalized observed values;
- concise raw evidence or evidence references;
- an actionable hint when not fully available;
- a Boolean indicating whether the observation permits a formal measurement.

The Linux backend supports these Phase 2 controller capabilities:

- `linux.cpufreq`: CPU-frequency policy inspection and control;
- `linux.hugepage`: global hugepage-pool inspection and control;
- `linux.transparent-hugepage`: transparent-hugepage policy inspection and
  control.

The host inspector reports CPU online state, CPU/cluster/cache topology, PMU
interfaces and permission state, required kernel interfaces, and system-load
preconditions without modifying them.

The Darwin ARM64 backend reports basic real host facts where the Python
standard library provides them. All v1.0 mutation controllers and measurement
capabilities explicitly report `unsupported`; no M4 performance claim follows
from this backend.

## Controller Contract

Each independently testable mutation controller implements:

```text
inspect() -> before state
validate_request(request)
apply(request) -> applied record
verify(request) -> effective state
restore(before)
verify_restored(before) -> after state
```

Controllers must reject unknown values, missing interfaces, and ambiguous
state before writing. They record normalized state plus enough bounded raw
evidence to diagnose failures. They never infer success solely from a
successful write; verification requires a new observation.

### CPU Frequency

CPU frequency is managed by Linux `policy*` domains, not by treating every CPU
as an independent control. State records each policy identity, related CPUs,
governor, minimum frequency, and maximum frequency. Apply and restore use an
order that never intentionally creates an invalid minimum/maximum interval.
Missing policy files, inconsistent related-CPU sets, or unreadable values are
reported explicitly.

### Hugepages

The hugepage controller changes only the global hugepage pool for the
configured hugepage size. NUMA-node pools are inspected and reported but are
not changed in Phase 2. The controller verifies the observed pool after apply
and after restore; allocation shortfalls are failures rather than silent
degradation.

### Transparent Hugepages

Transparent hugepage policy is a separate controller because its interface,
values, and restoration semantics differ from the explicit hugepage pool. It
records the selected policy and the kernel-reported available choices.

## Plan Environment Preview

Phase 2 separates global host mutation requirements from case-local execution
requirements:

- host mutations include CPU governor/frequency, hugepage-pool, and
  transparent-hugepage policy;
- case-local requirements include CPU affinity and allocation page policy.

Only conflicting host mutations split the plan into environment transaction
phases. A page-policy difference alone does not require changing global host
state and therefore does not split a transaction phase. Public plan schemas
and contract tests are updated together to make this distinction explicit.

Each preview reports the responsible capability, requested policy, whether
mutation is expected, and whether elevated privileges are normally required.
The preview does not claim that the requested state is currently available or
already effective.

## Transaction Lifecycle

One environment transaction owns one durable journal and follows this order:

```text
acquire mutation lock
  -> rediscover and reject unfinished journals
  -> inspect before
  -> create journal
  -> record requested operations
  -> apply controllers in deterministic order
  -> inspect and verify effective state
  -> mark prepared
  -> invoke caller-supplied work
  -> restore applied controllers in reverse order
  -> inspect and verify after state
  -> finalize journal
  -> release lock
```

Phase 2 exposes the lifecycle as an internal stable API and tests it with a
caller-supplied work callback. Phase 3 will supply case execution as that
callback.

The lock must be held before the authoritative `before` inspection and journal
creation so two concurrent processes cannot both capture stale original state
or create competing active journals. Journal creation and requested operations
remain durably persisted before the first host mutation.

Journal states are:

```text
created
applying
prepared
restoring
restored
restore-failed
```

The journal is atomically persisted before the first mutation. After each
controller applies successfully, its applied state is persisted immediately.
Restoration touches only controllers recorded as applied and processes them in
reverse order.

Apply failure, verification failure, work-callback failure, and handled common
signals all enter restoration. A successful restoration after an earlier
failure remains a failed transaction and reports the original failure. A
restoration verification failure changes the journal to `restore-failed`,
returns a serious recovery error, and is never hidden by an earlier error.

The coordinator rejects a new mutation when it discovers an active mutation
lock or unfinished journal. Read-only inspection never requires the mutation
lock. A restored journal remains as local audit evidence.

## Journal, Lock, and Recovery Storage

Runtime transaction state lives under:

```text
/var/lib/arm64-uarch-probe/
  mutation.lock
  journals/<transaction-id>.json
```

This Linux host-level directory is authoritative so separate clones and
worktrees on the same machine share one mutation lock and discover the same
unfinished journals. A repository-local lock would not protect global
frequency and hugepage state.

Read-only commands inspect the directory without creating it. It is created
only as part of an explicitly authorized mutation flow with sufficient
permissions. The public CLI provides no state-root override because separate
roots would bypass host-wide serialization and recovery discovery. Tests
inject a temporary state root through internal APIs.

On Linux, the state root and journals are readable for diagnostics but writable
only by the privileged owner. Journals contain no secrets or unbounded command
output. Implementations create the root and journal directory with mode `0755`
and journal and lock files with mode `0644`, reject unsafe existing ownership
or modes before mutation, and never relax permissions on an existing path.

Phase 3 will copy finalized environment evidence into the corresponding
structured run result. Host-state journals remain local audit and recovery
evidence and are never committed to Git.

Journals use versioned, schema-validated JSON. Atomic updates write a temporary
file in the journal directory, flush it, replace the target, and preserve the
last valid journal if an update fails. The journal records:

- schema version, transaction ID, backend ID, platform ID, and repository
  identity;
- lifecycle state and bounded timestamps;
- requested controller policies;
- `before`, applied, `effective`, and `after` controller states;
- restoration status and structured failures.

The mutation lock uses a Linux advisory file lock and records diagnostic owner
metadata. The held OS lock is authoritative; metadata alone never proves that
a live owner exists. If a process crashes, the OS releases its lock, but its
unfinished journal still prevents a new mutation until explicit recovery.

Repository identity is the normalized authoritative repository identity, not a
checkout path or commit, so another clone of the same repository can perform
recovery.

`probe restore` first rejects symlink escapes and paths outside the
authoritative host-state journal directory without writing. It then acquires
the mutation lock, rereads the journal, and performs the authoritative schema,
backend, repository-identity, and supported-controller validation before any
restoration. It restores only recorded applied controllers. An already restored
journal is a successful no-op. An unfinished or `restore-failed` journal
remains discoverable by `doctor`.

## CLI Contract

Phase 2 adds:

```text
probe doctor [--platform <id>] [-o table|json]
probe restore --journal <path> --allow-mutation [-o table|json]
```

It also enhances `probe plan` environment previews without making planning
host-dependent.

`doctor` is always read-only. It reports selected backend and platform,
observed capabilities and permissions, host-inspection results, and unfinished
or failed recovery journals. It may return a nonzero inspection status but
never requests privileges or mutates the host.

Expected `unsupported` observations, including the Darwin mutation boundary,
do not make `doctor` itself fail. Exit code `10` means the requested diagnostic
could not be completed reliably, not merely that a capability is unavailable.

`restore` accepts no desired target state. It can only restore the original
state recorded in a managed journal. It refuses to run without explicit
mutation authorization, sufficient permissions, a valid journal, and an
available mutation lock.

Phase 2 deliberately provides no public `environment apply` command. Phase 3
`probe run --allow-mutation` will be the normal entry point that creates a new
transaction.

## Error and Exit Semantics

Phase 1 exit codes remain unchanged. Phase 2 fixes these runtime codes:

| Code | Meaning |
| --- | --- |
| `10` | Backend or host inspection failure |
| `11` | Mutation authorization or permission failure |
| `12` | Environment apply or verification failure; restoration succeeded |
| `13` | Environment restoration or recovery failure |
| `14` | Active lock or unfinished journal prevents mutation |

Human-readable errors go to `stderr`. JSON output uses the existing stable
error envelope with structured context and an actionable hint. When multiple
failures occur, restoration failure has the highest severity, while the
original failure remains recorded in the journal.

## Validation Strategy

### Continuous Mac Verification

Mac tests all platform-independent behavior and does not produce GB10
measurement evidence:

- controller contracts through fake filesystem and command boundaries;
- journal schema, atomic updates, recovery discovery, and managed-path checks;
- lock acquisition, contention, release, and stale diagnostic metadata;
- every valid transaction-state transition and invalid-transition rejection;
- deterministic apply order and reverse restoration;
- fault injection at every inspect, apply, verify, work, restore, and journal
  persistence step;
- subprocess and signal-driven automatic restoration;
- Darwin ARM64 real read-only/minimal backend contract;
- `doctor`, `restore`, enhanced `plan`, JSON schemas, and exit codes;
- proof that read-only commands do not create runtime state or mutate the host.

### Linux ARM64 Fixture and CI Verification

Linux ARM64 verification uses temporary sysfs/procfs fixtures and, where an
isolated CI environment safely permits it, controlled integration checks. It
covers path and parsing variants, permission failures, frequency-policy
domains, global and NUMA hugepage observations, transparent-hugepage policy,
topology, PMU interfaces, and restoration behavior.

Container or CI observations are engineering evidence only, never hardware
performance conclusions.

## Compatibility and Acceptance

Existing C probes, legacy runners, historical data, and transitional
cache-information tools remain unchanged. Phase 2 may use those tools as
behavior references but does not move or extend them.

Phase 2 is accepted when:

- capability interfaces contain no experiment-specific or GB10-specific logic;
- Linux ARM64 inspection and approved controllers satisfy their contracts;
- GB10 configuration contains facts and policies without backend or runner
  logic;
- Darwin ARM64 satisfies its explicit read-only/minimal unsupported contract;
- transactions persist and expose before/requested/effective/after state,
  serialize mutation, restore after failures and signals, and recover
  unfinished journals;
- `doctor`, `restore`, and plan previews satisfy their public contracts;
- all Mac checks and Linux ARM64 fixture/CI checks pass without GB10 access.

After Phase 2 acceptance and merge, Phase 3 begins normalized probes and the
unified runner. At Phase 3 start, the project must remind the user to prepare
GB10 access. The project must not announce **"GB10 Gate 1 is ready to run"**
until the unified runner, transaction/recovery flow, and minimal smoke workflow
are ready and verified.
