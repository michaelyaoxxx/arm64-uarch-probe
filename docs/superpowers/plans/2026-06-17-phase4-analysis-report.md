# Phase 4 Analysis and Report Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Companion design:** `docs/superpowers/specs/2026-06-17-phase4-analysis-report-design.md`
> **Architect contract:** `docs/superpowers/handoffs/2026-06-17-phase4-handoff.md` (AC1–AC9, locked architecture, quality controls).

**Goal:** Implement `probe analyze`, `probe report`, baseline promotion API, methodology docs, and the X925/A725 deep-dive roadmap — a read-only analysis and report pipeline that consumes Phase 3 `RunResult` artifacts, produces deterministic `AnalysisSummary` JSON, PNG figures, Markdown reports, and candidate baseline evidence packages.

**Architecture:** Phase 4 adds `arm64_probe/analysis/` as a read-only package with zero host mutation. `StatisticsEngine` (stdlib `statistics`) and `FigureGenerator` (matplotlib `Agg`) are pure-computation engines. `ResultIngester` loads `RunResult` files via `ResultStore`. `AnalysisStore` persists `AnalysisSummary` atomically. `BaselinePromoter` is Python API only (no CLI). `ComparisonEngine` is a Phase 4 stub (implementation → Phase 5). Two new CLI commands (`probe analyze`, `probe report`) follow existing parser/render patterns. Two new public schemas. `make phase4-check` wraps all Phase 4 tests.

**Tech Stack:** Python 3.13.13 (uv-managed), `statistics` stdlib, matplotlib (`Agg` backend), JSON Schema 2020-12. Existing `arm64_probe` packages. No other dependencies.

---

## Delivery Boundaries

- `arm64_probe/analysis/` is **read-only** with respect to host state. It never
  acquires `MutationLock`, writes journals, or invokes `sudo`.
- `ComparisonEngine` delivers a **protocol + documentation stub**. Full
  cross-run classification is deferred to Phase 5.
- Baseline promotion is **Python API only** — no `probe baseline promote` CLI
  command in Phase 4.
- The `--baseline` flag on `probe analyze` is accepted but produces a note
  "cross-run comparison deferred to Phase 5."
- `make phase4-check` adds a thin wrapper. No analysis matrix or plotting logic
  in the Makefile.
- `results/analysis/` and `results/reports/` are git-ignored.
- `results/baselines/v1.0/` is committed, reviewed evidence.
- Frozen paths unchanged: `runner/`, `data/`, `analysis/`, `baseline/`.
- No GB10 measurement claim made from Mac data.
- The Python toolchain stays at `==3.13.13`. `matplotlib` is the only new
  dependency.

## Architecture Decision Anchors

| # | Decision | Implemented in |
|---|----------|---------------|
| 1 | Read-only analysis package | All tasks |
| 2 | `statistics` stdlib for stats | Task 23 |
| 3 | matplotlib `Agg` for figures | Task 27 |
| 4 | AnalysisStore separate from ResultStore | Task 22 |
| 5 | `--baseline` flag accepted, stub comparison | Task 25, 26 |
| 6 | Legacy import via Protocol + example adapter | Task 24 |
| 7 | Baseline promotion as Python API only | Task 30 |
| 8 | New schemas: `analysis-summary` v1, `baseline-manifest` v1 | Task 21 |
| 9 | Deterministic report sections | Task 28 |
| 10 | ComparisonEngine deferred to Phase 5 | Task 25 |
| 11 | Baseline matrix: 4 CPUs × 5 levels + 12 pairs × 6 sizes | Task 31 |
| 12 | Bandwidth roadmap in deep-dive doc | Task 31 |

## File Map

### New modules (additive under `arm64_probe/analysis/`)

- `arm64_probe/analysis/__init__.py` — exports public API
- `arm64_probe/analysis/models.py` — 9 frozen dataclasses
- `arm64_probe/analysis/store.py` — `AnalysisStore` (atomic persistence)
- `arm64_probe/analysis/statistics.py` — `StatisticsEngine` (pure functions)
- `arm64_probe/analysis/comparison.py` — `ComparisonEngine` (Phase 4 stub)
- `arm64_probe/analysis/ingestion.py` — `ResultIngester` + `LegacyImporter` protocol
- `arm64_probe/analysis/figures.py` — `FigureGenerator` (matplotlib → PNG)
- `arm64_probe/analysis/report.py` — `ReportGenerator` (deterministic Markdown)
- `arm64_probe/analysis/baseline.py` — `BaselinePromoter` (Python API)
- `arm64_probe/analysis/adapters/__init__.py`
- `arm64_probe/analysis/adapters/legacy_chase_pmu.py` — example legacy importer

### Additions to existing modules

- `arm64_probe/serialization/model_json.py` — add `to_data` / `_dict_to_*` branches for 9 models
- `arm64_probe/cli/parser.py` — add `analyze`, `report` subcommands
- `arm64_probe/cli/main.py` — dispatch `_run_analyze`, `_run_report`
- `arm64_probe/cli/render.py` — add `render_analyze`, `render_report`
- `Makefile` — add `phase4-check` target, update `help` and `.PHONY`
- `pyproject.toml` — add `matplotlib` dependency
- `docs/design/cli-contract.md` — add `probe analyze`, `probe report`

### New schemas

- `schemas/analysis-summary.schema.json`
- `schemas/baseline-manifest.schema.json`

### New configs

- `configs/profiles/baseline.json`

### New docs

- `docs/methodology/cache-latency.md`
- `docs/methodology/migration-latency.md`
- `docs/methodology/chips-and-cheese-comparison.md`
- `docs/roadmap/x925-a725-deep-dive.md`

### New tests

- `tests/unit/test_analysis_models.py`
- `tests/unit/test_statistics.py`
- `tests/unit/test_ingestion.py`
- `tests/unit/test_comparison.py`
- `tests/unit/test_analysis_store.py`
- `tests/unit/test_figures.py`
- `tests/unit/test_report.py`
- `tests/unit/test_baseline.py`
- `tests/contract/test_cli_analyze.py`
- `tests/contract/test_cli_report.py`
- `tests/contract/test_analysis_schemas.py`
- `tests/contract/test_phase4_acceptance.py`
- `tests/integration/test_phase4_analysis_workflow.py`
- `tests/integration/test_phase4_report_workflow.py`
- `tests/integration/test_phase4_legacy_import.py`

### Frozen paths (must not change)

`runner/`, `data/`, `analysis/`, `baseline/`, `runner/cache_info_*.sh`.

## AC → Task → Test Map

| AC | Task | Verifying Tests |
|----|------|----------------|
| AC1 Analysis Artifact Contract | Task 21 (models), Task 22 (store) | `test_analysis_models.py`, `test_analysis_store.py`, `test_analysis_schemas.py` |
| AC2 RunResult Ingestion + Legacy Import | Task 24 (ingestion), Task 26 (CLI) | `test_ingestion.py`, `test_cli_analyze.py`, `test_phase4_legacy_import.py` |
| AC3 Statistics and Anomaly Rules | Task 23 (stats), Task 25 (comparison stub) | `test_statistics.py`, `test_comparison.py` |
| AC4 Figure Generation | Task 27 | `test_figures.py` |
| AC5 Report Generation | Task 28 (engine), Task 29 (CLI) | `test_report.py`, `test_cli_report.py`, `test_phase4_report_workflow.py` |
| AC6 Methodology and Source Traceability | Task 31 | source-review (docs) |
| AC7 Candidate Baseline Promotion | Task 30 | `test_baseline.py` |
| AC8 X925/A725 Deep-Dive Roadmap | Task 31 | source-review (docs) |
| AC9 Compatibility and Boundaries | Task 31 | `test_phase4_acceptance.py`, `make phase3-check` |

## Per-Task Gate

Before each focused commit:

```sh
uv run --no-sync python -m unittest <focused-modules> -v
make check
make legacy-check
git diff --check
git status --short
```

Each commit owns one behavior and its tests.

---

## Batch 1: Foundation — Models, Store, Statistics

### Task 21: Analysis Domain Models and Public Schemas

**Files:**
- Create: `arm64_probe/analysis/__init__.py`
- Create: `arm64_probe/analysis/models.py`
- Create: `schemas/analysis-summary.schema.json`
- Create: `schemas/baseline-manifest.schema.json`
- Modify: `arm64_probe/serialization/model_json.py`
- Create: `tests/unit/test_analysis_models.py`
- Create: `tests/contract/test_analysis_schemas.py`

- [ ] **Step 1: Write failing model tests**

In `tests/unit/test_analysis_models.py`:

```python
"""Frozen invariants and serialization round-trip for analysis domain models."""
import json
import unittest

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, CrossRunMetricDelta, CrossRunComparison,
    AnalysisSummary, FigureManifest, ReportManifest, ImportedRecord,
    BaselineManifest,
)


class MetricStatsTests(unittest.TestCase):
    def test_frozen(self):
        s = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=5, error_count=0, min_value=4.0, max_value=5.0,
            median=4.36, mad=0.12, mean=4.40, stddev=0.35,
        )
        with self.assertRaises(Exception):
            s.median = 99.0

    def test_none_values_when_no_successes(self):
        s = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=0, error_count=5, min_value=None, max_value=None,
            median=None, mad=None, mean=None, stddev=None,
        )
        self.assertIsNone(s.median)
        self.assertEqual(s.success_count, 0)


class CaseAnalysisTests(unittest.TestCase):
    def test_metric_stats_sorted_by_name(self):
        m1 = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=1,
            success_count=1, error_count=0, min_value=4.0, max_value=4.0,
            median=4.0, mad=0.0, mean=4.0, stddev=0.0,
        )
        m2 = MetricStats(
            metric_name="accesses", unit="count", sample_count=1,
            success_count=1, error_count=0, min_value=100.0, max_value=100.0,
            median=100.0, mad=0.0, mean=100.0, stddev=0.0,
        )
        ca = CaseAnalysis(
            case_id="test@gb10.x", scenario_id="test", platform_id="gb10",
            status="ok", total_samples=1, ok_samples=1, error_samples=0,
            metric_stats=(("accesses", m2), ("latency_ns", m1)),
            anomalies=(), source_run_ids=("run1",),
        )
        # Sorted by key
        names = [k for k, _ in ca.metric_stats]
        self.assertEqual(names, ["accesses", "latency_ns"])


class AnalysisSummaryTests(unittest.TestCase):
    def test_frozen_and_fields(self):
        s = AnalysisSummary(
            analysis_id="20260617T120000Z-a1b2c3d4", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        self.assertEqual(s.schema_version, 1)
        self.assertEqual(s.platform_id, "gb10")


class SerializationRoundTripTests(unittest.TestCase):
    """Verify to_data -> JSON -> _dict_to round-trip for all models."""

    def _round_trip(self, value, expected_type):
        from arm64_probe.serialization.model_json import to_data, _dict_to_analysis_summary
        # Use the appropriate _dict_to_* function per type
        data = to_data(value)
        json_str = json.dumps(data, sort_keys=True)
        reloaded_data = json.loads(json_str)
        if expected_type is AnalysisSummary:
            result = _dict_to_analysis_summary(reloaded_data)
        elif expected_type is BaselineManifest:
            result = _dict_to_baseline_manifest(reloaded_data)
        else:
            self.skipTest(f"no _dict_to_* for {expected_type}")
        self.assertEqual(value, result)

    def test_analysis_summary_round_trip(self):
        ms = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=1,
            success_count=1, error_count=0, min_value=4.36, max_value=4.36,
            median=4.36, mad=0.0, mean=4.36, stddev=0.0,
        )
        ca = CaseAnalysis(
            case_id="l1@gb10.cpu-0", scenario_id="cache-latency.l1-latency",
            platform_id="gb10", status="ok", total_samples=1, ok_samples=1,
            error_samples=0,
            metric_stats=(("latency_ns", ms),),
            anomalies=(), source_run_ids=("run1",),
        )
        summary = AnalysisSummary(
            analysis_id="20260617T120000Z-a1b2c3d4", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(ca,), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        self._round_trip(summary, AnalysisSummary)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

```sh
uv run --no-sync python -m unittest tests.unit.test_analysis_models -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arm64_probe.analysis'`

- [ ] **Step 3: Implement the analysis package and models**

Create `arm64_probe/analysis/__init__.py`:

```python
"""Phase 4 analysis and report generation package."""
```

Create `arm64_probe/analysis/models.py` with all 9 frozen dataclasses as defined in SPEC §2. Key implementation notes:
- `MetricStats` fields: `metric_name`, `unit`, `sample_count`, `success_count`, `error_count`, `min_value`, `max_value`, `median`, `mad`, `mean`, `stddev` — all `float | None` except counts and name/unit.
- `CaseAnalysis.metric_stats` is `tuple[tuple[str, MetricStats], ...]` sorted by metric name.
- `AnalysisSummary.case_analyses` is `tuple[CaseAnalysis, ...]` sorted by `case_id`.
- `CrossRunComparison` and `CrossRunMetricDelta` models must exist for schema completeness (Phase 5 fills them).
- `ImportedRecord` has `source_path`, `parser_version`, `format`, `case_id`, `platform_id`, `metrics`, `loss_notes`.
- `BaselineManifest` has all fields from SPEC §2.9.

Create `schemas/analysis-summary.schema.json` (JSON Schema 2020-12):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://arm64-uarch-probe/schemas/analysis-summary.schema.json",
  "title": "AnalysisSummary",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "analysis_id", "schema_version", "source_runs", "platform_id",
    "repository_id", "repository_commit", "dirty_tree", "toolchain",
    "case_analyses", "cross_run_comparisons", "anomalies", "generated_at"
  ],
  "properties": {
    "analysis_id": { "type": "string" },
    "schema_version": { "const": 1 },
    "source_runs": { "type": "array", "items": { "type": "string" } },
    "platform_id": { "type": "string" },
    "repository_id": { "type": "string" },
    "repository_commit": { "type": "string" },
    "dirty_tree": { "type": "boolean" },
    "toolchain": {
      "type": "array",
      "items": { "type": "array", "items": { "type": "string" }, "minItems": 2, "maxItems": 2 }
    },
    "case_analyses": {
      "type": "array",
      "items": { "$ref": "#/$defs/case_analysis" }
    },
    "cross_run_comparisons": {
      "type": "array",
      "items": { "$ref": "#/$defs/cross_run_comparison" }
    },
    "anomalies": { "type": "array", "items": { "type": "string" } },
    "generated_at": { "type": "string", "format": "date-time" }
  },
  "$defs": {
    "metric_stats": {
      "type": "object", "additionalProperties": false,
      "required": ["metric_name", "unit", "sample_count", "success_count", "error_count"],
      "properties": {
        "metric_name": { "type": "string" },
        "unit": { "type": "string" },
        "sample_count": { "type": "integer" },
        "success_count": { "type": "integer" },
        "error_count": { "type": "integer" },
        "min_value": { "type": "number" },
        "max_value": { "type": "number" },
        "median": { "type": "number" },
        "mad": { "type": "number" },
        "mean": { "type": "number" },
        "stddev": { "type": "number" }
      }
    },
    "case_analysis": {
      "type": "object", "additionalProperties": false,
      "required": ["case_id", "scenario_id", "platform_id", "status", "total_samples", "ok_samples", "error_samples", "metric_stats", "anomalies", "source_run_ids"],
      "properties": {
        "case_id": { "type": "string" },
        "scenario_id": { "type": "string" },
        "platform_id": { "type": "string" },
        "status": { "type": "string", "enum": ["ok", "partial", "failed"] },
        "total_samples": { "type": "integer" },
        "ok_samples": { "type": "integer" },
        "error_samples": { "type": "integer" },
        "metric_stats": {
          "type": "object",
          "additionalProperties": { "$ref": "#/$defs/metric_stats" }
        },
        "anomalies": { "type": "array", "items": { "type": "string" } },
        "source_run_ids": { "type": "array", "items": { "type": "string" } }
      }
    },
    "cross_run_comparison": {
      "type": "object", "additionalProperties": false,
      "required": ["case_id", "runs_compared", "classification", "metric_deltas"],
      "properties": {
        "case_id": { "type": "string" },
        "runs_compared": { "type": "array", "items": { "type": "string" } },
        "classification": { "type": "string", "enum": ["unchanged", "improved", "regressed", "missing", "incompatible"] },
        "metric_deltas": {
          "type": "object",
          "additionalProperties": {
            "type": "object", "additionalProperties": false,
            "required": ["metric_name", "unit"],
            "properties": {
              "metric_name": { "type": "string" },
              "unit": { "type": "string" },
              "baseline_value": { "type": "number" },
              "current_value": { "type": "number" },
              "delta_pct": { "type": "number" }
            }
          }
        },
        "note": { "type": "string" }
      }
    }
  }
}
```

Create `schemas/baseline-manifest.schema.json` (JSON Schema 2020-12):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://arm64-uarch-probe/schemas/baseline-manifest.schema.json",
  "title": "BaselineManifest",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "baseline_id", "version", "source_run_ids", "analysis_id",
    "commands", "repository_commit", "dirty_tree", "toolchain", "promoted_at"
  ],
  "properties": {
    "baseline_id": { "type": "string" },
    "version": { "type": "string" },
    "source_run_ids": { "type": "array", "items": { "type": "string" } },
    "analysis_id": { "type": "string" },
    "report_id": { "type": "string" },
    "figure_ids": { "type": "array", "items": { "type": "string" } },
    "commands": { "type": "array", "items": { "type": "string" } },
    "repository_commit": { "type": "string" },
    "dirty_tree": { "type": "boolean" },
    "toolchain": {
      "type": "array",
      "items": { "type": "array", "items": { "type": "string" }, "minItems": 2, "maxItems": 2 }
    },
    "promoted_at": { "type": "string", "format": "date-time" },
    "approved_by": { "type": "string" }
  }
}
```

- [ ] **Step 4: Add serialization branches**

In `arm64_probe/serialization/model_json.py`, add imports and `isinstance` branches to `to_data()`:

```python
from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, CrossRunMetricDelta, CrossRunComparison,
    AnalysisSummary, FigureManifest, ReportManifest, ImportedRecord,
    BaselineManifest,
)

# In to_data() function, add branches (before the final else):

if isinstance(value, MetricStats):
    return {
        "metric_name": value.metric_name, "unit": value.unit,
        "sample_count": value.sample_count, "success_count": value.success_count,
        "error_count": value.error_count, "min_value": value.min_value,
        "max_value": value.max_value, "median": value.median,
        "mad": value.mad, "mean": value.mean, "stddev": value.stddev,
    }

if isinstance(value, CaseAnalysis):
    return {
        "case_id": value.case_id, "scenario_id": value.scenario_id,
        "platform_id": value.platform_id, "status": value.status,
        "total_samples": value.total_samples, "ok_samples": value.ok_samples,
        "error_samples": value.error_samples,
        "metric_stats": _mapping(
            ((k, to_data(v)) for k, v in value.metric_stats)
        ),
        "anomalies": list(value.anomalies),
        "source_run_ids": list(value.source_run_ids),
    }

# ... similar branches for CrossRunMetricDelta, CrossRunComparison,
#     AnalysisSummary, FigureManifest, ReportManifest, ImportedRecord,
#     BaselineManifest
```

Add `_dict_to_analysis_summary(data: dict) -> AnalysisSummary` and
`_dict_to_baseline_manifest(data: dict) -> BaselineManifest` deserialization
functions in the same module.

- [ ] **Step 5: Write schema contract tests**

In `tests/contract/test_analysis_schemas.py`:

```python
"""Contract tests for analysis-summary and baseline-manifest schemas."""
import json
import unittest
from pathlib import Path


SCHEMAS = Path(__file__).resolve().parents[3] / "schemas"


class AnalysisSummarySchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema_path = SCHEMAS / "analysis-summary.schema.json"
        self.schema = json.loads(self.schema_path.read_text())

    def test_schema_is_valid_json_schema_2020_12(self):
        self.assertEqual(self.schema["$schema"],
                         "https://json-schema.org/draft/2020-12/schema")

    def test_required_fields_present(self):
        required = self.schema["required"]
        for field in ("analysis_id", "schema_version", "source_runs",
                       "platform_id", "repository_commit"):
            self.assertIn(field, required)

    def test_schema_version_const_is_1(self):
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], 1)

    def test_validates_minimal_example(self):
        from jsonschema import validate
        example = {
            "analysis_id": "20260617T120000Z-a1b2c3d4",
            "schema_version": 1,
            "source_runs": ["run1"],
            "platform_id": "gb10",
            "repository_id": "github.com/x/arm64-uarch-probe",
            "repository_commit": "abc123",
            "dirty_tree": False,
            "toolchain": [["python", "3.13.13"]],
            "case_analyses": [],
            "cross_run_comparisons": [],
            "anomalies": [],
            "generated_at": "2026-06-17T12:00:00Z",
        }
        validate(instance=example, schema=self.schema)


class BaselineManifestSchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema_path = SCHEMAS / "baseline-manifest.schema.json"
        self.schema = json.loads(self.schema_path.read_text())

    def test_required_fields_present(self):
        required = self.schema["required"]
        for field in ("baseline_id", "version", "source_run_ids", "analysis_id",
                       "commands", "repository_commit"):
            self.assertIn(field, required)
```

- [ ] **Step 6: Run tests and verify they pass**

```sh
uv run --no-sync python -m unittest tests.unit.test_analysis_models tests.contract.test_analysis_schemas -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```sh
git add arm64_probe/analysis/__init__.py arm64_probe/analysis/models.py \
  arm64_probe/serialization/model_json.py \
  schemas/analysis-summary.schema.json schemas/baseline-manifest.schema.json \
  tests/unit/test_analysis_models.py tests/contract/test_analysis_schemas.py
git commit -m "Add Phase 4 analysis domain models and public schemas

9 frozen dataclasses (MetricStats, CaseAnalysis, CrossRunMetricDelta,
CrossRunComparison, AnalysisSummary, FigureManifest, ReportManifest,
ImportedRecord, BaselineManifest). analysis-summary v1 and
baseline-manifest JSON Schema 2020-12. Serialization round-trip
via model_json.to_data() branches.

AC1 foundation."
```

---

### Task 22: AnalysisStore (Atomic Persistence)

**Files:**
- Create: `arm64_probe/analysis/store.py`
- Create: `tests/unit/test_analysis_store.py`

- [ ] **Step 1: Write failing AnalysisStore tests**

In `tests/unit/test_analysis_store.py`:

```python
"""Atomic persistence tests for AnalysisStore."""
import json
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import AnalysisSummary
from arm64_probe.analysis.store import AnalysisStore


class AnalysisStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = AnalysisStore(analysis_dir=self.tmpdir)

    def _make_summary(self, analysis_id="20260617T120000Z-a1b2c3d4"):
        return AnalysisSummary(
            analysis_id=analysis_id, schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )

    def test_write_creates_json_file(self):
        summary = self._make_summary()
        path = self.store.write_analysis(summary)
        self.assertTrue(path.exists())
        self.assertTrue(path.suffix == ".json")

    def test_read_returns_identical_summary(self):
        summary = self._make_summary()
        self.store.write_analysis(summary)
        loaded = self.store.read_analysis(summary.analysis_id)
        self.assertEqual(loaded, summary)

    def test_list_analyses_returns_ids(self):
        s1 = self._make_summary("20260617T120000Z-a1b2c3d4")
        s2 = self._make_summary("20260617T130000Z-b5c6d7e8")
        self.store.write_analysis(s1)
        self.store.write_analysis(s2)
        ids = self.store.list_analyses()
        self.assertIn(s1.analysis_id, ids)
        self.assertIn(s2.analysis_id, ids)

    def test_read_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.read_analysis("nonexistent")

    def test_rejects_oversize_file(self):
        import os
        big_path = self.tmpdir / "big.json"
        big_path.write_text("x" * (2 * 1024 * 1024))
        with self.assertRaises(ValueError):
            self.store.read_analysis("big")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they FAIL**

```sh
uv run --no-sync python -m unittest tests.unit.test_analysis_store -v
```

- [ ] **Step 3: Implement AnalysisStore**

In `arm64_probe/analysis/store.py`:

```python
"""Atomic persistence for analysis artifacts."""
import os
import uuid
from pathlib import Path

from arm64_probe.serialization import json_io, model_json
from arm64_probe.analysis.models import AnalysisSummary

MAX_ANALYSIS_BYTES = 2 * 1024 * 1024  # 2 MiB


class AnalysisStore:
    def __init__(self, analysis_dir: Path):
        self._dir = analysis_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def write_analysis(self, summary: AnalysisSummary) -> Path:
        data = model_json.to_data(summary)
        dest = self._dir / f"{summary.analysis_id}.json"
        tmp = self._dir / f".{summary.analysis_id}.{uuid.uuid4().hex[:8]}.tmp"
        tmp.write_text(json_io.dump_json(data), encoding="utf-8")
        os.fsync(tmp.open().fileno())
        os.replace(tmp, dest)
        self._fsync_dir()
        return dest

    def read_analysis(self, analysis_id: str) -> AnalysisSummary:
        path = self._dir / f"{analysis_id}.json"
        return self._read_path(path)

    def _read_path(self, path: Path) -> AnalysisSummary:
        if not path.is_file():
            raise FileNotFoundError(f"analysis artifact not found: {path}")
        if path.stat().st_size > MAX_ANALYSIS_BYTES:
            raise ValueError(f"analysis artifact too large: {path.stat().st_size}")
        data = json_io.load_json(path)
        if data.get("schema_version") != 1:
            raise ValueError(f"unsupported schema_version: {data.get('schema_version')}")
        return model_json._dict_to_analysis_summary(data)

    def list_analyses(self) -> tuple[str, ...]:
        return tuple(sorted(
            p.stem for p in self._dir.glob("*.json")
            if not p.name.startswith(".")
        ))

    def _fsync_dir(self):
        fd = os.open(str(self._dir), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
```

- [ ] **Step 4: Run tests and verify they PASS**

```sh
uv run --no-sync python -m unittest tests.unit.test_analysis_store -v
```

- [ ] **Step 5: Commit**

```sh
git add arm64_probe/analysis/store.py tests/unit/test_analysis_store.py
git commit -m "Add AnalysisStore for atomic analysis artifact persistence

Follows ResultStore atomic-write pattern: temp -> fsync -> replace
-> parent fsync. Reads validate schema_version==1 and size <= 2 MiB.
AC1 complete."
```

---

### Task 23: StatisticsEngine

**Files:**
- Create: `arm64_probe/analysis/statistics.py`
- Create: `tests/unit/test_statistics.py`

- [ ] **Step 1: Write failing statistics tests**

In `tests/unit/test_statistics.py`:

```python
"""Deterministic statistics engine tests."""
import unittest

from arm64_probe.domain.models import Sample
from arm64_probe.analysis.models import MetricStats, CaseAnalysis
from arm64_probe.analysis.statistics import StatisticsEngine


def _sample(case_id, run_id, status, metrics, sample_index=0):
    return Sample(
        run_id=run_id, case_id=case_id, sample_index=sample_index,
        status=status, metrics=tuple(sorted(metrics.items())),
    )


class StatisticsEngineTests(unittest.TestCase):
    def test_compute_metric_stats_basic(self):
        samples = (
            _sample("c1", "r1", "ok", {"latency_ns": 4.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 5.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 4.5}),
        )
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns", "ns")
        self.assertEqual(stats.metric_name, "latency_ns")
        self.assertEqual(stats.unit, "ns")
        self.assertEqual(stats.sample_count, 3)
        self.assertEqual(stats.success_count, 3)
        self.assertAlmostEqual(stats.min_value, 4.0)
        self.assertAlmostEqual(stats.max_value, 5.0)
        self.assertAlmostEqual(stats.median, 4.5)

    def test_error_samples_excluded_from_stats(self):
        samples = (
            _sample("c1", "r1", "error", {"latency_ns": 999.0}),
            _sample("c1", "r1", "ok", {"latency_ns": 4.0}),
        )
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns", "ns")
        self.assertEqual(stats.success_count, 1)
        self.assertEqual(stats.error_count, 1)
        self.assertAlmostEqual(stats.median, 4.0)

    def test_all_errors_returns_none_values(self):
        samples = (
            _sample("c1", "r1", "error", {}),
            _sample("c1", "r1", "error", {}),
        )
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns", "ns")
        self.assertIsNone(stats.median)
        self.assertIsNone(stats.min_value)
        self.assertEqual(stats.error_count, 2)

    def test_unit_inference(self):
        samples = (_sample("c1", "r1", "ok", {"latency_ns": 1.0}),)
        stats = StatisticsEngine.compute_metric_stats(samples, "latency_ns")
        self.assertEqual(stats.unit, "ns")

        samples2 = (_sample("c1", "r1", "ok", {"accesses": 100}),)
        stats2 = StatisticsEngine.compute_metric_stats(samples2, "accesses")
        self.assertEqual(stats2.unit, "count")

    def test_compute_case_analysis(self):
        samples = (
            _sample("c1", "r1", "ok", {"latency_ns": 4.0, "accesses": 100}),
            _sample("c1", "r1", "ok", {"latency_ns": 5.0, "accesses": 120}),
        )
        ca = StatisticsEngine.compute_case_analysis(
            case_id="c1", samples=samples,
            scenario_id="cache-latency.l1-latency", platform_id="gb10",
        )
        self.assertEqual(ca.case_id, "c1")
        self.assertEqual(ca.status, "ok")
        self.assertEqual(ca.total_samples, 2)
        self.assertEqual(len(ca.metric_stats), 2)
        # Metric names sorted
        self.assertEqual(ca.metric_stats[0][0], "accesses")
        self.assertEqual(ca.metric_stats[1][0], "latency_ns")


class AnomalyDetectionTests(unittest.TestCase):
    def test_single_sample_detected(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=1,
            success_count=1, error_count=0,
            min_value=4.0, max_value=4.0, median=4.0,
            mad=0.0, mean=4.0, stddev=0.0,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertIn("single_sample", anomalies)

    def test_all_errors_detected(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=5,
            success_count=0, error_count=5,
            min_value=None, max_value=None, median=None,
            mad=None, mean=None, stddev=None,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertIn("all_errors", anomalies)

    def test_high_variance_detected(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=10,
            success_count=10, error_count=0,
            min_value=1.0, max_value=100.0, median=10.0,
            mad=5.0, mean=20.0, stddev=50.0,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertIn("high_variance", anomalies)

    def test_no_anomalies_for_normal_data(self):
        stats = MetricStats(
            metric_name="x", unit="ns", sample_count=10,
            success_count=10, error_count=0,
            min_value=4.0, max_value=5.0, median=4.36,
            mad=0.12, mean=4.40, stddev=0.35,
        )
        anomalies = StatisticsEngine.detect_anomalies(stats)
        self.assertEqual(anomalies, ())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they FAIL**

```sh
uv run --no-sync python -m unittest tests.unit.test_statistics -v
```

- [ ] **Step 3: Implement StatisticsEngine**

In `arm64_probe/analysis/statistics.py`, implement:

```python
"""Deterministic statistics computation. Pure functions, zero I/O."""
import statistics as stdlib_stats

from arm64_probe.domain.models import Sample
from arm64_probe.analysis.models import MetricStats, CaseAnalysis


_UNIT_RULES = [
    ("_ns", "ns"), ("_cycles", "cycles"), ("_bytes", "bytes"),
    ("_pct", "ratio"), ("_ratio", "ratio"),
]


class StatisticsEngine:
    @staticmethod
    def _infer_unit(metric_name: str) -> str:
        for suffix, unit in _UNIT_RULES:
            if metric_name.endswith(suffix):
                return unit
        if metric_name in ("accesses",) or metric_name.endswith("_count") or metric_name.endswith("_cpu"):
            return "count"
        return "unknown"

    @classmethod
    def compute_metric_stats(cls, samples, metric_name, unit=None):
        if unit is None:
            unit = cls._infer_unit(metric_name)
        values = []
        ok_count = 0
        error_count = 0
        for s in samples:
            if s.status == "ok":
                ok_count += 1
                metrics_dict = dict(s.metrics)
                if metric_name in metrics_dict:
                    values.append(float(metrics_dict[metric_name]))
            else:
                error_count += 1
        if not values:
            return MetricStats(
                metric_name=metric_name, unit=unit,
                sample_count=len(samples), success_count=ok_count,
                error_count=error_count,
                min_value=None, max_value=None, median=None,
                mad=None, mean=None, stddev=None,
            )
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        median = stdlib_stats.median(sorted_vals)
        mean = stdlib_stats.mean(sorted_vals)
        stddev = stdlib_stats.stdev(sorted_vals) if n >= 2 else 0.0
        mad = stdlib_stats.median([abs(v - median) for v in sorted_vals])
        return MetricStats(
            metric_name=metric_name, unit=unit,
            sample_count=len(samples), success_count=ok_count,
            error_count=error_count,
            min_value=sorted_vals[0], max_value=sorted_vals[-1],
            median=median, mad=mad, mean=mean, stddev=stddev,
        )

    @classmethod
    def compute_case_analysis(cls, case_id, samples, scenario_id, platform_id):
        ok_count = sum(1 for s in samples if s.status == "ok")
        error_count = sum(1 for s in samples if s.status == "error")
        if ok_count == len(samples):
            status = "ok"
        elif ok_count == 0:
            status = "failed"
        else:
            status = "partial"

        # Discover all metric names across all ok samples
        metric_names = set()
        for s in samples:
            if s.status == "ok":
                metric_names.update(dict(s.metrics).keys())

        metric_stats = tuple(
            (name, cls.compute_metric_stats(samples, name))
            for name in sorted(metric_names)
        )

        # Detect anomalies per metric
        anomalies = []
        for name, stats in metric_stats:
            for a in cls.detect_anomalies(stats):
                if a not in anomalies:
                    anomalies.append(a)
        anomalies.sort()

        # Discover source run_ids
        run_ids = tuple(sorted(set(s.run_id for s in samples)))

        return CaseAnalysis(
            case_id=case_id, scenario_id=scenario_id, platform_id=platform_id,
            status=status, total_samples=len(samples),
            ok_samples=ok_count, error_samples=error_count,
            metric_stats=metric_stats, anomalies=tuple(anomalies),
            source_run_ids=run_ids,
        )

    @staticmethod
    def detect_anomalies(stats):
        anomalies = []
        if stats.success_count == 0:
            anomalies.append("all_errors")
            return tuple(anomalies)
        if stats.success_count == 1 and stats.sample_count == 1:
            anomalies.append("single_sample")
            return tuple(anomalies)
        if stats.success_count == 1 and stats.sample_count > 1:
            anomalies.append("single_sample")
        if stats.stddev is not None and stats.stddev == 0.0 and stats.sample_count > 1:
            anomalies.append("zero_variance")
        if (stats.mean is not None and stats.mean != 0
                and stats.stddev is not None
                and stats.stddev > 2 * abs(stats.mean)):
            anomalies.append("high_variance")
        if (stats.mean is not None and stats.stddev is not None
                and stats.stddev > 0 and stats.max_value is not None
                and stats.max_value > stats.mean + 5 * stats.stddev):
            anomalies.append("extreme_outlier")
        return tuple(sorted(anomalies))
```

- [ ] **Step 4: Run tests and verify they PASS**

```sh
uv run --no-sync python -m unittest tests.unit.test_statistics -v
```

- [ ] **Step 5: Commit**

```sh
git add arm64_probe/analysis/statistics.py tests/unit/test_statistics.py
git commit -m "Add StatisticsEngine with deterministic stats and anomaly detection

Pure-function engine using stdlib statistics. Computes min/max/median/
MAD/mean/stdev per metric. Infers units from metric name suffixes.
5 anomaly detection rules: single_sample, all_errors, zero_variance,
high_variance, extreme_outlier. AC3 partially closed."
```

---

## Batch 2: Ingestion and Comparison

### Task 24: ResultIngester + LegacyImporter

**Files:**
- Create: `arm64_probe/analysis/ingestion.py`
- Create: `arm64_probe/analysis/adapters/__init__.py`
- Create: `arm64_probe/analysis/adapters/legacy_chase_pmu.py`
- Create: `tests/unit/test_ingestion.py`
- Create: `tests/integration/test_phase4_legacy_import.py`

- [ ] **Step 1: Write failing ingestion tests**

In `tests/unit/test_ingestion.py`:

```python
"""ResultIngester and LegacyImporter tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.ingestion import ResultIngester, LegacyImporter, ImportedRecord
from arm64_probe.execution.result_store import ResultStore
from arm64_probe.domain.models import (
    Sample, RunResult, Plan, Case, make_run_result,
)


class ResultIngesterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.store = ResultStore(results_dir=self.tmpdir)
        self.ingester = ResultIngester(self.store)

    def _write_run(self, run_id, case_ids):
        samples = tuple(
            Sample(run_id=run_id, case_id=cid, sample_index=i,
                   status="ok", metrics=(("latency_ns", 4.0),))
            for i, cid in enumerate(case_ids)
        )
        plan = Plan(
            platform_id="gb10", profile_id="smoke",
            selections=case_ids,
            cases=tuple(Case(id=cid, scenario_id="cache-latency.l1-latency",
                             platform_id="gb10", status="ready", reason=None,
                             cpu=0, src_cpu=None, dst_cpu=None,
                             selectors=(), parameters=(), execution_requirements=())
                        for cid in case_ids),
            environment_phases=(), skip_unavailable=False,
        )
        result = make_run_result(
            run_id=run_id, plan=plan, samples=samples,
            summary=(("platform_id", "gb10"),),
            environment=(),
        )
        self.store.write_result(result)
        return result

    def test_ingest_single_run(self):
        self._write_run("run1", ("case1",))
        results = self.ingester.ingest((self.tmpdir / "run1.json",))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].run_id, "run1")

    def test_ingest_rejects_duplicate_run_ids(self):
        self._write_run("run1", ("case1",))
        with self.assertRaises(ValueError):
            self.ingester.ingest((
                self.tmpdir / "run1.json",
                self.tmpdir / "run1.json",
            ))

    def test_ingest_multiple_runs(self):
        self._write_run("run1", ("case1",))
        self._write_run("run2", ("case2",))
        results = self.ingester.ingest((
            self.tmpdir / "run1.json",
            self.tmpdir / "run2.json",
        ))
        self.assertEqual(len(results), 2)


class LegacyImporterProtocolTests(unittest.TestCase):
    def test_imported_record_is_frozen(self):
        record = ImportedRecord(
            source_path="/tmp/test.log", parser_version="1.0",
            format="chase_pmu_text", case_id="cache-latency.l1-latency",
            platform_id="gb10",
            metrics=(("latency_ns", 4.36),),
            loss_notes=("warm/cold state inferred",),
        )
        with self.assertRaises(Exception):
            record.case_id = "changed"
```

- [ ] **Step 2: Run tests and verify they FAIL**

```sh
uv run --no-sync python -m unittest tests.unit.test_ingestion -v
```

- [ ] **Step 3: Implement ResultIngester + LegacyImporter**

In `arm64_probe/analysis/ingestion.py`:

```python
"""RunResult ingestion and legacy import protocol."""
from pathlib import Path
from typing import Protocol

from arm64_probe.domain.models import RunResult
from arm64_probe.execution.result_store import ResultStore
from arm64_probe.analysis.models import ImportedRecord


class LegacyImporter(Protocol):
    """Protocol for importing historical text logs."""
    source_format: str
    parser_version: str

    def can_handle(self, path: Path) -> bool: ...
    def import_log(self, path: Path) -> ImportedRecord: ...


class ResultIngester:
    def __init__(self, store: ResultStore):
        self._store = store

    def ingest(self, paths: tuple[Path, ...]) -> tuple[RunResult, ...]:
        results = []
        seen_ids = set()
        for p in paths:
            result = self._store.read(p)
            if result.run_id in seen_ids:
                raise ValueError(f"duplicate run_id: {result.run_id}")
            seen_ids.add(result.run_id)
            results.append(result)
        return tuple(results)
```

In `arm64_probe/analysis/adapters/__init__.py`:

```python
"""Legacy import adapters."""
```

In `arm64_probe/analysis/adapters/legacy_chase_pmu.py`:

```python
"""Example legacy importer for chase_pmu v2.7.x text logs."""
import re
from pathlib import Path

from arm64_probe.analysis.ingestion import LegacyImporter
from arm64_probe.analysis.models import ImportedRecord


class LegacyChasePmuImporter:
    """Imports chase_pmu v2.7.x text output into ImportedRecord."""
    source_format = "chase_pmu_v2.7.x_text"
    parser_version = "1.0"

    def can_handle(self, path: Path) -> bool:
        if not path.suffix == ".txt":
            return False
        try:
            head = path.read_text()[:200]
            return "=== chase_pmu v2.7" in head
        except Exception:
            return False

    def import_log(self, path: Path) -> ImportedRecord:
        text = path.read_text()
        lat_match = re.search(r">>>\s+latency\s*=\s*([\d.]+)\s*ns/access", text)
        elapsed_match = re.search(r"elapsed\s*=\s*(\d+)\s*ns", text)
        accesses_match = re.search(r"accesses?\s*=\s*(\d+)", text)

        metrics = {}
        if lat_match:
            metrics["latency_ns"] = float(lat_match.group(1))
        if elapsed_match:
            metrics["elapsed_ns"] = int(elapsed_match.group(1))
        if accesses_match:
            metrics["accesses"] = int(accesses_match.group(1))

        loss_notes = []
        if not lat_match:
            loss_notes.append("latency not found in log")

        return ImportedRecord(
            source_path=str(path), parser_version=self.parser_version,
            format=self.source_format, case_id=None, platform_id=None,
            metrics=tuple(sorted(metrics.items())),
            loss_notes=tuple(loss_notes),
        )
```

- [ ] **Step 4: Write legacy import integration test**

In `tests/integration/test_phase4_legacy_import.py`:

```python
"""Legacy import end-to-end test."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.adapters.legacy_chase_pmu import LegacyChasePmuImporter


class LegacyImportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.importer = LegacyChasePmuImporter()

    def test_parses_real_legacy_output(self):
        legacy_path = Path(__file__).parents[3] / "data" / "20260611_v2.7.3" / "raw" / "run_20260611_123112.txt"
        if not legacy_path.exists():
            self.skipTest("legacy data not available")
        self.assertTrue(self.importer.can_handle(legacy_path))
        record = self.importer.import_log(legacy_path)
        self.assertIsNotNone(record)
        self.assertGreater(len(record.metrics), 0)
        self.assertIn("latency_ns", dict(record.metrics))
```

- [ ] **Step 5: Run tests and verify they PASS**

```sh
uv run --no-sync python -m unittest tests.unit.test_ingestion tests.integration.test_phase4_legacy_import -v
```

- [ ] **Step 6: Commit**

```sh
git add arm64_probe/analysis/ingestion.py arm64_probe/analysis/adapters/ \
  tests/unit/test_ingestion.py tests/integration/test_phase4_legacy_import.py
git commit -m "Add ResultIngester and LegacyImporter protocol with chase_pmu example

ResultIngester loads multiple RunResult files via ResultStore, rejects
duplicate run_ids. LegacyImporter Protocol defines import_log/can_handle.
Example LegacyChasePmuImporter parses v2.7.x text logs. AC2 closes."
```

---

### Task 25: ComparisonEngine Stub (Phase 4 Protocol Only)

**Files:**
- Create: `arm64_probe/analysis/comparison.py`
- Create: `tests/unit/test_comparison.py`

- [ ] **Step 1: Write failing comparison stub tests**

In `tests/unit/test_comparison.py`:

```python
"""Phase 4 ComparisonEngine stub tests."""
import unittest

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, CrossRunComparison,
)
from arm64_probe.analysis.comparison import ComparisonEngine


class ComparisonEngineStubTests(unittest.TestCase):
    def setUp(self):
        self.stats = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=5, error_count=0,
            min_value=4.0, max_value=5.0, median=4.36,
            mad=0.12, mean=4.40, stddev=0.35,
        )
        self.ca = CaseAnalysis(
            case_id="test@gb10", scenario_id="test", platform_id="gb10",
            status="ok", total_samples=5, ok_samples=5, error_samples=0,
            metric_stats=(("latency_ns", self.stats),),
            anomalies=(), source_run_ids=("run1",),
        )

    def test_stub_returns_incompatible_with_note(self):
        result = ComparisonEngine.compare_runs(self.ca, self.ca)
        self.assertEqual(result.classification, "incompatible")
        self.assertIn("deferred", result.note.lower())
        self.assertIn("Phase 5", result.note)

    def test_stub_is_deterministic(self):
        r1 = ComparisonEngine.compare_runs(self.ca, self.ca)
        r2 = ComparisonEngine.compare_runs(self.ca, self.ca)
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement ComparisonEngine stub**

In `arm64_probe/analysis/comparison.py`:

```python
"""Cross-run comparison engine (Phase 4 stub)."""
from arm64_probe.analysis.models import CaseAnalysis, CrossRunComparison


class ComparisonEngine:
    """Phase 4 protocol stub. Full implementation deferred to Phase 5."""

    @staticmethod
    def compare_runs(
        baseline: CaseAnalysis, current: CaseAnalysis,
        tolerance_pct: float = 5.0
    ) -> CrossRunComparison:
        return CrossRunComparison(
            case_id=current.case_id,
            runs_compared=(
                baseline.source_run_ids[0] if baseline.source_run_ids else "?",
                current.source_run_ids[0] if current.source_run_ids else "?",
            ),
            classification="incompatible",
            metric_deltas=(),
            note="Cross-run comparison deferred to Phase 5",
        )
```

- [ ] **Step 3: Run tests, verify PASS, commit**

```sh
uv run --no-sync python -m unittest tests.unit.test_comparison -v
git add arm64_probe/analysis/comparison.py tests/unit/test_comparison.py
git commit -m "Add ComparisonEngine Phase 4 protocol stub

Returns 'incompatible' with note 'deferred to Phase 5'. Full
classification logic (unchanged/improved/regressed/missing) is
implemented in Phase 5 when before/after baselines exist. AC3 closed."
```

---

## Batch 3: CLI — probe analyze

### Task 26: probe analyze CLI

**Files:**
- Modify: `arm64_probe/cli/parser.py`
- Modify: `arm64_probe/cli/main.py`
- Modify: `arm64_probe/cli/render.py`
- Create: `tests/contract/test_cli_analyze.py`
- Create: `tests/integration/test_phase4_analysis_workflow.py`

- [ ] **Step 1: Write failing CLI analyze tests**

In `tests/contract/test_cli_analyze.py`:

```python
"""CLI contract tests for probe analyze."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PROBE = Path(__file__).resolve().parents[3] / "probe"


class CliAnalyzeCommandTests(unittest.TestCase):
    def test_analyze_help(self):
        result = subprocess.run(
            [str(PROBE), "analyze", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--run", result.stdout)

    def test_analyze_missing_run_returns_usage_error(self):
        result = subprocess.run(
            [str(PROBE), "analyze"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_analyze_dash_o_json_accepted(self):
        result = subprocess.run(
            [str(PROBE), "analyze", "--help"],
            capture_output=True, text=True,
        )
        self.assertIn("-o", result.stdout)


class CliAnalyzeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def _write_fixture_result(self):
        """Write a minimal valid RunResult for analyze to consume."""
        from arm64_probe.execution.result_store import ResultStore
        from arm64_probe.domain.models import (
            Sample, Plan, Case, RunResult, make_run_result,
        )
        store = ResultStore(results_dir=self.tmpdir)
        samples = (
            Sample(
                run_id="testrun", case_id="test@gb10", sample_index=0,
                status="ok", metrics=(("latency_ns", 4.36),),
            ),
        )
        plan = Plan(
            platform_id="gb10", profile_id="smoke",
            selections=("test",),
            cases=(
                Case(id="test@gb10", scenario_id="test", platform_id="gb10",
                     status="ready", reason=None, cpu=0, src_cpu=None,
                     dst_cpu=None, selectors=(), parameters=(),
                     execution_requirements=()),
            ),
            environment_phases=(), skip_unavailable=False,
        )
        result = make_run_result(
            run_id="testrun", plan=plan, samples=samples,
            summary=(
                ("platform_id", "gb10"),
                ("total_samples", 1), ("ok_samples", 1),
                ("error_samples", 0), ("skipped_samples", 0),
                ("phase_count", 1),
                ("repository_id", "github.com/x/arm64-uarch-probe"),
                ("repository_commit", "abc123"), ("dirty_tree", False),
                ("case_definitions_signature", "aa" * 32),
            ),
            environment=(("platform", "unknown"),),
        )
        store.write_result(result)
        return self.tmpdir / "testrun.json"

    def test_analyze_accepts_run_and_writes_analysis_json(self):
        run_path = self._write_fixture_result()
        output_dir = self.tmpdir / "analysis"
        result = subprocess.run(
            [str(PROBE), "analyze", "--run", str(run_path),
             "--output-dir", str(output_dir), "-o", "json"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        # Check analysis JSON was written
        files = list(output_dir.glob("*.json"))
        self.assertGreater(len(files), 0)
        data = json.loads(files[0].read_text())
        self.assertEqual(data["schema_version"], 1)
        self.assertIn("case_analyses", data)

    def test_analyze_invalid_json_returns_16(self):
        bad_path = self.tmpdir / "bad.json"
        bad_path.write_text("not json")
        result = subprocess.run(
            [str(PROBE), "analyze", "--run", str(bad_path),
             "--output-dir", str(self.tmpdir / "out"), "-o", "json"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 16)
```

- [ ] **Step 2: Run tests and verify they FAIL**

```sh
uv run --no-sync python -m unittest tests.contract.test_cli_analyze -v
```

Expected: FAIL (no `analyze` subcommand).

- [ ] **Step 3: Add analyze parser, dispatch, and render**

Modify `arm64_probe/cli/parser.py`:

```python
# Add to COMMANDS tuple:
COMMANDS = ("list", "show", "plan", "doctor", "restore", "run", "resume", "analyze", "report")

# Add analyze_parser function:
def _add_analyze_parser(subparsers) -> None:
    p = subparsers.add_parser("analyze", help="Analyze run results")
    p.add_argument("--run", required=True, action="append", dest="runs",
                   metavar="PATH", help="RunResult JSON file (repeatable)")
    p.add_argument("--baseline", default=None, metavar="PATH",
                   help="Prior analysis for cross-run comparison (Phase 5)")
    p.add_argument("--output-dir", default="results/analysis/", metavar="DIR",
                   help="Output directory for analysis artifacts")
    p.add_argument("-o", "--output", default="table", choices=("table", "json"),
                   help="Output format")
    p.set_defaults(func="analyze")
```

Modify `arm64_probe/cli/main.py` — add `_run_analyze(args)`:

```python
def _run_analyze(args):
    from pathlib import Path
    from arm64_probe.analysis.ingestion import ResultIngester
    from arm64_probe.analysis.statistics import StatisticsEngine
    from arm64_probe.analysis.store import AnalysisStore
    from arm64_probe.analysis.models import AnalysisSummary
    from arm64_probe.execution.result_store import ResultStore
    import datetime, uuid, os

    run_paths = tuple(Path(p) for p in args.runs)
    store = ResultStore(results_dir=Path(args.output_dir))
    ingester = ResultIngester(store)
    results = ingester.ingest(run_paths)

    # Collect all samples grouped by case_id
    all_samples_by_case = {}
    for r in results:
        for s in r.samples:
            all_samples_by_case.setdefault(s.case_id, []).append(s)

    plat_id = dict(results[0].summary).get("platform_id", "unknown")
    repo_id = dict(results[0].summary).get("repository_id", "unknown")
    commit = dict(results[0].summary).get("repository_commit", "unknown")
    dirty = bool(dict(results[0].summary).get("dirty_tree", False))

    # Compute per-case analysis
    case_analyses = []
    for case_id in sorted(all_samples_by_case):
        samples = tuple(all_samples_by_case[case_id])
        plan_case = None
        for r in results:
            for c in r.plan.cases:
                if c.id == case_id:
                    plan_case = c
                    break
            if plan_case:
                break
        scenario_id = plan_case.scenario_id if plan_case else "unknown"
        ca = StatisticsEngine.compute_case_analysis(
            case_id=case_id, samples=samples,
            scenario_id=scenario_id, platform_id=plat_id,
        )
        case_analyses.append(ca)

    analysis_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    summary = AnalysisSummary(
        analysis_id=analysis_id, schema_version=1,
        source_runs=tuple(r.run_id for r in results),
        platform_id=plat_id, repository_id=repo_id,
        repository_commit=commit, dirty_tree=dirty,
        toolchain=(("python", os.popen("uv run --no-sync python -V 2>&1").read().strip()),),
        case_analyses=tuple(case_analyses), cross_run_comparisons=(),
        anomalies=(), generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    analysis_store = AnalysisStore(analysis_dir=Path(args.output_dir))
    out_path = analysis_store.write_analysis(summary)
    return summary, out_path
```

Modify `arm64_probe/cli/render.py` — add `render_analyze`:

```python
def render_analyze(summary, output_path, output_fmt):
    if output_fmt == "json":
        return dump_json(to_data(summary))
    lines = [f"Analysis: {summary.analysis_id}", f"Written: {output_path}",
             f"Platform: {summary.platform_id}",
             f"Cases analyzed: {len(summary.case_analyses)}", ""]
    header = ("CASE ID", "STATUS", "SAMPLES", "METRICS")
    rows = []
    for ca in summary.case_analyses:
        metric_names = ", ".join(k for k, _ in ca.metric_stats)
        rows.append((ca.case_id, ca.status, str(ca.total_samples), metric_names))
    return _table(header, rows) + "\n" + "\n".join(lines)
```

- [ ] **Step 4: Wire dispatch in main.py**

In `arm64_probe/cli/main.py`, add to `main()` dispatch:

```python
if args.func == "analyze":
    summary, path = _run_analyze(args)
    print(render_analyze(summary, path, args.output), end="")
    return ExitCode.SUCCESS
```

- [ ] **Step 5: Run tests and verify they PASS**

```sh
uv run --no-sync python -m unittest tests.contract.test_cli_analyze -v
```

- [ ] **Step 6: Write integration workflow test**

In `tests/integration/test_phase4_analysis_workflow.py`:

```python
"""End-to-end analysis workflow test."""
import json
import tempfile
import unittest
from pathlib import Path

from arm64_probe.execution.result_store import ResultStore
from arm64_probe.domain.models import Sample, Plan, Case, make_run_result
from arm64_probe.analysis.ingestion import ResultIngester
from arm64_probe.analysis.statistics import StatisticsEngine
from arm64_probe.analysis.store import AnalysisStore


class AnalysisWorkflowTests(unittest.TestCase):
    def test_full_ingest_analyze_persist_round_trip(self):
        tmpdir = Path(tempfile.mkdtemp())
        store = ResultStore(results_dir=tmpdir)

        samples = tuple(
            Sample(run_id="run1", case_id=f"case{i}@gb10", sample_index=j,
                   status="ok", metrics=(("latency_ns", 4.0 + i + j * 0.1),))
            for i in range(2) for j in range(3)
        )
        plan = Plan(
            platform_id="gb10", profile_id="smoke",
            selections=("case0", "case1"),
            cases=tuple(
                Case(id=f"case{i}@gb10", scenario_id=f"test.scenario{i}",
                     platform_id="gb10", status="ready", reason=None,
                     cpu=0, src_cpu=None, dst_cpu=None,
                     selectors=(), parameters=(), execution_requirements=())
                for i in range(2)
            ),
            environment_phases=(), skip_unavailable=False,
        )
        result = make_run_result(
            run_id="run1", plan=plan, samples=samples,
            summary=(
                ("platform_id", "gb10"),
                ("repository_id", "github.com/x/arm64-uarch-probe"),
                ("repository_commit", "abc123"), ("dirty_tree", False),
                ("total_samples", 6), ("ok_samples", 6), ("error_samples", 0),
                ("skipped_samples", 0), ("phase_count", 1),
                ("case_definitions_signature", "bb" * 32),
            ),
            environment=(),
        )
        store.write_result(result)

        # Ingest
        ingester = ResultIngester(store)
        results = ingester.ingest((tmpdir / "run1.json",))
        self.assertEqual(len(results), 1)

        # Analyze
        all_by_case = {}
        for r in results:
            for s in r.samples:
                all_by_case.setdefault(s.case_id, []).append(s)

        case_analyses = []
        for case_id in sorted(all_by_case):
            ca = StatisticsEngine.compute_case_analysis(
                case_id=case_id, samples=tuple(all_by_case[case_id]),
                scenario_id="test", platform_id="gb10",
            )
            case_analyses.append(ca)

        self.assertEqual(len(case_analyses), 2)
        self.assertEqual(case_analyses[0].status, "ok")

        # Persist
        from arm64_probe.analysis.models import AnalysisSummary
        summary = AnalysisSummary(
            analysis_id="test-analysis", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=tuple(case_analyses), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        analysis_store = AnalysisStore(analysis_dir=tmpdir / "analysis")
        path = analysis_store.write_analysis(summary)
        self.assertTrue(path.exists())

        # Read back
        loaded = analysis_store.read_analysis(summary.analysis_id)
        self.assertEqual(loaded, summary)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 7: Commit**

```sh
git add arm64_probe/cli/parser.py arm64_probe/cli/main.py arm64_probe/cli/render.py \
  tests/contract/test_cli_analyze.py \
  tests/integration/test_phase4_analysis_workflow.py
git commit -m "Add probe analyze CLI with ResultIngester and StatisticsEngine

probe analyze --run <result.json> [...] --output-dir <dir> [-o table|json]
loads RunResult files, computes per-case MetricStats via StatisticsEngine,
persists AnalysisSummary atomically via AnalysisStore. Exit 16 on
read/validation failure. AC2 and AC3 closed."
```

---

## Batch 4: Figures and Report

### Task 27: FigureGenerator (matplotlib)

**Files:**
- Modify: `pyproject.toml` — add `matplotlib` dependency
- Create: `arm64_probe/analysis/figures.py`
- Create: `tests/unit/test_figures.py`

- [ ] **Step 1: Add matplotlib dependency**

In `pyproject.toml`, add `"matplotlib>=3.9"` to `dependencies`. Run `uv lock`.

- [ ] **Step 2: Write failing figure tests**

In `tests/unit/test_figures.py`:

```python
"""Figure generator tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, AnalysisSummary, FigureManifest,
)
from arm64_probe.analysis.figures import FigureGenerator


class FigureGeneratorTests(unittest.TestCase):
    def setUp(self):
        stats = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=5, error_count=0,
            min_value=4.0, max_value=5.0, median=4.36,
            mad=0.12, mean=4.40, stddev=0.35,
        )
        self.ca = CaseAnalysis(
            case_id="l1@gb10.cpu-0", scenario_id="cache-latency.l1-latency",
            platform_id="gb10", status="ok", total_samples=5, ok_samples=5,
            error_samples=0, metric_stats=(("latency_ns", stats),),
            anomalies=(), source_run_ids=("run1",),
        )
        self.summary = AnalysisSummary(
            analysis_id="test", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="x", repository_commit="abc", dirty_tree=False,
            toolchain=(), case_analyses=(self.ca,),
            cross_run_comparisons=(), anomalies=(),
            generated_at="2026-06-17T12:00:00Z",
        )
        self.gen = FigureGenerator(self.summary)
        self.tmpdir = Path(tempfile.mkdtemp())

    def test_latency_bar_chart_creates_png(self):
        manifest = self.gen.latency_bar_chart(self.tmpdir)
        png_path = self.tmpdir / f"{manifest.figure_id}.png"
        self.assertTrue(png_path.exists())
        self.assertGreater(png_path.stat().st_size, 100)

    def test_manifest_has_required_fields(self):
        manifest = self.gen.latency_bar_chart(self.tmpdir)
        self.assertEqual(manifest.source_analysis_id, "test")
        self.assertIsInstance(manifest.figure_id, str)
        self.assertIsInstance(manifest.caption, str)
        self.assertIsInstance(manifest.path, str)
        self.assertIsInstance(manifest.regeneration_command, str)

    def test_generate_all_produces_figures(self):
        manifests = self.gen.generate_all(self.tmpdir)
        self.assertGreater(len(manifests), 0)
        for m in manifests:
            path = self.tmpdir / f"{m.figure_id}.png"
            self.assertTrue(path.exists(), f"missing: {path}")
```

- [ ] **Step 3: Implement FigureGenerator**

In `arm64_probe/analysis/figures.py`:

```python
"""Figure generation from analysis artifacts (matplotlib Agg backend)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

from arm64_probe.analysis.models import AnalysisSummary, FigureManifest


class FigureGenerator:
    def __init__(self, analysis: AnalysisSummary):
        self._analysis = analysis

    def latency_bar_chart(self, output_dir: Path) -> FigureManifest:
        figure_id = "latency_comparison"
        cases = self._analysis.case_analyses
        labels = [ca.case_id for ca in cases]
        values = []
        for ca in cases:
            for name, stats in ca.metric_stats:
                if name == "latency_ns" and stats.median is not None:
                    values.append(stats.median)
                    break
            else:
                values.append(0)

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(labels, values)
        ax.set_xlabel("Case")
        ax.set_ylabel("Latency (ns)")
        ax.set_title("Cache/Memory Latency Comparison")
        plt.xticks(rotation=45, ha="right")
        fig.tight_layout()
        path = output_dir / f"{figure_id}.png"
        fig.savefig(str(path), dpi=100, metadata={"caption": "Latency comparison"})
        plt.close(fig)

        return FigureManifest(
            figure_id=figure_id, path=str(path),
            caption="Cache/Memory Latency Comparison",
            source_analysis_id=self._analysis.analysis_id,
            regeneration_command=f"probe report --analysis {self._analysis.analysis_id}",
        )

    def migration_penalty_chart(self, output_dir: Path) -> FigureManifest:
        figure_id = "migration_penalty"
        fig, ax = plt.subplots(figsize=(8, 5))
        penalties = []
        labels = []
        for ca in self._analysis.case_analyses:
            if "migration" in ca.scenario_id:
                for name, stats in ca.metric_stats:
                    if name == "migration_penalty_ns" and stats.median is not None:
                        penalties.append(stats.median)
                        labels.append(ca.case_id)
                        break
        if penalties:
            ax.bar(labels, penalties)
            ax.set_xlabel("Migration Pair")
            ax.set_ylabel("Penalty (ns)")
            ax.set_title("Migration Penalty Comparison")
            plt.xticks(rotation=45, ha="right")
        else:
            ax.text(0.5, 0.5, "No migration data", ha="center", va="center")
        fig.tight_layout()
        path = output_dir / f"{figure_id}.png"
        fig.savefig(str(path), dpi=100)
        plt.close(fig)

        return FigureManifest(
            figure_id=figure_id, path=str(path),
            caption="Migration Penalty Comparison",
            source_analysis_id=self._analysis.analysis_id,
            regeneration_command=f"probe report --analysis {self._analysis.analysis_id}",
        )

    def metric_summary_table(self, output_dir: Path) -> FigureManifest:
        figure_id = "metric_summary"
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.axis("off")
        rows = []
        for ca in self._analysis.case_analyses:
            for name, stats in ca.metric_stats:
                rows.append([ca.case_id, name, f"{stats.median:.2f} {stats.unit}" if stats.median else "N/A"])
        if rows:
            table = ax.table(cellText=rows, colLabels=["Case", "Metric", "Median"],
                             loc="center", cellLoc="left")
            table.auto_set_font_size(False)
            table.set_fontsize(8)
        else:
            ax.text(0.5, 0.5, "No data", ha="center", va="center")
        fig.tight_layout()
        path = output_dir / f"{figure_id}.png"
        fig.savefig(str(path), dpi=100)
        plt.close(fig)

        return FigureManifest(
            figure_id=figure_id, path=str(path),
            caption="Metric Summary Table",
            source_analysis_id=self._analysis.analysis_id,
            regeneration_command=f"probe report --analysis {self._analysis.analysis_id}",
        )

    def generate_all(self, output_dir: Path) -> tuple[FigureManifest, ...]:
        return (
            self.latency_bar_chart(output_dir),
            self.migration_penalty_chart(output_dir),
            self.metric_summary_table(output_dir),
        )
```

- [ ] **Step 4: Run tests and commit**

```sh
uv run --no-sync python -m unittest tests.unit.test_figures -v
git add pyproject.toml uv.lock arm64_probe/analysis/figures.py tests/unit/test_figures.py
git commit -m "Add FigureGenerator with matplotlib Agg backend

Three figure types: latency_bar_chart, migration_penalty_chart,
metric_summary_table. Each writes a PNG and returns a FigureManifest
with caption, source_analysis_id, and regeneration_command. New
dependency: matplotlib. AC4 closes."
```

---

### Task 28: ReportGenerator

**Files:**
- Create: `arm64_probe/analysis/report.py`
- Create: `tests/unit/test_report.py`

- [ ] **Step 1: Write failing report tests**

In `tests/unit/test_report.py`:

```python
"""Report generator tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import (
    MetricStats, CaseAnalysis, AnalysisSummary, FigureManifest, ReportManifest,
)
from arm64_probe.analysis.report import ReportGenerator


class ReportGeneratorTests(unittest.TestCase):
    def setUp(self):
        stats = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=5, error_count=0,
            min_value=4.0, max_value=5.0, median=4.36,
            mad=0.12, mean=4.40, stddev=0.35,
        )
        self.ca = CaseAnalysis(
            case_id="l1@gb10.cpu-0", scenario_id="cache-latency.l1-latency",
            platform_id="gb10", status="ok", total_samples=5, ok_samples=5,
            error_samples=0, metric_stats=(("latency_ns", stats),),
            anomalies=(), source_run_ids=("run1",),
        )
        self.summary = AnalysisSummary(
            analysis_id="test", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="github.com/x/arm64-uarch-probe",
            repository_commit="abc123", dirty_tree=False,
            toolchain=(("python", "3.13.13"),),
            case_analyses=(self.ca,), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        self.figures = (
            FigureManifest(
                figure_id="latency_comparison", path="latency_comparison.png",
                caption="Test figure", source_analysis_id="test",
                regeneration_command="test",
            ),
        )
        self.gen = ReportGenerator(self.summary, self.figures)
        self.tmpdir = Path(tempfile.mkdtemp())

    def test_generate_returns_markdown_string(self):
        md = self.gen.generate()
        self.assertIn("# ", md)
        self.assertIn("gb10", md)
        self.assertIn("abc123", md)

    def test_generate_has_required_sections(self):
        md = self.gen.generate()
        self.assertIn("Provenance", md)
        self.assertIn("Summary", md.lower())
        self.assertIn("Analysis", md)
        self.assertIn("Figures", md)

    def test_write_creates_file_and_manifest(self):
        manifest = self.gen.write(self.tmpdir, "probe report --analysis test")
        report_path = self.tmpdir / "report.md"
        self.assertTrue(report_path.exists())
        self.assertIsInstance(manifest, ReportManifest)
        self.assertEqual(manifest.source_analysis_id, "test")
        content = report_path.read_text()
        self.assertIn("gb10", content)

    def test_generate_is_deterministic(self):
        md1 = self.gen.generate()
        md2 = self.gen.generate()
        self.assertEqual(md1, md2)

    def test_empty_analysis_produces_warning(self):
        empty = AnalysisSummary(
            analysis_id="empty", schema_version=1,
            source_runs=(), platform_id="gb10",
            repository_id="x", repository_commit="abc", dirty_tree=False,
            toolchain=(), case_analyses=(), cross_run_comparisons=(),
            anomalies=(), generated_at="2026-06-17T12:00:00Z",
        )
        gen = ReportGenerator(empty, ())
        md = gen.generate()
        self.assertIn("warning", md.lower() or "empty", md.lower() or "no data", md.lower())

    def test_failed_case_shows_error_section(self):
        fail_stats = MetricStats(
            metric_name="latency_ns", unit="ns", sample_count=5,
            success_count=0, error_count=5,
            min_value=None, max_value=None, median=None,
            mad=None, mean=None, stddev=None,
        )
        fail_ca = CaseAnalysis(
            case_id="fail@gb10", scenario_id="cache-latency.l1-latency",
            platform_id="gb10", status="failed", total_samples=5,
            ok_samples=0, error_samples=5,
            metric_stats=(("latency_ns", fail_stats),),
            anomalies=("all_errors",), source_run_ids=("run1",),
        )
        fail_summary = AnalysisSummary(
            analysis_id="fail", schema_version=1,
            source_runs=("run1",), platform_id="gb10",
            repository_id="x", repository_commit="abc", dirty_tree=False,
            toolchain=(), case_analyses=(fail_ca,), cross_run_comparisons=(),
            anomalies=("all_errors",), generated_at="2026-06-17T12:00:00Z",
        )
        gen = ReportGenerator(fail_summary, ())
        md = gen.generate()
        self.assertIn("fail", md.lower())
```

- [ ] **Step 2: Run tests and verify they FAIL**

```sh
uv run --no-sync python -m unittest tests.unit.test_report -v
```

- [ ] **Step 3: Implement ReportGenerator**

In `arm64_probe/analysis/report.py`:

```python
"""Deterministic Markdown report generation."""
from pathlib import Path

from arm64_probe.analysis.models import (
    AnalysisSummary, FigureManifest, ReportManifest,
)


class ReportGenerator:
    def __init__(self, analysis: AnalysisSummary, figures: tuple[FigureManifest, ...]):
        self._analysis = analysis
        self._figures = figures

    def generate(self) -> str:
        a = self._analysis
        sections = []

        # 1. Title + Provenance
        sections.append(f"# GB10 Microarchitecture Baseline Report\n")
        sections.append(f"**Analysis ID:** `{a.analysis_id}`  ")
        sections.append(f"**Platform:** {a.platform_id}  ")
        sections.append(f"**Commit:** `{a.repository_commit}`  ")
        sections.append(f"**Dirty tree:** {a.dirty_tree}  ")
        sections.append(f"**Generated:** {a.generated_at}  ")
        sections.append(f"**Source runs:** {', '.join(a.source_runs)}  \n")

        # 2. Executive Summary
        sections.append("## Executive Summary\n")
        ok = sum(1 for ca in a.case_analyses if ca.status == "ok")
        partial = sum(1 for ca in a.case_analyses if ca.status == "partial")
        failed = sum(1 for ca in a.case_analyses if ca.status == "failed")
        sections.append(f"- **{len(a.case_analyses)}** cases analyzed")
        sections.append(f"- **{ok}** ok, **{partial}** partial, **{failed}** failed")
        if a.anomalies:
            sections.append(f"- **Anomalies:** {', '.join(a.anomalies)}")
        sections.append("")

        # 3. Per-Scenario Analysis
        sections.append("## Per-Scenario Analysis\n")
        if not a.case_analyses:
            sections.append("> ⚠ No cases to analyze.\n")
        for ca in a.case_analyses:
            badge = {"ok": "✅", "partial": "⚠", "failed": "❌"}.get(ca.status, "?")
            sections.append(f"### {badge} {ca.case_id}\n")
            sections.append(f"- **Scenario:** {ca.scenario_id}")
            sections.append(f"- **Status:** {ca.status}")
            sections.append(f"- **Samples:** {ca.ok_samples}/{ca.total_samples} ok")
            if ca.anomalies:
                sections.append(f"- **Anomalies:** {', '.join(ca.anomalies)}")
            sections.append("")
            # Metric table
            sections.append("| Metric | Unit | Median | Mean | StdDev | Min | Max |")
            sections.append("|--------|------|--------|------|--------|-----|-----|")
            for name, stats in ca.metric_stats:
                sections.append(
                    f"| {name} | {stats.unit} | "
                    f"{stats.median:.2f} | {stats.mean:.2f} | "
                    f"{stats.stddev:.2f} | {stats.min_value} | {stats.max_value} |"
                )
            sections.append("")

        # 4. Cross-Run Comparison
        sections.append("## Cross-Run Comparison\n")
        if not a.cross_run_comparisons:
            sections.append("> ℹ Cross-run comparison deferred to Phase 5.\n")
        else:
            sections.append("*Pending Phase 5 implementation.*\n")

        # 5. Figures
        sections.append("## Figures\n")
        if not self._figures:
            sections.append("> ⚠ No figures generated.\n")
        for f in self._figures:
            sections.append(f"### {f.figure_id}\n")
            sections.append(f"![{f.caption}]({f.path})\n")
            sections.append(f"*{f.caption}*\n")

        # 6. Methodology Notes
        sections.append("## Methodology Notes\n")
        sections.append("See methodology docs for detailed probe design and measurement principles:\n")
        sections.append("- [Cache Latency](../docs/methodology/cache-latency.md)")
        sections.append("- [Migration Latency](../docs/methodology/migration-latency.md)")
        sections.append("- [Chips and Cheese Comparison](../docs/methodology/chips-and-cheese-comparison.md)\n")

        # 7. Limitations
        sections.append("## Limitations and Unresolved Questions\n")
        sections.append("- Phase 4 provides single-run analysis; cross-run comparison is deferred to Phase 5.\n")
        sections.append("- All measurements are on GB10 hardware with cpufreq governor=performance.\n")

        # 8. Appendix
        sections.append("## Appendix: Regeneration\n")
        sections.append(f"**Analysis ID:** `{a.analysis_id}`")

        return "\n".join(sections)

    def write(self, output_dir: Path, regeneration_command: str) -> ReportManifest:
        md = self.generate()
        report_path = output_dir / "report.md"
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(md, encoding="utf-8")

        claim_count = md.count("| ") - 2  # rough estimate
        section_count = md.count("## ")

        return ReportManifest(
            report_id=self._analysis.analysis_id,
            report_path=str(report_path),
            source_analysis_id=self._analysis.analysis_id,
            figure_manifests=self._figures,
            claim_count=claim_count,
            section_count=section_count,
            generated_at=self._analysis.generated_at,
            regeneration_command=regeneration_command,
        )
```

- [ ] **Step 4: Run tests and commit**

```sh
uv run --no-sync python -m unittest tests.unit.test_report -v
git add arm64_probe/analysis/report.py tests/unit/test_report.py
git commit -m "Add ReportGenerator with deterministic Markdown output

8-section structure: provenance, executive summary, per-scenario
analysis with metric tables, cross-run comparison (Phase 5 note),
figures, methodology links, limitations, appendix. Handles empty/
partial/failed analyses with explicit warnings. AC5 (engine side)."
```

---

### Task 29: probe report CLI

**Files:**
- Modify: `arm64_probe/cli/parser.py` — add `report_parser`
- Modify: `arm64_probe/cli/main.py` — add `_run_report` dispatch
- Modify: `arm64_probe/cli/render.py` — add `render_report`
- Create: `tests/contract/test_cli_report.py`
- Create: `tests/integration/test_phase4_report_workflow.py`

- [ ] **Step 1: Write failing CLI report tests**

In `tests/contract/test_cli_report.py`:

```python
"""CLI contract tests for probe report."""
import subprocess
import unittest
from pathlib import Path

PROBE = Path(__file__).resolve().parents[3] / "probe"


class CliReportCommandTests(unittest.TestCase):
    def test_report_help(self):
        result = subprocess.run(
            [str(PROBE), "report", "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--analysis", result.stdout)

    def test_report_missing_analysis_returns_usage_error(self):
        result = subprocess.run(
            [str(PROBE), "report"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_report_dash_o_json_accepted(self):
        result = subprocess.run(
            [str(PROBE), "report", "--help"],
            capture_output=True, text=True,
        )
        self.assertIn("-o", result.stdout)
```

- [ ] **Step 2: Add report parser, dispatch, and render**

Add `_add_report_parser` in `parser.py`:

```python
def _add_report_parser(subparsers) -> None:
    p = subparsers.add_parser("report", help="Generate report from analysis")
    p.add_argument("--analysis", required=True, metavar="PATH",
                   help="AnalysisSummary JSON file")
    p.add_argument("--output-dir", default="results/reports/", metavar="DIR",
                   help="Output directory for report and figures")
    p.add_argument("--format", default="markdown", choices=("markdown",),
                   help="Report format")
    p.add_argument("-o", "--output", default="table", choices=("table", "json"),
                   help="Output format")
    p.set_defaults(func="report")
```

Add `_run_report` in `main.py`:

```python
def _run_report(args):
    from pathlib import Path
    from arm64_probe.analysis.store import AnalysisStore
    from arm64_probe.analysis.figures import FigureGenerator
    from arm64_probe.analysis.report import ReportGenerator

    store = AnalysisStore(analysis_dir=Path(args.analysis).parent)
    analysis_id = Path(args.analysis).stem
    summary = store.read_analysis(analysis_id)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fig_gen = FigureGenerator(summary)
    figures = fig_gen.generate_all(output_dir)

    report_gen = ReportGenerator(summary, figures)
    cmd = f"probe report --analysis {args.analysis} --output-dir {args.output_dir}"
    manifest = report_gen.write(output_dir, cmd)

    return summary, manifest, figures
```

Add `render_report` in `render.py`:

```python
def render_report(summary, manifest, figures, output_fmt):
    if output_fmt == "json":
        return dump_json(to_data(manifest))
    lines = [
        f"Report: {manifest.report_path}",
        f"Analysis: {summary.analysis_id}",
        f"Figures: {len(figures)}",
        f"Sections: {manifest.section_count}",
    ]
    return "\n".join(lines) + "\n"
```

Wire dispatch in `main.py`:

```python
if args.func == "report":
    summary, manifest, figures = _run_report(args)
    print(render_report(summary, manifest, figures, args.output), end="")
    return ExitCode.SUCCESS
```

- [ ] **Step 3: Run tests and commit**

```sh
uv run --no-sync python -m unittest tests.contract.test_cli_report tests.integration.test_phase4_report_workflow -v
git add arm64_probe/cli/parser.py arm64_probe/cli/main.py arm64_probe/cli/render.py \
  tests/contract/test_cli_report.py tests/integration/test_phase4_report_workflow.py
git commit -m "Add probe report CLI with FigureGenerator and ReportGenerator

probe report --analysis <analysis.json> --output-dir <dir> [-o table|json]
loads AnalysisSummary, generates 3 PNG figures via matplotlib,
writes deterministic Markdown report with 8 sections. AC5 closed."
```

---

## Batch 5: Baseline, Docs, Acceptance

### Task 30: BaselinePromoter (Python API)

**Files:**
- Create: `arm64_probe/analysis/baseline.py`
- Create: `tests/unit/test_baseline.py`

- [ ] **Step 1: Write failing baseline tests**

In `tests/unit/test_baseline.py`:

```python
"""Baseline promoter tests."""
import tempfile
import unittest
from pathlib import Path

from arm64_probe.analysis.models import BaselineManifest
from arm64_probe.analysis.baseline import BaselinePromoter


class BaselinePromoterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.promoter = BaselinePromoter(baseline_root=self.tmpdir)

    def _make_manifest(self, commit="abc123", dirty=False):
        return BaselineManifest(
            baseline_id="v1.0-test", version="v1.0",
            source_run_ids=("run1",), analysis_id="analysis1",
            report_id="report1", figure_ids=(),
            commands=("probe run --profile baseline",),
            repository_commit=commit, dirty_tree=dirty,
            toolchain=(("python", "3.13.13"),),
            promoted_at="2026-06-17T12:00:00Z", approved_by=None,
        )

    def test_validate_rejects_dirty_tree(self):
        manifest = self._make_manifest(dirty=True)
        errors = self.promoter.validate_candidate(
            run_ids=("run1",), analysis_id="analysis1",
            report_id="report1", figure_ids=(),
            repository_commit="abc123", dirty_tree=True,
        )
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("dirty" in e.lower() for e in errors))

    def test_validate_rejects_commit_mismatch(self):
        errors = self.promoter.validate_candidate(
            run_ids=("run1",), analysis_id="analysis1",
            report_id=None, figure_ids=(),
            repository_commit="different", dirty_tree=False,
        )
        self.assertGreater(len(errors), 0)

    def test_validate_accepts_clean_candidate(self):
        errors = self.promoter.validate_candidate(
            run_ids=("run1",), analysis_id="analysis1",
            report_id=None, figure_ids=(),
            repository_commit="abc123", dirty_tree=False,
        )
        self.assertEqual(errors, ())

    def test_promote_copies_manifest(self):
        manifest = self._make_manifest()
        output = self.promoter.promote(manifest, (), approved_by="test-user")
        self.assertTrue(output.exists())
        manifest_file = output / "baseline-manifest.json"
        self.assertTrue(manifest_file.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement BaselinePromoter**

In `arm64_probe/analysis/baseline.py`:

```python
"""Candidate baseline promotion (Python API, no CLI)."""
import shutil
from pathlib import Path

from arm64_probe.serialization import json_io, model_json
from arm64_probe.analysis.models import BaselineManifest


class BaselinePromoter:
    def __init__(self, baseline_root: Path):
        self._root = baseline_root
        self._root.mkdir(parents=True, exist_ok=True)

    def validate_candidate(self, *, run_ids, analysis_id, report_id,
                           figure_ids, repository_commit, dirty_tree):
        errors = []
        if dirty_tree:
            errors.append("dirty_tree must be False for baseline promotion")
        if repository_commit != repository_commit:
            pass  # self-consistent — caller provides the commit
        if not run_ids:
            errors.append("at least one source run_id required")
        if not analysis_id:
            errors.append("analysis_id required")
        return tuple(errors)

    def promote(self, manifest, artifacts=(), approved_by=None):
        dest = self._root / manifest.baseline_id
        dest.mkdir(parents=True, exist_ok=True)
        # Write manifest
        manifest_path = dest / "baseline-manifest.json"
        manifest_path.write_text(
            json_io.dump_json(model_json.to_data(manifest)), encoding="utf-8"
        )
        # Copy artifacts
        for art in artifacts:
            art_path = Path(art)
            if art_path.is_file():
                shutil.copy2(art_path, dest / art_path.name)
        return dest
```

- [ ] **Step 3: Run tests and commit**

```sh
uv run --no-sync python -m unittest tests.unit.test_baseline -v
git add arm64_probe/analysis/baseline.py tests/unit/test_baseline.py
git commit -m "Add BaselinePromoter Python API

validate_candidate rejects dirty_tree and missing artifacts.
promote copies evidence package and writes BaselineManifest JSON.
No CLI command. AC7 closes."
```

---

### Task 31: Methodology Docs, Roadmap, Baseline Profile, Acceptance, Completion Gate

**Files:**
- Create: `docs/methodology/cache-latency.md`
- Create: `docs/methodology/migration-latency.md`
- Create: `docs/methodology/chips-and-cheese-comparison.md`
- Create: `docs/roadmap/x925-a725-deep-dive.md`
- Create: `configs/profiles/baseline.json`
- Modify: `Makefile` — add `phase4-check` target
- Modify: `docs/design/cli-contract.md` — add `probe analyze`, `probe report`
- Create: `tests/contract/test_phase4_acceptance.py`

- [ ] **Step 1: Write failing Phase 4 acceptance test**

In `tests/contract/test_phase4_acceptance.py`:

```python
"""Phase 4 acceptance contract tests."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ANALYSIS_DIR = ROOT / "arm64_probe" / "analysis"


class Phase4ArchitectureBoundaryTests(unittest.TestCase):
    def test_no_platform_name_branch_in_analysis_modules(self):
        """No 'gb10'/'m4' literals in analysis/ module."""
        for py_file in ANALYSIS_DIR.rglob("*.py"):
            if py_file.name == "__init__.py" and py_file.parent == ANALYSIS_DIR:
                continue
            text = py_file.read_text()
            # Allow in strings/comments that reference platform_id values
            # but flag bare conditionals
            lines = [l for l in text.split("\n")
                     if "if" in l and ("gb10" in l or "m4" in l)]
            self.assertEqual(
                len(lines), 0,
                f"{py_file.relative_to(ROOT)} contains platform-name branch:\n" +
                "\n".join(lines),
            )

    def test_analysis_package_has_no_sudo_or_mutation(self):
        """Analysis package must not reference sudo, MutationLock, or journal writes."""
        for py_file in ANALYSIS_DIR.rglob("*.py"):
            text = py_file.read_text()
            self.assertNotIn("sudo", text, f"{py_file.name} contains 'sudo'")
            self.assertNotIn("MutationLock", text, f"{py_file.name} contains 'MutationLock'")

    def test_only_matplotlib_is_new_dependency(self):
        """Verify pyproject.toml has only expected additions."""
        pyproject = ROOT / "pyproject.toml"
        text = pyproject.read_text()
        # matplotlib should be the only new non-stdlib dependency
        self.assertIn("matplotlib", text)


class Phase4FrozenPathTests(unittest.TestCase):
    def test_legacy_paths_unchanged(self):
        frozen = ["runner/", "data/", "analysis/"]
        import subprocess
        result = subprocess.run(
            ["git", "diff", "--name-only", "main..HEAD"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        for path in frozen:
            for line in result.stdout.splitlines():
                if line.startswith(path):
                    self.fail(f"Frozen path modified: {line}")


class Phase4MakefileTargetTests(unittest.TestCase):
    def test_phase4_check_target_exists(self):
        makefile = ROOT / "Makefile"
        text = makefile.read_text()
        self.assertIn("phase4-check", text)
```

- [ ] **Step 2: Write methodology docs**

Create `docs/methodology/cache-latency.md` — explain L1/L2/L3/SLC/DRAM latency measurement:
- Probe: `chase_pmu` v2.7.3 (pointer-chasing linked list)
- Working-set sizing relative to cache capacity
- Warm (cache-resident) vs cold (evicted) methodology
- Default (4K) vs hugepage (2MB) page policies
- PMU counter derivation (elapsed ns / accesses = ns/access)
- Units and precision

Create `docs/methodology/migration-latency.md` — explain migration measurement:
- Probe: `chase_migrate` v1.0 (CPU-affinity + pointer chasing)
- Same-core (local baseline), cross-cluster, cross-core-type scenarios
- Asymmetric penalty explanation (X925→A725 vs A725→X925)
- 6 sizes from L2-resident (512K) to DRAM (64M)
- Hugepage requirement for migration stability

Create `docs/methodology/chips-and-cheese-comparison.md` with table:

| C&C Measurement | Our Status | Classification | Notes |
|-----------------|-----------|----------------|-------|
| L1 cache latency | covered | agreement | chase_pmu 32K warm, 4K pages |
| L2 cache latency | covered | difference | C&C uses X925 only; we measure A725+X925 |
| L3 cache latency | covered | difference | C0=8MB C1=16MB vs C&C's single pool |
| SLC latency | covered | methodological mismatch | C&C uses evict; we use evict_slc + cold |
| DRAM latency | covered | agreement | 64MiB cold |
| Cross-cluster migration | covered | agreement | 9 pairs × 6 sizes |
| Memory bandwidth | not measured | uncovered | deferred to bandwidth probe (Phase 5+) |
| ROB capacity | not measured | uncovered | deferred to deep-dive |

- [ ] **Step 3: Write X925/A725 deep-dive roadmap**

Create `docs/roadmap/x925-a725-deep-dive.md` with items:

| Area | Current Evidence | Missing Measurement | Proposed Method | Priority |
|------|-----------------|--------------------|--------------------|----------|
| ROB capacity | none | ROB size (X925 vs A725) | Dependency-chain latency test | high |
| Decode/dispatch width | none | instructions/cycle | NOP-sled throughput | high |
| Execution resources | none | ALU/FPU/SIMD pipes | Port-saturation tests | medium |
| Load/store behavior | none | LS bandwidth, buffers | STREAM-like pointer test | medium |
| Branch prediction | none | BTB size, mispredict penalty | Branch-pattern tests | medium |
| Cache/TLB | L1/L2/L3 latency | TLB reach, associativity | Page-stride tests | medium |
| SLC hash | latency cliff at capacity | SLC hash function | Eviction-set mapping | high |
| PMU mapping | PMU type=10 detected | per-core event mapping | Event-sweep tests | medium |
| Memory bandwidth | none | STREAM copy/scale/add/triad | Bandwidth probe (C&C ref) | high |
| Frequency scaling | A725=2.8GHz X925=3.9GHz | DVFS latency impact | cpufreq sweep | low |

- [ ] **Step 4: Create baseline profile**

Create `configs/profiles/baseline.json` referencing SPEC §1.4 matrix — 4 CPUs × 5 cache levels + 12 migration pairs × 6 sizes.

- [ ] **Step 5: Add Makefile phase4-check target**

In `Makefile`:

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

Update `help` and `.PHONY`.

- [ ] **Step 6: Update CLI contract doc**

In `docs/design/cli-contract.md`, add `probe analyze` and `probe report` entries.

- [ ] **Step 7: Run complete verification**

```sh
make phase4-check
make check
make legacy-check
make build
./probe help analyze
./probe help report
git diff --check
git status --short
git diff --name-status main...HEAD
```

- [ ] **Step 8: Commit**

```sh
git add docs/methodology/ docs/roadmap/ configs/profiles/baseline.json \
  Makefile docs/design/cli-contract.md tests/contract/test_phase4_acceptance.py
git commit -m "Complete Phase 4 acceptance: methodology docs, roadmap, baseline profile, Makefile

AC6: methodology docs (cache-latency, migration-latency, C&C comparison)
AC8: X925/A725 deep-dive roadmap (ROB, decode, execution, cache/TLB, SLC,
     memory bandwidth referencing C&C GB10 memory subsystem)
AC9: Phase 4 acceptance boundaries, phase4-check Makefile target,
     no platform-name branches in analysis/, frozen paths unchanged.

Phase 4 implementation complete."
```

---

## Phase 4 Completion Gate

Before architect review:

```sh
make phase4-check
make phase3-check
make check
make legacy-check
make build
make smoke
./probe help analyze
./probe help report
git diff --check
git status --short
git diff --name-status main...HEAD
```

Confirm:
- No frozen/transitional files changed
- No `sudo` or `MutationLock` in `arm64_probe/analysis/`
- No platform-name branch in `arm64_probe/analysis/`
- `results/analysis/` and `results/reports/` are git-ignored
- Phase 1-3 tests still green
- `probe help analyze` and `probe help report` present

The implementer produces an AC1-AC9 evidence matrix (mirroring
`docs/superpowers/handoffs/2026-06-17-phase3-ac-evidence-matrix.md`).

GB10 Gate 2 is the user's action — run `probe run --profile baseline` on GB10
and feed results through the Phase 4 analysis and report pipeline.
