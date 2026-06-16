# Error Patterns and Prevention Mechanisms

> **Living document.** Every bug discovered at the GB10 measurement stage
> that could have been caught earlier must be recorded here with its root
> cause pattern and the mechanism that now prevents it.

## Pattern Index

| # | Pattern | First Seen | Prevention Layer |
|---|---------|------------|------------------|
| P1 | C↔Python CLI contract drift | 2026-06-16 | Layer A + B |
| P2 | Platform assumption in tests | 2026-06-16 | Layer C |
| P3 | Null dependency not guarded | 2026-06-16 | Layer D |
| P4 | Sysfs path hardcoding | 2026-06-16 | Layer E |
| P5 | Fixture-vs-reality output format drift | 2026-06-16 | Layer F + G |

---

## P1: C↔Python CLI Contract Drift

### Symptoms
```
Probe exited with code 1 — stderr: "size too small"
Probe exited with code 2 — stderr: "unrecognized option '--src_cpu'"
Probe exited with code 2 — stderr: "unrecognized option '--evict_mb'"
```

### Root Cause
The C probe CLIs are the **authoritative source of truth**.  The Python
adapters (`chase_pmu.py`, `chase_migrate.py`, `evict_slc.py`) were
written against an idealized CLI design, not against the actual C
`argv` parsing.  Three concrete mismatches:

| C Probe Expects | Adapter Generated | Type |
|-----------------|-------------------|------|
| `<size_kb> <warm> [force_rounds] [seed] [clflush] [hugepage]` | `--cpu 0 --size 32 --warm 0 --measure 50 --rounds 0 --seed 42` | positional vs named |
| `--src-cpu N --dst-cpu N --size-kb N` | `--src_cpu N --dst_cpu N --size N` | hyphen vs underscore + wrong name |
| `--evict_mb=N` | `--evict_mb N` | equals vs space |

Additionally, every adapter included its own binary name (`"chase_pmu"`)
in the returned `argv`, but the runner already prepends `probe_path`.

### Prevention (Layer A — structural)

`tests/integration/test_probe_cli_contract.py::ProbeAdapterArgvContractTests`
(4 tests) run **without** a C compiler and enforce:

- `chase_pmu` argv contains zero `--` prefixed tokens
- `chase_migrate` argv contains `--src-cpu` / `--dst-cpu` / `--size-kb` and zero `_` variants
- `evict_slc` argv contains `=` syntax (`--evict_mb=32`)
- No adapter includes its binary name in the returned argv

### Prevention (Layer B — integration)

`tests/integration/test_probe_cli_contract.py::ProbeCliContractTests`
(7 tests) run **after `make build`** and actually invoke each compiled
probe binary with the adapter-generated argv.  The test passes when
stderr does **not** contain `Usage:`, `unrecognized option`, or `size
too small`.  Probes that don't compile on the current host skip
gracefully.

### Developer Contract

**When changing a C probe's CLI:**
1. Update the adapter's `build_argv` to match.
2. Update the corresponding `test_build_argv_basic` in `tests/unit/test_probe_adapters.py`.
3. Add or update a `ProbeAdapterArgvContractTests` entry if the argument *style* changed.
4. Run `make build && make phase3-check`.  The CLI contract tests must pass.
5. If the C probe is Linux-only, test on a Linux host or fixture before merging.

**When changing a Python adapter's `build_argv`:**
1. Verify the C probe still accepts the new argv (run `make build && make phase3-check`).
2. The same tests protect against regressions.

---

## P2: Platform Assumption in Tests

### Symptoms
```
FAIL: test_darwin_probe_workflow_creates_no_state — '/sys/' unexpectedly found
FAIL: test_show_targets_lists_exact_supported_probe_mappings — GNU Make noise
FAIL: test_clean_cannot_be_redirected_by_command_line — 'Entering directory' in output
```

### Root Cause
Tests written on macOS assumed (a) `doctor` output never contains `/sys/`
paths, (b) `make` output is BSD-style without recursive-directory
messages.  On Linux these assumptions don't hold.

### Prevention (Layer C)

Three rules for all new tests:

1. **OS-specific tests must be guarded:**
   ```python
   @unittest.skipUnless(platform.system() == "Darwin", "requires Darwin ARM64 host")
   ```
   or
   ```python
   if platform.system() != "Linux":
       self.skipTest("requires Linux")
   ```

2. **Subprocess output assertions must strip platform-specific noise.**
   The `make()` helper in `tests/test_makefile_contract.py` now filters
   `make[1]: Entering/Leaving directory` lines from stdout via a regex.

3. **Tests that run `doctor` on a real host must accept that the output
   reflects the actual OS.**  Don't assert absence of `/sys/` on Linux.

### Checklist for new tests
- [ ] Does this test run on both macOS and Linux?
- [ ] If OS-specific, is the guard in place?
- [ ] Does the test parse subprocess output that may contain OS-specific noise?

---

## P3: Null Dependency Not Guarded

### Symptoms
```
AttributeError: 'NoneType' object has no attribute 'execute'
```

### Root Cause
In `arm64_probe/cli/main.py`, the Runner was constructed with
`coordinator=None` because the smoke profile has no host mutations.
However, `Runner._execute_phase` only bypassed the coordinator for
`phase_id == "default"`, not for named phases with empty
`host_requirements`.  An empty-but-named phase fell through to
`self.coordinator.execute()` → crash.

### Prevention (Layer D)

1. **Nullable dependencies must be checked at every call site, not just
   at a "default" guard.**  The fix adds `if not requests:` before the
   coordinator path — empty requests means no coordinator needed.

2. **Tests must cover `None` for every optional constructor parameter.**
   `test_runner_handles_phase_with_no_host_requirements` now verifies
   `coordinator=None` + real phase + empty host_requirements.

### Checklist
- [ ] For every method parameter typed `X | None`, is there a test with `None`?
- [ ] Are there "accidental" guards (like `phase_id == "default"`) that should
      be semantic guards (like `if not requests`)?

---

## P4: Sysfs Path Hardcoding

### Symptoms
```
host.kernel-interfaces → pmu: false
host.pmu → status: "degraded" (pmu-type unavailable)
```
while `/sys/bus/event_source/devices/armv8_pmuv3_0/type` actually exists.

### Root Cause
`ARMV8_PMU_TYPE` was hardcoded to `/sys/bus/event_source/devices/armv8_pmuv3/type`.
On GB10, PMU devices are numbered (`armv8_pmuv3_0`, `armv8_pmuv3_1`) and the
unnumbered path doesn't exist.

### Prevention (Layer E)

1. **Sysfs paths that vary across hardware must be discovered at runtime,
   not hardcoded.**  `_discover_pmu_type_path()` first tries the canonical
   path, then globs for numbered variants.

2. **New sysfs paths must include a discovery fallback** — canonical path
   first, glob second, graceful degradation third.

3. **Unit tests must cover both patterns:**
   `test_reports_expected_read_only_linux_observations` (canonical)
   `test_discovers_numbered_pmu_device_on_gb10_like_platforms` (numbered)

### Checklist for new sysfs paths
- [ ] Is the path identical on all target platforms?
- [ ] If not, is there a runtime discovery method?
- [ ] Is there a test with both the canonical and the variant path?

---

## P5: Fixture-vs-Reality Output Format Drift

### Symptoms

```
chase_migrate: "Could not find migration_penalty in output"
evict_slc:     "Could not find evict_slc performance line in output"
```

### Root Cause

Adapter `parse_output` implementations and their corresponding fixture files
were **invented** — written against an expected/idealized output format rather
than captured from actual C probe runs.  Two concrete mismatches:

**chase_migrate (v1.0):**

| Adapter/ Fixture Expected | C Probe Actually Prints |
|---|---|
| `migration_penalty` | `migrate_penalty` |
| `Before migration:` / `After migration:` | `[src] measure` / `[dst] measure` |
| `latency=` | `src_latency =` / `migrate_latency =` |

**evict_slc (v1.2):**

| Adapter/ Fixture Expected | C Probe Actually Prints |
|---|---|
| `>>> latency = X ns/access` (on stdout) | `[evict_slc] touch_ms=… evict_ms=… approx_bw=… GB/s sink=…` (on **stderr**) |
| No `--verbose` flag | Requires `--verbose` for performance output |

Additionally, the `evict_slc` adapter only parsed `stdout`, but the C probe
writes its performance measurements to **stderr**.  The `combined = stdout +
stderr` fix was needed.

### Why This Was Missed Until GB10

1. **Unit tests used inline strings, not fixture files.**  They validated the
   adapter against the same person's mental model of the output, not against
   the actual C probe.  `assertIn("migration_penalty", ...)` passed because
   the test string was invented with the same mistake.

2. **Fixture files (when they existed) were also invented, not captured.**
   The content of `cross_cluster.stdout` was handwritten to match the
   adapter's expectations, not copied from a real probe run.

3. **No test ever ran the compiled probe and fed its actual stdout through
   `parse_output`.**  The integration gap: CLI contract tests proved the
   probe *accepts* the argv, but nothing proved the adapter *understands*
   the probe's output.

### Prevention (Layer F — single source of truth for fixtures)

**All fixture files must be captured from real probe output**, not
handwritten.  When adding a new fixture:

1. Compile the probe: `make build`
2. Run the probe with representative arguments, capturing stdout + stderr
3. Copy the verbatim output to `tests/fixtures/probe_output/<probe>/<version>/<scenario>.stdout`
4. Write the `parse_output` regex against the captured fixture
5. Write the characterization test against the captured fixture

**Never** invent a fixture to match an adapter's expectations.  The C
probe's `printf` output is the authoritative source of truth.

### Prevention (Layer G — parse contract verification)

`tests/integration/test_probe_cli_contract.py::ProbeParseContractTests`
(3 tests) run after `make build` and actually invoke each compiled probe
binary, capture its stdout+stderr, and feed it through the adapter's
`parse_output`.  The test fails if `parse_output` returns `ProbeError`.

This catches **all** output format mismatches before they reach measurement
hardware — wrong metric names, wrong line format, wrong stream (stdout vs
stderr), missing required fields, and regex syntax errors.

### Developer Contract

**When changing a C probe's `printf` output format:**

1. Run the probe and capture fresh output.
2. Update the fixture file in `tests/fixtures/probe_output/<probe>/<version>/`.
3. Update the adapter's `parse_output` regex to match.
4. Update the corresponding characterization test assertions.
5. Run `make build && make phase3-check`.  **Both** the fixture tests AND
   the `ProbeParseContractTests` must pass.
6. If the C probe is Linux-only, test on a Linux host before merging.

**When writing a new adapter's `parse_output`:**

1. Do NOT invent the expected format.  Compile and run the C probe first.
2. Capture the real output → create the fixture → write the regex.
3. The fixture is the **spec** for what `parse_output` must handle.

### Checklist for adapter output changes
- [ ] Were the fixture files captured from a real probe run (not handwritten)?
- [ ] Does `parse_output` handle both stdout AND stderr (combined)?
- [ ] Does `parse_output` regex match the exact metric names (`migrate_penalty`, not `migration_penalty`)?
- [ ] Are the characterization tests asserting against fixture files?
- [ ] Does `ProbeParseContractTests` pass after `make build`?

---

## Quality Gates (mandatory before merge)

```
make build                          # compile probes
make phase3-check                   # full suite (362+ tests)
make legacy-check                   # frozen evidence integrity
git diff --check                    # whitespace
```

After `make build`, the CLI contract tests automatically verify every
compiled probe against its adapter.  A probe that compiles but rejects
its adapter's argv fails the suite.

### When to add new prevention tests

| Trigger | Action |
|---------|--------|
| C probe CLI change | Add/update a `ProbeAdapterArgvContractTests` entry |
| New adapter | Add `test_build_argv_basic` in `test_probe_adapters.py` |
| New sysfs/procfs path | Add both canonical + variant fixture tests |
| Optional parameter added | Add `None`-value test case |
| New OS-specific behavior | Add platform guard or noise filter |
