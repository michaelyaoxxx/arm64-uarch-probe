# CLI Contract

## Entry Points

Use `./probe` immediately after checkout. The Makefile routes this
through `uv run` against the pinned CPython 3.13.13 interpreter (see
`AGENTS.md`); after `make sync` a developer can also run
`uv run python -m arm64_probe` directly for debugging and automation.

Phase 1 exposes side-effect-free discovery and planning commands:

```text
probe --help
probe help plan
probe list [targets|profiles|platforms|capabilities] [-o table|json]
probe show <id> [-o table|json]
probe plan [--platform <id>] [--profile <id>] [--select <id> ...]
```

Only `-h`/`--help` and `-o`/`--output` are Phase 1 short options. Other
parameters use their complete long names.

`plan` accepts repeatable `--select`, semantic `--cluster` and `--core-group`
selectors, advanced `--cpu`/`--src-cpu`/`--dst-cpu` overrides, parameter
overrides, and `--skip-unavailable`. Parent experiments expand to all child
scenarios; repeated selections form a deterministic deduplicated union.

The default `--platform auto` resolves only to the M4 contract fixture on
Darwin ARM64. Other hosts must pass an explicit registered platform. M4 plans
validate contracts and report unsupported cases; they are not measurements.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | CLI usage error |
| `3` | Configuration or schema error |
| `4` | Platform identification or capability error |
| `5` | Planning error |
| `10` | Backend or host inspection failure |
| `11` | Mutation authorization or permission failure |
| `12` | Environment apply or verification failure; restoration succeeded |
| `13` | Environment restoration or recovery failure |
| `14` | Active lock or unfinished journal prevents mutation |
| `15` | Probe execution failure (timeout, signal, nonzero exit, or invalid output) |
| `16` | Run-result read, validation, compatibility, or persistence failure |

The implementation in `arm64_probe/errors.py` is the single source for these
values. Contract tests keep this table aligned with it.

## Side-Effect Boundary

Every Phase 1 command is read-only. It does not execute probes, request
privileges, create result directories, or modify CPU frequency, hugepages, page
policy, or other system state.

Phase 2 adds the read-only `probe doctor` and the mutating `probe restore`.

```text
probe doctor [--platform <id>] [-o table|json]
probe restore --journal <path> --allow-mutation [-o table|json]
```

`probe doctor` reuses the existing read-only boundary; it never acquires the
host mutation lock, never creates a journal, and never touches the production
state root. `probe restore` is the only public mutating entry point: it accepts
a managed journal path and `--allow-mutation`, replays the recorded controllers
in reverse order under the host-wide `MutationLock`, and persists the recovered
journal. It never executes journal-provided commands, never accepts target
settings (`--state-root`, `--value`, `--command`), and never invokes `sudo`.
Restore is denied with exit code `11` when authorization is missing, with
exit code `13` when the journal path is unsafe or restore fails, and with exit
code `14` when the host-wide lock is already held.

`SIGINT` and `SIGTERM` are converted into a private exception inside any
in-flight transaction and automatically restore the host before exit.
Unhandleable process termination leaves a durable journal for explicit
recovery via `probe restore`.

Phase 3 adds the mutating `probe run` and the resumptive `probe resume`.

```text
probe run [--platform <id>] [--profile <id>] [--select <id> ...]
          [--cluster <id>] [--core-group <id>]
          [--cpu <int>] [--src-cpu <int>] [--dst-cpu <int>]
          [--samples <int>] [--working-set <size>]
          [--page-policy default|hugepage]
          [--case <stable-case-id>]
          [--output-dir <path>]
          [--allow-mutation]
          [-o table|json]
          [<target> ...]

probe resume --run <path-to-run-result-json>
             [--output-dir <path>]
             [--allow-mutation]
             [-o table|json]
```

`probe run` executes cases selected identically to `probe plan` and writes
a schema-valid `RunResult` (schema v2) under `results/runs/` (git-ignored).
It groups cases by environment phase, executes each phase through
`EnvironmentCoordinator`, and records provenance including
`case_definitions_signature`, `repository_commit`, and `dirty_tree`.
Exit code `0` when all cases succeed; `15` on probe execution failure;
`16` on result persistence failure; `11`–`14` per the existing transaction
exit-code ladder.

`probe resume` reads a prior `RunResult`, validates schema/platform/case-definition
compatibility (rejecting with `16` on mismatch), carries over `ok` samples,
re-executes `error` cases, drops `skipped` cases, and writes a new `RunResult`
with `prior_run_id` and `resume_kind`. Repeated resume on a fully successful
result is an idempotent no-op.

GB10 is first required at Phase 3 Gate 1 after the unified runner, environment
recovery, and minimal smoke workflow receive an explicit ready notice.

## probe analyze

`probe analyze --run <result.json> [--run <result.json> ...] [--baseline <path>] --output-dir <dir> [-o table|json]`

Loads one or more schema v2 `RunResult` files, computes per-case summary
statistics via `StatisticsEngine`, and persists an `AnalysisSummary` JSON
artifact atomically.

Exit codes: `0` success, `16` run-result persistence/compatibility failure.

## probe report

`probe report --analysis <analysis-summary.json> --output-dir <dir> [-o table|json]`

Loads an `AnalysisSummary` artifact, generates PNG figures via matplotlib
(`Agg` backend), and writes a deterministic Markdown report.

Exit codes: `0` success, `16` analysis artifact compatibility failure.
