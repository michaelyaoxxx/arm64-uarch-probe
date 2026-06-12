# arm64-uarch-probe v1.0 Baseline Design

## 1. Purpose

`arm64-uarch-probe` v1.0 will turn the existing GB10 microarchitecture
experiments into an engineered, reproducible, and extensible research
baseline.

The v1.0 release is complete when a contributor can:

1. Clone the authoritative GitHub repository on a GB10 system.
2. Inspect the planned environment changes and experiment cases.
3. Build and run individual, combined, or complete experiment profiles.
4. Restore modified system settings after success or failure.
5. Transfer structured results through GitHub.
6. Analyze the results and regenerate the published figures and report.

GB10 is the only officially supported measurement platform for v1.0. The
architecture must allow later ARM64 platforms, including Apple M4 systems, to
reuse platform-independent components without rewriting the runner, result
protocol, or reports.

## 2. Scope

### 2.1 Included in v1.0

- Cache topology collection and modeling.
- Pointer-chase L1, L2, L3, SLC, and DRAM latency experiments.
- Warm and cold paths, 4K and hugepage policies, and SLC eviction.
- Same-core, same-cluster, and cross-cluster migration latency.
- Unified planning and execution of individual or combined test scenarios.
- Transactional environment preparation and restoration.
- Structured results, historical result import, analysis, figures, and
  documentation.
- A Chips and Cheese comparison that distinguishes agreement, differences,
  and experiments not yet covered.
- Design roadmaps for deeper X925 and A725 exploration.

### 2.2 Excluded from v1.0

- New benchmark families such as bandwidth, latency under load, CPU/GPU
  contention, and a complete core-to-core matrix.
- Official performance-analysis support for macOS or Apple M4.
- Reproducing every experiment in the Chips and Cheese article.

Excluded experiments belong in the v1.x roadmap and must not delay v1.0.

## 3. Repository and Collaboration Contract

`michaelyaoxxx/arm64-uarch-probe` is the single authoritative repository. The
existing Git history must be preserved. Mac and GB10 systems collaborate only
through GitHub branches, pull requests, commits, and tags.

- Mac is the primary development, offline-test, analysis, figure, and
  documentation environment.
- GB10 is the authoritative hardware-measurement environment.
- Every hardware run records the exact Git commit or tag.
- Neither machine maintains independent changes directly on `main`.
- Release-candidate runs use immutable tags such as `v1.0.0-rc1`.
- `v1.0.0` is created only after the final baseline and documentation merge.

Daily run output is ignored by Git. The repository commits only evidence needed
to review published conclusions:

- `results/baselines/v1.0/`: structured baseline data, manifests, selected raw
  logs, and anomaly evidence.
- `docs/assets/v1.0/`: generated publication figures.
- `docs/results/v1.0.md`: conclusions, limitations, and traceability.

Existing versioned runners and `data/` remain as historical evidence.

## 4. Extensibility Architecture

The core architecture is:

```text
experiment definition
  -> capability interface
  -> OS backend
  -> hardware platform description
  -> probe
  -> structured result
```

### 4.1 Platform-Independent Core

The core owns stable domain models and orchestration:

- `Platform`: selected hardware description and backend.
- `Capability`: a measurable or controllable platform feature.
- `Experiment`: a benchmark family.
- `Scenario`: an independently selectable test item.
- `Case`: one fully expanded measurement point with a stable ID.
- `Profile`: a named composition of scenarios and selectors.
- `Sample` and `RunResult`: platform-neutral result records.

Experiments declare required and optional capabilities rather than checking a
platform name. Platform-specific branches such as `if platform == "gb10"` are
not allowed in experiment code.

Example capability declaration:

```python
required = {"monotonic_timer", "cpu_binding"}
optional = {"explicit_hugepage", "cache_flush", "pmu"}
```

The planner must reject, explicitly skip, or document degradation when a
capability is unavailable. It must never silently simulate support.

### 4.2 OS Backends

OS backends implement mechanisms shared by multiple hardware platforms.

- `linux_arm64`: affinity, `/sys`, `/proc`, Linux hugepages, PMU access, and
  Linux environment controls.
- `darwin_arm64`: a future backend for macOS-supported affinity, topology, and
  memory-policy capabilities.

Adding another Linux ARM64 system should normally require a new platform
description rather than a new backend. Adding Apple M4 requires one reusable
Darwin backend and an Apple M4 platform description.

### 4.3 Hardware Platform Descriptions

A hardware platform description contains facts and policies rather than runner
logic:

- Core groups, clusters, cache domains, and default representative CPUs.
- Supported capabilities and known limitations.
- Recommended environment policies.
- Default scenario matrices and platform-specific validation constraints.

GB10 is the complete v1.0 platform description. Apple M4 may be represented in
fixtures for contract testing, but is not a supported v1.0 measurement target.

### 4.4 Probes

C probes perform one explicit measurement. They validate arguments and emit
both readable diagnostics and a stable machine-readable record. They do not
expand experiment matrices, calculate multi-run statistics, or manage system
environment settings.

The existing `chase_pmu`, `evict_slc`, and `chase_migrate` behavior will be
retained and normalized behind this contract.

## 5. Target Repository Organization

The implementation plan will refine exact package names, but ownership
boundaries should follow this shape:

```text
src/                         C single-measurement probes
arm64_probe/
  core/                      domain models, planner, results, schemas
  backends/
    linux_arm64/
    darwin_arm64/            future implementation
  platforms/
    gb10/
    apple_m4/                future description and fixtures
  experiments/               capability-driven experiment definitions
  reports/                   platform-independent analysis inputs
configs/
  platforms/
  experiments/
  profiles/
legacy/runner/               frozen historical runner scripts
tests/
  unit/
  contract/
  fixtures/
  integration/
results/
  runs/                      ignored temporary runs
  baselines/v1.0/            committed release evidence
analysis/                    analysis and figure generation
docs/
  design/
  methodology/
  references/
  results/
  roadmap/
  assets/
```

Files should be moved with `git mv` where practical to preserve history.
The existing `data/` directory remains unchanged as historical evidence.

## 6. Experiment Composition Model

Experiments are composed at three levels:

```text
Experiment -> Scenario -> Case
```

Examples:

```text
cache-latency
  l1-latency
  l2-latency
  l3-latency
  slc-latency
  dram-latency

migration-latency
  same-core
  same-cluster
  cross-cluster
```

Each scenario independently declares:

- Capability requirements.
- Environment policy.
- Core and cluster selection rules.
- Working-set parameter space.
- Warm, cold, page, and eviction policies.
- Required setup steps.
- Result fields and acceptance rules.

Users can select one scenario, combine multiple scenarios, select an
experiment, or run a named profile. Selected scenarios are merged into one
execution plan, and duplicate cases are removed.

Environment-policy conflicts split the plan into explicit transaction phases.
They must not be silently overridden.

Each case has a stable semantic ID, for example:

```text
gb10/cache-latency/l2/C0-X925/2048KB/hugepage/warm
```

Stable IDs support resume, failed-case reruns, result comparison, and baseline
traceability.

## 7. Unified Control Surface

The stable interface will be a Python standard-library control layer. Exact
flags and configuration syntax will be finalized after implementation-level
analysis, but the conceptual operations are:

```text
probe doctor       inspect dependencies, capabilities, and recovery journals
probe plan         expand cases and show required environment changes
probe run          execute a plan inside environment transactions
probe resume       continue incomplete cases
probe analyze      calculate statistics and compare baselines
probe report       generate figures and Markdown reports
probe restore      recover an interrupted environment transaction
```

Rules:

- `plan` is read-only and reviewable before execution.
- Formal runs reference a committed profile; CLI overrides are recorded.
- Unsupported capabilities are identified during planning.
- `run` writes structured results but does not generate figures.
- Analysis and reporting can run offline on Mac.
- Makefile targets wrap common development tasks but do not contain experiment
  orchestration logic.

The GB10 runtime depends only on compiled probes, Bash/system utilities, and
Python's standard library. Development, testing, analysis, and plotting use a
repository-managed Python environment with controlled third-party dependencies.

## 8. Transactional Environment Management

Environment setup is a first-class transaction:

```text
detect capabilities
  -> inspect current state
  -> save original state
  -> apply requested policy
  -> verify effective state
  -> run cases
  -> restore original state
  -> verify restoration
```

Policies may include:

- CPU governor, minimum and maximum frequencies, and online CPUs.
- Hugepage pool, transparent-hugepage policy, and page policy.
- CPU and NUMA affinity.
- PMU permissions and required kernel interfaces.
- System-load and GPU-activity preconditions.

The result must distinguish requested settings from observed effective state.
For example, setting frequency limits does not prove that a fixed frequency
was maintained during a run.

Environment transactions must:

- Acquire a process lock before mutation.
- Save a durable recovery journal before changing settings.
- Record `before`, `requested`, `effective`, and `after` states.
- Restore settings on normal completion, command failure, and common signals.
- Verify restoration and treat incomplete restoration as a serious error.
- Detect unfinished journals on the next invocation and offer explicit
  recovery.
- Reject formal baseline execution when required settings cannot be inspected,
  applied, or reliably restored.

The default mode only inspects and describes required changes. Privileged
changes require explicit authorization. Once mutation begins, restoration is
automatic.

## 9. Result Protocol and Reporting

Each run creates:

```text
results/runs/<run-id>/
  manifest.json
  environment.json
  cases.jsonl
  raw/
  errors.jsonl
```

`manifest.json` records the Git commit, platform, backend, profile, selectors,
expanded-plan summary, tool versions, and timestamps.

Each case record contains:

- Stable case ID, experiment, and scenario.
- Platform, backend, CPU, core group, cluster, and topology facts.
- Working set, page policy, warm/cold policy, and eviction method.
- Requested parameters and observed capabilities.
- Individual samples, median, dispersion, and anomaly flags.
- Probe version, exit status, and raw log references.

Analysis reads only the structured protocol. Historical text logs are imported
through tested compatibility adapters; new reports must not parse human log
format directly.

Published conclusions must distinguish:

- Platform facts.
- Direct measurements.
- Derived results.
- Hypotheses or architectural inference.
- External references.

## 10. Documentation Deliverables

- `README.md`: positioning, quick start, result overview, and navigation.
- `docs/design/`: architecture, environment transactions, schemas, and
  extension guide.
- `docs/methodology/`: pointer chasing, eviction, migration, statistics, and
  code-to-method reasoning.
- `docs/results/`: GB10 v1.0 baselines, figures, confidence, anomalies, and
  limitations.
- `docs/references/`: analysis of Chips and Cheese's
  [GB10 memory-subsystem article](https://chipsandcheese.com/p/inside-nvidia-gb10s-memory-subsystem),
  including agreements, differences, methodological differences, and missing
  experiments.
- `docs/roadmap/`: X925/A725 exploration plus bandwidth, load contention,
  CPU/GPU interference, and complete core-to-core studies.

Figure-generation code, structured baseline inputs, and generated publication
figures are committed so GitHub readers can review the report directly.

## 11. Verification Strategy

### 11.1 Continuous Mac Verification

The Apple M4 Pro Mac validates engineering behavior, not GB10 performance:

- Configuration expansion and stable case IDs.
- Statistics, anomaly handling, and resume behavior.
- Result schemas and historical-log import.
- Report generation.
- Backend contract tests using GB10 and M4 fixtures.
- Probe parameter validation, pointer-chain logic, and safe portable subsets.
- Makefile, configuration, and documentation examples.

The implementation must separate generic ARM64 code from Linux-specific
features. `__aarch64__` alone must not imply Linux support for `MAP_HUGETLB`,
`MAP_POPULATE`, `dc civac`, or Linux affinity APIs.

### 11.2 Linux ARM64 Verification

Native ARM64 Linux containers or CI validate:

- Linux probe builds.
- Linux backend behavior and failure paths.
- Runner, Makefile, `taskset`, sysfs/procfs fixtures, and signal recovery.

Container measurements are never treated as hardware-performance conclusions.

### 11.3 GB10 Verification Gates

**Gate 1: one-time clean-environment toolchain acceptance**

- Start from a clean checkout.
- Verify bootstrap, build, doctor, plan, scenario composition, environment
  transactions, recovery, smoke execution, and GitHub result handoff.
- Repeat only when bootstrap/build/environment machinery changes, the OS or
  kernel changes, a different GB10 is used, or evidence is incomplete.

**Gate 2: methodology and result validation**

- Reuse the accepted environment.
- Run representative C0/C1, A725/X925, warm/cold, 4K/hugepage, eviction, and
  migration cases.
- Validate structured results, resume, statistics, figures, and comparisons
  with historical data.

**Gate 3: v1.0 release candidate**

- Checkout a fixed RC tag.
- Run `doctor` and a minimal regression smoke.
- Execute the complete v1.0 profile.
- Freeze release evidence, figures, conclusions, and known limitations.

## 12. Delivery Phases

### Phase 0: Repository Contract and History Freeze

- Point collaboration at the renamed authoritative repository.
- Freeze legacy runners and historical data.
- Establish dependency, build, Git-ignore, and platform-responsibility
  contracts.

### Phase 1: Core Domain Model

- Define platform, capability, experiment, scenario, case, profile, stable IDs,
  and result schemas.
- Add fixtures, historical imports, and Mac unit/contract tests.

### Phase 2: Backends and Environment Transactions

- Implement core interfaces, Linux ARM64 backend, GB10 platform description,
  environment journaling, restoration, and recovery.
- Preserve contracts for a future Darwin ARM64 backend.

### Phase 3: Probes and Unified Runner

- Normalize the three C probes and machine-readable output.
- Implement independent and composed scenarios, profiles, planning, execution,
  and resume.
- Align Makefile and run GB10 Gate 1.

### Phase 4: Analysis, Figures, and Methodology

- Import historical evidence and generate the release-candidate baseline.
- Complete figures, methodology, reference comparison, and roadmap.
- Run GB10 Gate 2.

### Phase 5: Release Closure

- Complete README, extension guide, and known limitations.
- Run GB10 Gate 3 from an RC tag.
- Freeze v1.0 evidence and publish `v1.0.0`.

Each phase requires design review, code review, and independent acceptance
before proceeding.

## 13. v1.0 Acceptance Criteria

v1.0 is ready when:

- Mac and Linux automated verification passes.
- GB10 Gate 1 evidence is complete and later gates pass their regression smoke.
- The complete GB10 v1.0 profile finishes without unexplained failures.
- Environment restoration is verified and recorded.
- Individual and combined scenarios, profiles, resume, and failed-case reruns
  work through the stable control surface.
- A fresh GB10 checkout can follow README instructions through a smoke run.
- Published figures and conclusions trace to structured cases, raw evidence,
  and a Git commit.
- Chips and Cheese comparisons clearly distinguish agreement, difference,
  methodological mismatch, and uncovered work.
- The repository contains a reviewed roadmap for deeper X925/A725 and v1.x
  experimentation.
