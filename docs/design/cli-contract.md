# CLI Contract

## Entry Points

Use `./probe` immediately after checkout. `python3 -m arm64_probe` is the
equivalent module entry point for debugging and automation.

Phase 1 exposes side-effect-free discovery and planning commands:

```text
probe --help
probe help plan
probe list
probe show
probe plan
```

Only `-h`/`--help` and `-o`/`--output` are Phase 1 short options. Other
parameters use their complete long names.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | CLI usage error |
| `3` | Configuration or schema error |
| `4` | Platform identification or capability error |
| `5` | Planning error |
| `10+` | Reserved for Phase 3 runtime failures |

The implementation in `arm64_probe/errors.py` is the single source for these
values. Contract tests keep this table aligned with it.

## Side-Effect Boundary

Every Phase 1 command is read-only. It does not execute probes, request
privileges, create result directories, or modify CPU frequency, hugepages, page
policy, or other system state.
