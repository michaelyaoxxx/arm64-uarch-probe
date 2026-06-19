# Phase 4 Analysis and Report Generation — 详细设计

> **Handoff:** `docs/superpowers/handoffs/2026-06-17-phase4-handoff.md`
> **状态:** 已批准设计 — 准备进入 implementation plan
> **目标:** `probe analyze` + `probe report` + baseline promotion

## 1. Architecture Overview

Phase 4 在 Phase 3 execution layer 之上增加一个只读 analysis 和 report pipeline。它**绝不**获取 `MutationLock`，不写 journals，也不调用 `sudo`。所有 analysis 都消费结构化 `RunResult` 或经 `LegacyImporter` 适配后的 records；任何代码都不直接读取 legacy text。

**为什么不需要 `sudo`？** Phase 3（`probe run`）是**测量**阶段——它需要 `sudo` 来通过 `EnvironmentCoordinator` 控制 `cpufreq` governor 和配置 hugepage。Phase 4 是**消费**阶段——它读取已经包含测量数据的 `RunResult` JSON 文件。分析、统计、图表和报告是纯计算，零主机变更。这个边界是刻意设计的：用特权一次性采集，在任何地方无特权分析。

**Phase 4 不发起新测量。** `probe analyze` 和 `probe report` 是严格的只读消费者。它们接受由 `probe run`（Phase 3）已经采集的 `RunResult` 和 `AnalysisSummary` JSON 文件。Phase 4 绝不调用 `Runner`、`EnvironmentCoordinator` 或任何 C probe 二进制。这是采集阶段和分析阶段之间的基本契约——Phase 3 采集，Phase 4 消费。任何新的测量活动（例如基线刷新、带宽探测）需要先单独运行 Phase 3 调用，然后 Phase 4 才能分析其输出。

### 1.1 Data Flow

```text
RunResult JSON ──→ ResultIngester ──→ StatisticsEngine ──→ AnalysisSummary JSON
                         │
Legacy text ──→ LegacyImporter ──→ ImportedRecord ────────┘
                         │
ComparisonEngine ←── (--baseline flag)
                         │
FigureGenerator ──→ PNG figures + FigureManifest
                         │
ReportGenerator ──→ report.md + ReportManifest
                         │
BaselinePromoter ──→ results/baselines/v1.0/   (Python API, no CLI)
```

1. `probe analyze --run <result.json> ...` 加载 `RunResult` files，运行 statistics 和 comparison engines，并持久化 `AnalysisSummary` JSON。
2. `probe report --analysis <analysis.json>` 加载 `AnalysisSummary`，运行 figure 和 report generation，写出 figures + Markdown report。
3. Candidate baseline promotion 是一个 reviewed action，通过 Python API 执行。

### 1.2 Module Layout

```text
arm64_probe/analysis/                  ← new top-level package (read-only)
    __init__.py                        ← exports public API
    models.py                          ← 8 frozen dataclasses
    store.py                           ← AnalysisStore (atomic persistence)
    statistics.py                      ← StatisticsEngine (pure functions)
    comparison.py                      ← ComparisonEngine (cross-run)
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

- **Python stdlib:** `statistics`、`json`、`csv`、`hashlib`、`re`、`pathlib`。
- **matplotlib**（新增）：使用 `'Agg'` backend 进行 headless PNG generation。
  需要更新 `pyproject.toml` dependency、`uv.lock`，并添加 contract tests 校验 figure metadata（不是 pixel-perfect equality）。
- 不新增其他 dependencies。

## 2. Domain Models

所有 models 都是 `@dataclass(frozen=True)`。Public collections 使用 `tuple[...]`，并按确定性排序。所有 IDs 遵循现有 kebab-case 约定。

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

Pure functions。无 state。无 I/O。

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

**Unit inference** 基于 metric name：

- `*_ns` → `"ns"`
- `*_cycles` → `"cycles"`
- `*_bytes` → `"bytes"`
- `*_ratio`、`*_pct` → `"ratio"`
- `accesses`、`*_count`、`*_cpu` → `"count"`

### 3.2 ComparisonEngine (`comparison.py`)

```python
class ComparisonEngine:
    @staticmethod
    def compare_runs(
        baseline: CaseAnalysis, current: CaseAnalysis, tolerance_pct: float = 5.0
    ) -> CrossRunComparison: ...

    @staticmethod
    def classify_delta(
        baseline_val: float | None, current_val: float | None, tolerance_pct: float
    ) -> str:
        """→ 'unchanged' | 'improved' | 'regressed' | 'missing'"""
```

Classification rules（以 latency 为中心；lower = better）：

- 二者都存在，delta 在 ±5% 内 → `"unchanged"`
- 二者都存在，current 比 baseline 低超过 5% → `"improved"`
- 二者都存在，current 比 baseline 高超过 5% → `"regressed"`
- 一方 missing → `"missing"`
- Platform/scenario 不同 → `"incompatible"`

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

使用带 `'Agg'` backend 的 `matplotlib`。每张 figure 写出为一个具有稳定文件名（`{figure_id}.png`）的 PNG。Figures 默认大小适合 report embedding（8×5 inches）。在可行时，`FigureManifest.caption` 嵌入 PNG metadata 中。

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

**确定性 report structure（8 sections）：**

1. **Title + Provenance** — platform、commit、run IDs、dirty-tree、timestamp
2. **Executive Summary** — case count、status breakdown、key findings
3. **Per-Scenario Analysis** — 每个 case 的 metric table + anomaly notes
4. **Cross-Run Comparison** — delta tables；如果是 single run，则省略
5. **Figures** — 通过 filename reference 嵌入
6. **Methodology Notes** — 链接到 methodology docs
7. **Limitations & Unresolved Questions**
8. **Appendix** — regeneration command、input manifest

Edge cases：

- Empty input → structured error section，而不是静默处理
- All-error samples → `"All samples failed"` section，并包含 failure list
- Incompatible baseline → 显式 warning block
- Partial analysis → 在受影响 sections 上标记 `"Partial Results"` badge

### 3.6 BaselinePromoter (`baseline.py`)

仅 Python API。Phase 4 不提供 CLI command。

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

遵循与 `ResultStore` 相同的 atomic-write pattern：
temp file → `fsync` → `os.replace` → parent `fsync`。

```python
class AnalysisStore:
    def __init__(self, analysis_dir: Path): ...
    def write_analysis(self, summary: AnalysisSummary) -> Path: ...
    def read_analysis(self, analysis_id: str) -> AnalysisSummary: ...
    def list_analyses(self) -> tuple[str, ...]: ...
```

Analysis artifacts 落在 `results/analysis/` 下（被 git 忽略）。

## 4. CLI Design

### 4.1 probe analyze

```sh
probe analyze --run <run-result.json> [--run <run-result.json> ...] \
  [--baseline <analysis-or-baseline.json>] --output-dir <dir> [-o table|json]
```

- `--run`（required，repeatable）：一个或多个 RunResult JSON files。
- `--baseline`（optional）：用于 cross-run comparison 的 prior AnalysisSummary。
- `--output-dir`（default：`results/analysis/`）。
- `-o`（default：`table`）。
- 成功 exit `0`，read/validation/persistence failure exit `16`。

### 4.2 probe report

```sh
probe report --analysis <analysis-summary.json> --output-dir <dir> \
  [--format markdown] [-o table|json]
```

- `--analysis`（required）：指向 AnalysisSummary JSON 的 path。
- `--output-dir`（default：`results/reports/`）。
- `--format`（default：`markdown`，Phase 4 中唯一取值）。
- `-o`（default：`table`）。
- 成功 exit `0`，read/generation/write failure exit `16`。

### 4.3 Changes to Existing Files

| File | Change |
|------|--------|
| `arm64_probe/cli/parser.py` | 将 `"analyze"` 和 `"report"` 添加到 `COMMANDS`；添加 `analyze_parser` 和 `report_parser` |
| `arm64_probe/cli/main.py` | 添加 `_run_analyze(args)` 和 `_run_report(args)` dispatch functions |
| `arm64_probe/cli/render.py` | 添加 `render_analyze()` 和 `render_report()`（table + JSON branches） |
| `Makefile` | 添加 `phase4-check` target；更新 `help` |
| `docs/design/cli-contract.md` | 添加 `probe analyze` 和 `probe report` |
| `pyproject.toml` | 添加 `matplotlib` dependency |

## 5. Public Schemas

### 5.1 analysis-summary.schema.json

JSON Schema 2020-12。Required：`analysis_id`、`schema_version`（const: 1）、`source_runs`、`platform_id`、`repository_id`、`repository_commit`、`dirty_tree`、`toolchain`、`case_analyses`、`cross_run_comparisons`、`anomalies`、`generated_at`。`additionalProperties: false`。

### 5.2 baseline-manifest.schema.json

JSON Schema 2020-12。Required：`baseline_id`、`version`、`source_run_ids`、`analysis_id`、`commands`、`repository_commit`、`dirty_tree`、`toolchain`、`promoted_at`。`additionalProperties: false`。

## 6. Serialization

在 `arm64_probe/serialization/model_json.py::to_data()` 中添加 branches：

| Type | JSON Shape |
|------|-----------|
| `MetricStats` | 包含所有 fields 的 dict |
| `CaseAnalysis` | dict，`metric_stats` 为排序后的 name→dict mapping |
| `CrossRunMetricDelta` | dict |
| `CrossRunComparison` | dict，`metric_deltas` 为排序后的 name→dict mapping |
| `AnalysisSummary` | dict，`case_analyses` 为排序后的 array |
| `FigureManifest` | dict |
| `ReportManifest` | dict |
| `ImportedRecord` | dict |
| `BaselineManifest` | dict |

在同一 module 中添加对应的 `_dict_to_*` deserialization branches。

## 7. Test Strategy

### 7.1 Unit Tests

| File | Scope |
|------|-------|
| `tests/unit/test_analysis_models.py` | Frozen invariants、round-trip serialization、schema validation |
| `tests/unit/test_statistics.py` | 所有 stat computations、unit inference、全部 5 条 anomaly rules、edge cases（empty、single、all-error） |
| `tests/unit/test_ingestion.py` | `ResultIngester` multi-run、duplicate rejection、`LegacyImporter` protocol conformance |
| `tests/unit/test_comparison.py` | 全部 5 种 classifications、tolerance edge cases、missing/incompatible |
| `tests/unit/test_analysis_store.py` | Atomic write/read、oversize rejection、schema version validation |
| `tests/unit/test_figures.py` | Figure generation determinism、manifest completeness、PNG output validation |
| `tests/unit/test_report.py` | Deterministic output、section structure、claim traceability、edge cases（empty/partial/failed/incompatible） |
| `tests/unit/test_baseline.py` | Validation rules、dirty-tree rejection、missing artifact detection |

### 7.2 Contract Tests

| File | Scope |
|------|-------|
| `tests/contract/test_cli_analyze.py` | CLI forms、exit codes、`-o`、missing `--run` → 2、invalid JSON → 16 |
| `tests/contract/test_cli_report.py` | CLI forms、`--analysis` required、`--format`、`-o`、exit codes |
| `tests/contract/test_analysis_schemas.py` | 针对 example `AnalysisSummary` 和 `BaselineManifest` 的 schema validation |
| `tests/contract/test_phase4_acceptance.py` | AC1–AC9 evidence、`analysis/` 中的 platform-name branch check、frozen paths、Phase 1-3 regression |

### 7.3 Integration Tests

| File | Scope |
|------|-------|
| `tests/integration/test_phase4_analysis_workflow.py` | End-to-end：fixture RunResult → `probe analyze` → valid AnalysisSummary → round-trip |
| `tests/integration/test_phase4_report_workflow.py` | End-to-end：fixture AnalysisSummary → `probe report` → Markdown + manifest |
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
| `results/baselines/v1.0/` | committed（reviewed evidence） |
| `docs/methodology/` | committed |
| `docs/roadmap/` | committed |
| `arm64_probe/analysis/` | committed |
| `schemas/analysis-summary.schema.json` | committed |
| `schemas/baseline-manifest.schema.json` | committed |

## 10. Architecture Decision Record

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Read-only analysis package | 无 host mutation；复用 Phase 3 safety boundaries |
| 2 | `statistics` stdlib module | 确定性的 median/stdev；stats 不引入 numpy dependency |
| 3 | matplotlib `'Agg'` for figures | Headless PNG generation；单一新增 dependency，且有显式理由 |
| 4 | `AnalysisStore` separate from `ResultStore` | artifact lifecycle 不同；analysis 可由 runs 重新生成 |
| 5 | `--baseline` flag for cross-run comparison | 不要求先 baseline promotion 即可进行 comparison |
| 6 | Legacy import via Protocol + example adapter | 遵循 `ProbeAdapter` pattern；完整覆盖推迟到 Phase 5+ |
| 7 | Baseline promotion as Python API only | Reviewed action；Phase 5 release freeze 前不提供 CLI command |
| 8 | New schemas: `analysis-summary` v1, `baseline-manifest` v1 | Schema evolution 独立于 `RunResult` v2 |
| 9 | Report sections are deterministic | 相同输入 → 相同输出；通过 known fixtures 的 string equality 测试 |
| 10 | C&C comparison as framework + qualitative | Numeric data 推迟到 Phase 5，等待 v1.0 baseline collected |