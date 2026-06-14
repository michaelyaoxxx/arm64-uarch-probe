# Phase 1 Core Domain and CLI Design

## Purpose

Phase 1 establishes the platform-independent vocabulary and read-only control
surface for v1.0. It must make experiments discoverable, composable, and
deterministically plannable without probing hardware, changing the host, or
running a measurement.

This specification refines the Phase 1 details in the v1.0 design. In
particular, canonical scenario IDs use dot-qualified names and the Phase 1
package boundaries below replace the earlier illustrative `core/` layout.

## Scope and Boundaries

Phase 1 includes:

- immutable domain models and stable identifiers;
- JSON configuration and public validation contracts;
- GB10 and Apple M4 platform fixtures;
- target and profile registries;
- `probe --help`, `list`, `show`, and read-only `plan`;
- stable planning errors, exit codes, and contract tests.

Phase 1 does not execute probes, modify the environment, aggregate real
results, generate figures, or change frozen and transitional paths. Apple M4
validates engineering contracts only; v1.0 does not claim M4 measurement
support.

## Architecture and Ownership

```text
arm64_probe/
  cli/                 argument parsing and rendering
  domain/              immutable models, IDs, and common validation
  planning/            selection, parameter resolution, gates, case generation
  registry/            target, profile, and platform definition loading
  platforms/           adapter protocol plus GB10 and M4 adapters
  serialization/       JSON encoding, decoding, and schema validation
configs/
  experiments/         experiment and scenario definitions
  profiles/            reproducible parameter baselines
  platforms/           topology, capabilities, and semantic CPU groups
schemas/               public JSON schemas
```

`domain` depends on no CLI, OS, platform, or C probe implementation.
`planning` is pure and side-effect free. Platform adapters resolve semantic
selectors and report capabilities; they contain no experiment orchestration.
Targets declare meaning, parameters, and capability requirements without CPU
IDs or commands. All CLI operations call the same registry and planner APIs.

Adding a platform should normally require a platform definition, a small
adapter only when necessary, and conformance fixtures. It must not require
changes to generic planning, existing targets, or result contracts.

## Domain Model and Stable IDs

The immutable models are:

- `Capability`: a named platform feature such as `linux.hugepage`.
- `Platform`: topology, semantic CPU groups, capabilities, and defaults.
- `Experiment`: a benchmark family.
- `Scenario`: an independently selectable test item.
- `Profile`: a committed, named parameter and selection baseline.
- `Case`: the smallest fully expanded future execution unit.
- `Plan`: ordered cases, environment preview, and gate decisions.
- `Sample` and `RunResult`: result contracts defined now and produced later.

Public IDs use lowercase kebab-case. Canonical scenarios are:

```text
cache-latency.l1-latency
cache-latency.l2-latency
cache-latency.l3-latency
cache-latency.slc-latency
cache-latency.dram-latency
migration-latency.same-core
migration-latency.same-cluster
migration-latency.cross-cluster
```

A case ID combines the scenario with normalized semantic dimensions, for
example:

```text
cache-latency.l2-latency@gb10.x925.c0.warm.default-page
```

IDs never depend on input order, display labels, implementation filenames, or
unresolved defaults. Resolved platform CPU IDs belong in the `Case` record, not
in target definitions. Every sample references both a run ID and case ID.

The initial registry contains the two experiments and eight scenarios listed
above, plus `smoke` and `baseline` profiles. Exact reproducibility comes from
the recorded Git commit and resolved plan; changes to committed profile content
remain reviewable even when the profile ID stays stable.

## Unified Read-Only CLI

Phase 1 exposes:

```text
probe --help
probe help plan
probe list [targets|profiles|platforms|capabilities]
probe show <id>
probe plan [options]
```

`targets` includes experiments and scenarios. `show` accepts any globally
unambiguous registry ID and reports ambiguity with qualified alternatives.

`probe plan` and the future `probe run` share the same selection interface:

```bash
probe plan --select cache-latency
probe plan --select cache-latency.l2-latency \
  --select migration-latency.cross-cluster
```

Repeated `--select` options form a deduplicated union. Selecting an experiment
expands all its scenarios. Semantic selectors such as `--cluster c0` and
`--core-group x925` are the normal interface. Advanced `--cpu`, `--src-cpu`,
and `--dst-cpu` options support diagnosis and exact reproduction; they override
semantic selection and the plan records the override.

Common long options are:

```text
--platform --profile --select --cluster --core-group --cpu
--samples --working-set --page-policy --skip-unavailable --output
```

`--output` accepts `table` or `json`; `--page-policy` initially accepts
`default` or `hugepage`. Each command documents only applicable options.

Only conventional, unambiguous short options are provided: `-h/--help` and
`-o/--output` in Phase 1, with `-v/--verbose` and `-q/--quiet` reserved for
Phase 3. Parameters such as `--platform`, `--profile`, `--select`, and
`--samples` intentionally have no short aliases. Documentation and scripts use
long options.

## Deterministic Planning

Planning follows this sequence:

```text
CLI input
  -> load and validate registries
  -> select platform
  -> expand selections
  -> merge parameters
  -> resolve semantic CPUs
  -> validate applicability and capabilities
  -> generate and sort cases
  -> render plan
```

Parameter precedence is:

```text
platform defaults < profile < explicit CLI overrides
```

Every resolved value records its value and source. Unknown fields, invalid
enumerations, selector conflicts, and parameters irrelevant to selected
targets fail instead of being ignored. Cases sort by normalized scenario,
platform, CPU, and parameter dimensions. The same inputs and committed
configuration must produce byte-equivalent JSON plans. Plans exclude timestamps,
random run IDs, and other volatile execution metadata.

`plan` previews required environment changes but never applies them. Phase 3
will implement the approved transaction lifecycle: inspect, save, apply,
execute, restore, and verify restoration. Profiles may declare CPU-frequency,
governor, hugepage, and page-policy requirements. Conflicting environment
requirements create explicit transaction phases rather than silent overrides.

## Capability Gates and Errors

Each planned case has `ready`, `unsupported`, or `blocked` status with a stable
reason. `plan` succeeds when it can deterministically report unavailable cases;
`--skip-unavailable` marks which unavailable cases a future execution would
skip. By default, the future `run` command refuses to measure when any selected
case is unavailable. This option never hides invalid input or configuration.

Stable public exit codes are:

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | CLI usage error |
| `3` | Configuration or schema error |
| `4` | Platform identification or capability error |
| `5` | Planning error |
| `10+` | Reserved for Phase 3 runtime failures |

The CLI implementation owns one exit-code definition. The implementation plan
will place the public table in `docs/design/cli-contract.md`; contract tests
freeze it against the code definition. Automation may consume the codes but
must not redefine them. Human-readable errors go to `stderr`. JSON output uses
a stable error schema and includes the category, context, affected target, and
an actionable hint.

## Result Contracts

Phase 1 defines, but does not populate, the future run layout:

```text
results/<run-id>/
  manifest.json
  plan.json
  samples.jsonl
  summary.json
  environment.json
  logs/
```

JSON and JSONL are authoritative. Figures, tables, and Markdown are derived
artifacts. Original samples are immutable; filtering or anomaly decisions
affect only recorded derived statistics. Run IDs and manifests capture time,
Git commit, platform, toolchain, fully resolved parameters, and environment
decisions.

Public schemas cover registry definitions, platform fixtures, cases, plans,
manifests, environment records, samples, run results, and errors. Unknown
fields are rejected unless a schema explicitly defines an extension field.

## Validation Strategy

Mac runs Phase 1 unit, schema, CLI, and contract tests. GB10 and M4 fixtures
must satisfy the same platform contract while reporting different
capabilities. Tests cover:

- valid, invalid, and serialization-round-trip behavior for every model;
- canonical IDs, deterministic case IDs, sorting, and deduplication;
- selection expansion, parameter precedence, overrides, and applicability;
- `list`, `show`, `plan`, table output, JSON output, help, and exit codes;
- capability failures and `--skip-unavailable`;
- no-side-effect guarantees for every Phase 1 CLI operation.

No GB10 access is required in Phase 1 or Phase 2. The first real GB10 use is
Phase 3 Gate 1, after the unified runner, environment transaction and recovery
flow, and minimal smoke workflow are ready. Gate 1 validates a clean checkout,
one-time toolchain acceptance, environment restoration, minimal L1 latency,
minimal cross-cluster migration, and structured result artifacts.

At Phase 3 start, the project must issue an advance notice to prepare GB10
access. Once the Gate 1 workflow and checklist are ready, it must issue an
explicit "GB10 Gate 1 is ready to run" notice before requesting hardware use.

## Compatibility and Acceptance

Existing C probes, legacy runners, historical `data/`, and transitional
cache-information tools remain unchanged. They are behavior references and
future compatibility inputs, not extension points for the new control layer.
Phase 3 will wrap probe behavior behind execution adapters and may retire a
legacy runner only after equivalent behavior passes GB10 verification.

Phase 1 is accepted when all models and schemas are implemented, the two
fixtures pass shared contracts, the read-only CLI satisfies its documented
behavior, plans are deterministic and side-effect free, all Mac checks pass,
and no frozen or transitional path changes.
