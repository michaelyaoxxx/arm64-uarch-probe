# Phase 4 Analysis and Report Generation — Detailed Design

> **Handoff:** `docs/superpowers/handoffs/2026-06-17-phase4-handoff.md`
> **Status:** Approved design — ready for implementation plan
> **Target:** `probe analyze` + `probe report` + baseline promotion

## 1. Architecture Overview

Phase 4 adds a read-only analysis and report pipeline on top of the Phase 3
execution layer. It **never** acquires `MutationLock`, writes journals, or
invokes `sudo`. All analysis consumes structured `RunResult` or
`LegacyImporter`-adapted records; no code reads legacy text directly.

**Why no `sudo`?** Phase 3 (`probe run`) is the **measurement** phase — it
requires `sudo` for `cpufreq` governor control and hugepage configuration via
the `EnvironmentCoordinator`. Phase 4 is the **consumer** phase — it reads
pre-collected `RunResult` JSON files that already contain the measurement data.
Analysis, statistics, figures, and reports are pure computation with zero host
mutation. The boundary is intentional: collect once with privilege, analyze
anywhere without it.

**Phase 4 does not initiate new measurements.** `probe analyze` and `probe
report` are strictly read-only consumers. They accept `RunResult` and
`AnalysisSummary` JSON files that were already collected by `probe run` (Phase
3). Phase 4 never invokes `Runner`, `EnvironmentCoordinator`, or any C probe
binary. This is the fundamental contract between the collection phase and the
analysis phase — Phase 3 collects; Phase 4 consumes. Any new measurement
campaign (e.g., baseline refresh, bandwidth probe) requires a separate Phase 3
invocation before Phase 4 can analyze its output.

### 1.1 Data Flow

```
RunResult JSON ──→ ResultIngester ──→ StatisticsEngine ──→ AnalysisSummary JSON
                         │
Legacy text ──→ LegacyImporter ──→ ImportedRecord ────────┘
                         │
ComparisonEngine ←── (--baseline flag)   [Phase 5: full implementation]
                         │
FigureGenerator ──→ PNG figures + FigureManifest
                         │
ReportGenerator ──→ report.md + ReportManifest
                         │
BaselinePromoter ──→ results/baselines/v1.0/   (Python API, no CLI)
```

1. `probe analyze --run <result.json> ...` loads `RunResult` files, runs
   statistics engine, persists `AnalysisSummary` JSON. The `--baseline` flag
   is accepted but cross-run comparison is deferred to Phase 5.
2. `probe report --analysis <analysis.json>` loads `AnalysisSummary`, runs
   figure and report generation, writes figures + Markdown report.
3. Candidate baseline promotion is a reviewed action via Python API.

### 1.2 Module Layout

```
arm64_probe/analysis/                  ← new top-level package (read-only)
    __init__.py                        ← exports public API
    models.py                          ← 8 frozen dataclasses
    store.py                           ← AnalysisStore (atomic persistence)
    statistics.py                      ← StatisticsEngine (pure functions)
    comparison.py                      ← ComparisonEngine (Phase 4 stub; implementation → Phase 5)
    ingestion.py                       ← ResultIngester + LegacyImporter protocol
    figures.py                         ← FigureGenerator (matplotlib → PNG)
    report.py                          ← ReportGenerator (deterministic Markdown)
    baseline.py                        ← BaselinePromoter (Python API only)
    adapters/
        __init__.py
        legacy_chase_pmu.py            ← example legacy import adapter

schemas/
    analysis-summary.schema.json       ← public schema v1
    baseline-manifest.schema.json       ← public schema v1

docs/
    methodology/
        cache-latency.md
        migration-latency.md
        chips-and-cheese-comparison.md
    roadmap/
        x925-a725-deep-dive.md
```

### 1.3 Dependencies

- **Python stdlib:** `statistics`, `json`, `csv`, `hashlib`, `re`, `pathlib`.
- **matplotlib** (new): `'Agg'` backend for headless PNG generation.
  Requires `pyproject.toml` dependency, `uv.lock` update, and contract tests
  that validate figure metadata (not pixel-perfect equality).
- No other new dependencies.

### 1.4 Baseline Collection Matrix

Phase 4's analysis pipeline consumes data collected by Phase 3's `probe run`.
A complete GB10 baseline (`--profile baseline`) covers the matrix below,
aligning with the measurement scope established by legacy runs in
`data/20260611_v2.7.*/`. The profile is a Phase 4 deliverable defined in
`configs/profiles/baseline.json`.

GB10 topology (see `docs/arch/cpu_topology.md`):

| Cluster | CPUs | Core Type | L1D | L2 | Shared L3 |
|---------|------|-----------|-----|-----|-----------|
| C0 | 0-4 | A725 | 64KB | 512KB | 8MB |
| C0 | 5-9 | X925 | 64KB | 2MB | 8MB |
| C1 | 10-14 | A725 | 64KB | 512KB | 16MB |
| C1 | 15-19 | X925 | 64KB | 2MB | 16MB |

SLC: 16MB shared. DRAM: 128GB.

**4 representative CPUs:** cpu0 (C0/A725), cpu5 (C0/X925), cpu10 (C1/A725), cpu15 (C1/X925).

#### Cache Latency (chase_pmu probe)

| Level | CPUs | working-set | page-policy | Rationale |
|-------|------|------------|-------------|-----------|
| L1 | 0, 5, 10, 15 | 32KiB | default (4K) | Fits in 64KB L1; 4K matches legacy L1 scans |
| L2 | 0, 10 (A725) | 256KiB | hugepage | Fits in 512KB A725 L2 |
| L2 | 5, 15 (X925) | 1MiB | hugepage | Fits in 2MB X925 L2 |
| L3 | 0, 5 (C0) | 4MiB | hugepage | Fits in 8MB C0 L3 |
| L3 | 10, 15 (C1) | 8MiB | hugepage | Fits in 16MB C1 L3 |

#### SLC and DRAM

| Level | CPUs | Method | page-policy |
|-------|------|--------|-------------|
| SLC | 0, 5, 10, 15 | evict_slc eviction → chase_pmu cold (warm=0) | hugepage |
| DRAM | 0, 5, 10, 15 | chase_pmu cold (warm=0) 64MiB | hugepage |

#### Migration Latency (chase_migrate probe, all hugepage)

9 migration pairs × 6 sizes (512K, 2M, 8M, 16M, 32M, 64M),
matching the legacy v2.7.11 measurement scope:

| # | Label | src | dst | Meaning |
|---|-------|-----|-----|---------|
| 1 | C0-A725 local | 0 | 0 | same-core baseline |
| 2 | C0-X925 local | 5 | 5 | same-core baseline |
| 3 | C1-A725 local | 10 | 10 | same-core baseline |
| 4 | C1-X925 local | 15 | 15 | same-core baseline |
| 5 | A725 C0→C1 | 0 | 10 | cross-cluster, same core type |
| 6 | A725 C1→C0 | 10 | 0 | reverse direction |
| 7 | X925 C0→C1 | 5 | 15 | cross-cluster, same core type |
| 8 | X925 C1→C0 | 15 | 5 | reverse direction |
| 9 | A725→X925 C0 | 0 | 5 | cross-core-type, same cluster |
| 10 | X925→A725 C0 | 5 | 0 | reverse (asymmetric per legacy) |
| 11 | A725→X925 C1 | 10 | 15 | cross-core-type, same cluster |
| 12 | X925→A725 C1 | 15 | 10 | reverse (asymmetric per legacy) |

#### Summary

- **Cache latency:** 4 (L1) + 4 (L2) + 4 (L3) + 4 (SLC) + 4 (DRAM) = **20 unique cases** × 5 samples = 100 samples
- **Migration latency:** 12 pairs × 6 sizes = **72 unique cases** × 1 measure_round = 72 samples
- **Total: ~92 unique cases, ~172 samples**

## 2. Domain Models

All models are `@dataclass(frozen=True)`. Public collections use `tuple[...]`
sorted for determinism. All IDs follow existing kebab-case conventions.

### 2.1 MetricStats

```python
@dataclass(frozen=True)
class MetricStats:
    metric_name: str
    unit: str               # "ns" | "cycles" | "bytes" | "ratio" | "count"
    sample_count: int
    success_count: int
    error_count: int
    min_value: float | None  # None when no successful samples
    max_value: float | None
    median: float | None     # statistics.median
    mad: float | None        # Median Absolute Deviation
    mean: float | None       # statistics.mean
    stddev: float | None     # statistics.stdev (sample)
```

### 2.2 CaseAnalysis

```python
@dataclass(frozen=True)
class CaseAnalysis:
    case_id: str
    scenario_id: str
    platform_id: str
    status: str              # "ok" | "partial" | "failed"
    total_samples: int
    ok_samples: int
    error_samples: int
    metric_stats: tuple[tuple[str, MetricStats], ...]   # sorted by name
    anomalies: tuple[str, ...]                           # sorted, deduplicated
    source_run_ids: tuple[str, ...]
```

### 2.3 CrossRunMetricDelta

```python
@dataclass(frozen=True)
class CrossRunMetricDelta:
    metric_name: str
    unit: str
    baseline_value: float | None
    current_value: float | None
    delta_pct: float | None   # None if either value is None
```

### 2.4 CrossRunComparison

```python
@dataclass(frozen=True)
class CrossRunComparison:
    case_id: str
    runs_compared: tuple[str, ...]
    classification: str      # "unchanged"|"improved"|"regressed"|"missing"|"incompatible"
    metric_deltas: tuple[tuple[str, CrossRunMetricDelta], ...]
    note: str | None
```

### 2.5 AnalysisSummary

```python
@dataclass(frozen=True)
class AnalysisSummary:
    analysis_id: str         # "YYYYMMDDTHHMMSSZ-8hex"
    schema_version: int      # 1
    source_runs: tuple[str, ...]
    platform_id: str
    repository_id: str
    repository_commit: str
    dirty_tree: bool
    toolchain: tuple[tuple[str, str], ...]
    case_analyses: tuple[CaseAnalysis, ...]          # sorted by case_id
    cross_run_comparisons: tuple[CrossRunComparison, ...]  # empty if single run
    anomalies: tuple[str, ...]
    generated_at: str        # ISO 8601
```

### 2.6 FigureManifest

```python
@dataclass(frozen=True)
class FigureManifest:
    figure_id: str           # stable filename stem
    path: str                # relative to output dir
    caption: str
    source_analysis_id: str
    regeneration_command: str
```

### 2.7 ReportManifest

```python
@dataclass(frozen=True)
class ReportManifest:
    report_id: str
    report_path: str
    source_analysis_id: str
    figure_manifests: tuple[FigureManifest, ...]
    claim_count: int
    section_count: int
    generated_at: str
    regeneration_command: str
```

### 2.8 ImportedRecord

```python
@dataclass(frozen=True)
class ImportedRecord:
    source_path: str
    parser_version: str
    format: str
    case_id: str | None
    platform_id: str | None
    metrics: tuple[tuple[str, JsonScalar], ...]
    loss_notes: tuple[str, ...]
```

### 2.9 BaselineManifest

```python
@dataclass(frozen=True)
class BaselineManifest:
    baseline_id: str
    version: str             # "v1.0"
    source_run_ids: tuple[str, ...]
    analysis_id: str
    report_id: str | None
    figure_ids: tuple[str, ...]
    commands: tuple[str, ...]
    repository_commit: str
    dirty_tree: bool
    toolchain: tuple[tuple[str, str], ...]
    promoted_at: str
    approved_by: str | None
```

## 3. Engine Designs

### 3.1 StatisticsEngine (`statistics.py`)

Pure functions. No state. No I/O.

```python
class StatisticsEngine:
    @staticmethod
    def compute_metric_stats(
        samples: tuple[Sample, ...], metric_name: str, unit: str
    ) -> MetricStats: ...

    @staticmethod
    def compute_case_analysis(
        case_id: str, samples: tuple[Sample, ...],
        scenario_id: str, platform_id: str
    ) -> CaseAnalysis: ...

    @staticmethod
    def detect_anomalies(stats: MetricStats) -> tuple[str, ...]:
        """Deterministic anomaly detection.
        - single_sample: only one successful sample
        - all_errors: no successful samples
        - zero_variance: stddev == 0 with >1 sample
        - high_variance: stddev > 2 * abs(mean) when mean != 0
        - extreme_outlier: max > mean + 5 * stddev
        Returns sorted, deduplicated tuple."""
```

**Unit inference** from metric name:
- `*_ns` → `"ns"`
- `*_cycles` → `"cycles"`
- `*_bytes` → `"bytes"`
- `*_ratio`, `*_pct` → `"ratio"`
- `accesses`, `*_count`, `*_cpu` → `"count"`

### 3.2 ComparisonEngine (`comparison.py`)

**Phase 4 scope: Protocol definition + documentation stub.**
Implementation deferred to Phase 5 (release freeze), where before/after
comparison becomes meaningful.

```python
class ComparisonEngine:
    """Protocol for cross-run comparison. Phase 4 defines the interface;
    full implementation with classify_delta logic is deferred to Phase 5."""

    @staticmethod
    def compare_runs(
        baseline: CaseAnalysis, current: CaseAnalysis, tolerance_pct: float = 5.0
    ) -> CrossRunComparison:
        """Phase 4 stub: returns CrossRunComparison with classification
        'incompatible' and note 'cross-run comparison deferred to Phase 5'."""
        ...


# Phase 5 implementation will populate these classification rules:
# - Both present, delta within ±5% → "unchanged"
# - Both present, current < baseline by >5% → "improved"
# - Both present, current > baseline by >5% → "regressed"
# - One missing → "missing"
# - Different platform/scenario → "incompatible"
```

`CrossRunComparison` and `CrossRunMetricDelta` models remain in `models.py`
so that `AnalysisSummary` can carry an empty comparison tuple. The
`--baseline` flag on `probe analyze` is accepted but produces a note
"cross-run comparison deferred to Phase 5" rather than an error.

### 3.3 ResultIngester + LegacyImporter (`ingestion.py`)

```python
class ResultIngester:
    def __init__(self, store: ResultStore): ...
    def ingest(self, paths: tuple[Path, ...]) -> tuple[RunResult, ...]:
        """Load each path. Validate schema_version==2.
        Reject duplicate run_ids."""


class LegacyImporter(Protocol):
    source_format: str
    parser_version: str
    def can_handle(self, path: Path) -> bool: ...
    def import_log(self, path: Path) -> ImportedRecord: ...
```

### 3.4 FigureGenerator (`figures.py`)

```python
class FigureGenerator:
    def __init__(self, analysis: AnalysisSummary): ...

    def latency_bar_chart(self, output_dir: Path) -> FigureManifest: ...
    def migration_penalty_chart(self, output_dir: Path) -> FigureManifest: ...
    def metric_summary_table(self, output_dir: Path) -> FigureManifest: ...
    def generate_all(self, output_dir: Path) -> tuple[FigureManifest, ...]: ...
```

Uses `matplotlib` with `'Agg'` backend. Each figure writes a PNG with a
stable filename (`{figure_id}.png`). Figures are sized for report embedding
(8×5 inches default). `FigureManifest.caption` is embedded in the PNG
metadata where possible.

### 3.5 ReportGenerator (`report.py`)

```python
class ReportGenerator:
    def __init__(
        self, analysis: AnalysisSummary,
        figures: tuple[FigureManifest, ...]
    ): ...

    def generate(self) -> str:
        """Returns deterministic Markdown report string."""

    def write(self, output_dir: Path, regeneration_command: str) -> ReportManifest:
        """Writes report.md, returns manifest."""
```

**Deterministic report structure (8 sections):**

1. **Title + Provenance** — platform, commit, run IDs, dirty-tree, timestamp
2. **Executive Summary** — case count, status breakdown, key findings
3. **Per-Scenario Analysis** — metric table + anomaly notes for each case
4. **Cross-Run Comparison** — (omitted if single run) delta tables
5. **Figures** — embedded by filename reference
6. **Methodology Notes** — links to methodology docs
7. **Limitations & Unresolved Questions**
8. **Appendix** — regeneration command, input manifest

Edge cases:
- Empty input → structured error section, not silent
- All-error samples → `"All samples failed"` section with failure list
- Incompatible baseline → explicit warning block
- Partial analysis → `"Partial Results"` badge on affected sections

### 3.6 BaselinePromoter (`baseline.py`)

Python API only. No CLI command in Phase 4.

```python
class BaselinePromoter:
    def __init__(self, baseline_root: Path = RESULTS_BASELINE_V1_0): ...

    def validate_candidate(
        self, *, run_ids: tuple[str, ...], analysis_id: str,
        report_id: str | None, figure_ids: tuple[str, ...],
        repository_commit: str, dirty_tree: bool
    ) -> tuple[str, ...]:
        """Returns validation errors (empty = valid).
        Rejects: dirty_tree, missing artifacts, mismatched commits,
        schema-incompatible inputs."""

    def promote(
        self, manifest: BaselineManifest,
        artifacts: tuple[Path, ...],
        approved_by: str | None = None
    ) -> Path:
        """Copy evidence package to results/baselines/v1.0/.
        Writes BaselineManifest JSON alongside artifacts."""
```

### 3.7 AnalysisStore (`store.py`)

Follows the same atomic-write pattern as `ResultStore`:
temp file → `fsync` → `os.replace` → parent `fsync`.

```python
class AnalysisStore:
    def __init__(self, analysis_dir: Path): ...
    def write_analysis(self, summary: AnalysisSummary) -> Path: ...
    def read_analysis(self, analysis_id: str) -> AnalysisSummary: ...
    def list_analyses(self) -> tuple[str, ...]: ...
```

Analysis artifacts land under `results/analysis/` (git-ignored).

## 4. CLI Design

### 4.1 probe analyze

```sh
probe analyze --run <run-result.json> [--run <run-result.json> ...] \
  [--baseline <analysis-or-baseline.json>] --output-dir <dir> [-o table|json]
```

- `--run` (required, repeatable): one or more RunResult JSON files.
- `--baseline` (optional): prior AnalysisSummary for cross-run comparison.
- `--output-dir` (default: `results/analysis/`).
- `-o` (default: `table`).
- Exit `0` on success, `16` on read/validation/persistence failure.

### 4.2 probe report

```sh
probe report --analysis <analysis-summary.json> --output-dir <dir> \
  [--format markdown] [-o table|json]
```

- `--analysis` (required): path to AnalysisSummary JSON.
- `--output-dir` (default: `results/reports/`).
- `--format` (default: `markdown`, only value in Phase 4).
- `-o` (default: `table`).
- Exit `0` on success, `16` on read/generation/write failure.

### 4.3 Changes to Existing Files

| File | Change |
|------|--------|
| `arm64_probe/cli/parser.py` | Add `"analyze"` and `"report"` to `COMMANDS`; add `analyze_parser` and `report_parser` |
| `arm64_probe/cli/main.py` | Add `_run_analyze(args)` and `_run_report(args)` dispatch functions |
| `arm64_probe/cli/render.py` | Add `render_analyze()` and `render_report()` (table + JSON branches) |
| `Makefile` | Add `phase4-check` target; update `help` |
| `docs/design/cli-contract.md` | Add `probe analyze` and `probe report` |
| `pyproject.toml` | Add `matplotlib` dependency |

## 5. Public Schemas

### 5.1 analysis-summary.schema.json

JSON Schema 2020-12. Required: `analysis_id`, `schema_version` (const: 1),
`source_runs`, `platform_id`, `repository_id`, `repository_commit`,
`dirty_tree`, `toolchain`, `case_analyses`, `cross_run_comparisons`,
`anomalies`, `generated_at`. `additionalProperties: false`.

### 5.2 baseline-manifest.schema.json

JSON Schema 2020-12. Required: `baseline_id`, `version`, `source_run_ids`,
`analysis_id`, `commands`, `repository_commit`, `dirty_tree`, `toolchain`,
`promoted_at`. `additionalProperties: false`.

## 6. Serialization

Add branches to `arm64_probe/serialization/model_json.py::to_data()`:

| Type | JSON Shape |
|------|-----------|
| `MetricStats` | dict with all fields |
| `CaseAnalysis` | dict, `metric_stats` as sorted name→dict mapping |
| `CrossRunMetricDelta` | dict |
| `CrossRunComparison` | dict, `metric_deltas` as sorted name→dict mapping |
| `AnalysisSummary` | dict, `case_analyses` as sorted array |
| `FigureManifest` | dict |
| `ReportManifest` | dict |
| `ImportedRecord` | dict |
| `BaselineManifest` | dict |

Add corresponding `_dict_to_*` deserialization branches in the same module.

## 7. Test Strategy

### 7.1 Unit Tests

| File | Scope |
|------|-------|
| `tests/unit/test_analysis_models.py` | Frozen invariants, round-trip serialization, schema validation |
| `tests/unit/test_statistics.py` | All stat computations, unit inference, all 5 anomaly rules, edge cases (empty, single, all-error) |
| `tests/unit/test_ingestion.py` | `ResultIngester` multi-run, duplicate rejection, `LegacyImporter` protocol conformance |
| `tests/unit/test_comparison.py` | Phase 4 stub: returns "incompatible" note, model round-trip; full classification tests deferred to Phase 5 |
| `tests/unit/test_analysis_store.py` | Atomic write/read, oversize rejection, schema version validation |
| `tests/unit/test_figures.py` | Figure generation determinism, manifest completeness, PNG output validation |
| `tests/unit/test_report.py` | Deterministic output, section structure, claim traceability, edge cases (empty/partial/failed/incompatible) |
| `tests/unit/test_baseline.py` | Validation rules, dirty-tree rejection, missing artifact detection |

### 7.2 Contract Tests

| File | Scope |
|------|-------|
| `tests/contract/test_cli_analyze.py` | CLI forms, exit codes, `-o`, missing `--run` → 2, invalid JSON → 16 |
| `tests/contract/test_cli_report.py` | CLI forms, `--analysis` required, `--format`, `-o`, exit codes |
| `tests/contract/test_analysis_schemas.py` | Schema validation for example `AnalysisSummary` and `BaselineManifest` |
| `tests/contract/test_phase4_acceptance.py` | AC1–AC9 evidence, platform-name branch check in `analysis/`, frozen paths, Phase 1-3 regression |

### 7.3 Integration Tests

| File | Scope |
|------|-------|
| `tests/integration/test_phase4_analysis_workflow.py` | End-to-end: fixture RunResult → `probe analyze` → valid AnalysisSummary → round-trip |
| `tests/integration/test_phase4_report_workflow.py` | End-to-end: fixture AnalysisSummary → `probe report` → Markdown + manifest |
| `tests/integration/test_phase4_legacy_import.py` | Legacy fixture → `LegacyImporter` → `ImportedRecord` → feeds `StatisticsEngine` |

## 8. Makefile Target

```makefile
phase4-check:
    $(UV_RUN) python -m unittest discover -s tests -p 'test_analysis_*.py' -v
    $(UV_RUN) python -m unittest discover -s tests -p 'test_statistics.py' -v
    $(UV_RUN) python -m unittest discover -s tests -p 'test_ingestion.py' -v
    $(UV_RUN) python -m unittest discover -s tests -p 'test_comparison.py' -v
    $(UV_RUN) python -m unittest discover -s tests -p 'test_figures.py' -v
    $(UV_RUN) python -m unittest discover -s tests -p 'test_report.py' -v
    $(UV_RUN) python -m unittest discover -s tests -p 'test_baseline.py' -v
    $(UV_RUN) python -m unittest tests.contract.test_cli_analyze \
        tests.contract.test_cli_report \
        tests.contract.test_analysis_schemas \
        tests.contract.test_phase4_acceptance -v
    $(UV_RUN) python scripts/legacy_manifest.py verify
    make phase3-check
```

## 9. Repository Boundaries

| Path | Status |
|------|--------|
| `results/analysis/` | git-ignored |
| `results/reports/` | git-ignored |
| `results/baselines/v1.0/` | committed (reviewed evidence) |
| `docs/methodology/` | committed |
| `docs/roadmap/` | committed |
| `arm64_probe/analysis/` | committed |
| `schemas/analysis-summary.schema.json` | committed |
| `schemas/baseline-manifest.schema.json` | committed |

## 10. Architecture Decision Record

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Read-only analysis package | No host mutation; reuses Phase 3 safety boundaries |
| 2 | `statistics` stdlib module | Deterministic median/stdev; no numpy dependency for stats |
| 3 | matplotlib `'Agg'` for figures | Headless PNG generation; single new dependency, explicit justification |
| 4 | `AnalysisStore` separate from `ResultStore` | Different artifact lifecycle; analysis is regenerable from runs |
| 5 | `--baseline` flag for cross-run comparison | Enables comparison without requiring baseline promotion first |
| 6 | Legacy import via Protocol + example adapter | Follows `ProbeAdapter` pattern; full coverage deferred to Phase 5+ |
| 7 | Baseline promotion as Python API only | Reviewed action; no CLI command until Phase 5 release freeze |
| 8 | New schemas: `analysis-summary` v1, `baseline-manifest` v1 | Schema evolution independent of `RunResult` v2 |
| 9 | Report sections are deterministic | Same input → same output; tested via string equality on known fixtures |
| 10 | C&C comparison as framework + qualitative | Numeric data deferred to Phase 5 after v1.0 baseline collected |
| 11 | ComparisonEngine deferred to Phase 5 | Protocol + documentation stub in Phase 4; before/after comparison needs two baselines, which only exist at release time |
| 12 | Baseline matrix: 4 CPUs × 5 cache levels × 2 page policies + 12 migration pairs × 6 sizes | ~92 unique cases, ~172 samples; defined as `--profile baseline`; aligns with legacy v2.7.3–v2.7.11 scope |
| 13 | Memory bandwidth in X925/A725 roadmap | Referenced in `docs/roadmap/x925-a725-deep-dive.md`; links to Chips and Cheese GB10 memory subsystem analysis (https://chipsandcheese.com/p/inside-nvidia-gb10s-memory-subsystem) |
