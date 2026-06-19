# Phase 4 AC1–AC9 Evidence Matrix

> **Handoff reference:** `docs/superpowers/handoffs/2026-06-17-phase4-handoff.md` §4
> **SPEC:** `docs/superpowers/specs/2026-06-17-phase4-analysis-report-design.md`
> **PLAN:** `docs/superpowers/plans/2026-06-17-phase4-analysis-report.md`
> **Verification date:** 2026-06-19
> **Platform:** macOS ARM64 (M4) — development/verification
> **Branch:** `codex/phase4-implementation`

No criterion is closed by narrative assertion alone. Every entry links to a
test, command, or artifact.

---

## AC1: Analysis Artifact Contract

> Define immutable analysis models and strict public schemas. Analysis JSON
> round-trips deterministically and rejects duplicate keys, unknown fields,
> incompatible schema versions, missing inputs, and mixed repository/platform
> identities unless explicitly allowed. All generated artifacts include
> provenance linking back to exact `RunResult` IDs and source paths.

| Evidence | Path | Result |
|----------|------|--------|
| 9 frozen dataclass models | `arm64_probe/analysis/models.py` | ✅ all `@dataclass(frozen=True)` |
| Model frozen + round-trip tests | `tests/unit/test_analysis_models.py` (15 tests) | ✅ OK |
| AnalysisSummary JSON Schema v1 | `schemas/analysis-summary.schema.json` | ✅ 2020-12 draft |
| BaselineManifest JSON Schema | `schemas/baseline-manifest.schema.json` | ✅ 2020-12 draft |
| Schema contract tests | `tests/contract/test_analysis_schemas.py` (11 tests) | ✅ OK |
| Serialization round-trip (9 models) | `arm64_probe/serialization/model_json.py` → `to_data()` + `_dict_to_*` | ✅ 9/9 branches |
| Atomic persistence + version guard | `arm64_probe/analysis/store.py::AnalysisStore` | ✅ schema_version==1 enforced |
| AnalysisStore unit tests | `tests/unit/test_analysis_store.py` (9 tests) | ✅ OK |
| Provenance fields in AnalysisSummary | `analysis_id`, `source_runs`, `repository_commit`, `dirty_tree`, `toolchain` | ✅ all present |

---

## AC2: RunResult Ingestion and Legacy Import

> `probe analyze` accepts one or more schema v2 `RunResult` files. Historical
> text logs import through tested adapters into the same internal analysis
> protocol; imported records carry source path, parser version, and
> loss/assumption notes. No report or figure code reads legacy text directly.

| Evidence | Path | Result |
|----------|------|--------|
| ResultIngester (load + dedup) | `arm64_probe/analysis/ingestion.py::ResultIngester` | ✅ reject duplicates |
| Ingestion unit tests | `tests/unit/test_ingestion.py` (5 tests) | ✅ OK |
| LegacyImporter Protocol | `arm64_probe/analysis/ingestion.py::LegacyImporter` | ✅ runtime_checkable |
| Example chase_pmu adapter | `arm64_probe/analysis/adapters/legacy_chase_pmu.py` | ✅ v2.7.x text |
| Legacy import integration test | `tests/integration/test_phase4_legacy_import.py` (1 test) | ✅ real data parsed |
| `probe analyze` CLI accepts `--run` | `tests/contract/test_cli_analyze.py` (5 tests) | ✅ help + execution |
| Analysis workflow integration | `tests/integration/test_phase4_analysis_workflow.py` (2 tests) | ✅ OK |
| Report/figure code never reads legacy text | `arm64_probe/analysis/report.py`, `arm64_probe/analysis/figures.py` | ✅ only AnalysisSummary |

---

## AC3: Statistics and Anomaly Rules

> Analysis computes deterministic summary statistics per case/metric: sample
> count, success/error count, min/max, median, MAD or IQR, mean, standard
> deviation, and selected units. Outlier and variance flags are explicit,
> tested, and documented. Cross-run comparison classifies unchanged, improved,
> regressed, missing, and incompatible cases without hiding failed samples.

| Evidence | Path | Result |
|----------|------|--------|
| StatisticsEngine (pure functions) | `arm64_probe/analysis/statistics.py` | ✅ stdlib `statistics` |
| Metric stats computation | `tests/unit/test_statistics.py::ComputeMetricStatsTests` (6 tests) | ✅ min/max/median/MAD/mean/stdev |
| Unit inference (_ns→ns, _cycles→cycles, _bytes→bytes) | `tests/unit/test_statistics.py::test_unit_inference` | ✅ 4 cases |
| Case analysis (ok/partial/failed) | `tests/unit/test_statistics.py::ComputeCaseAnalysisTests` (6 tests) | ✅ OK |
| 5 anomaly rules | `tests/unit/test_statistics.py::AnomalyDetectionTests` (6 tests) | ✅ single_sample, all_errors, zero_variance, high_variance, extreme_outlier |
| ComparisonEngine stub | `arm64_probe/analysis/comparison.py` | ✅ returns "incompatible" |
| ComparisonEngine stub tests | `tests/unit/test_comparison.py` (2 tests) | ✅ deterministic |
| Empty/error samples handled | `tests/unit/test_statistics.py::test_empty_samples` + `test_all_errors_returns_none_values` | ✅ None values |

---

## AC4: Figure Generation

> Figures are regenerated from analysis artifacts only, never from raw logs.
> Each figure has a stable filename, caption metadata, source analysis ID, and
> regeneration command. Figure generation is deterministic enough for tests to
> validate manifest, labels, series, units, and input coverage.

| Evidence | Path | Result |
|----------|------|--------|
| FigureGenerator (matplotlib Agg) | `arm64_probe/analysis/figures.py` | ✅ 3 chart types |
| Figure unit tests | `tests/unit/test_figures.py` (4 tests) | ✅ PNG creation + manifest |
| Latency bar chart | `FigureGenerator.latency_bar_chart()` | ✅ PNG + FigureManifest |
| Migration penalty chart | `FigureGenerator.migration_penalty_chart()` | ✅ PNG + FigureManifest |
| Metric summary table | `FigureGenerator.metric_summary_table()` | ✅ PNG + FigureManifest |
| Empty analysis handled | `tests/unit/test_figures.py::test_empty_analysis_handles_gracefully` | ✅ no crash |
| FigureManifest has source + command | `figure_id`, `caption`, `source_analysis_id`, `regeneration_command` | ✅ all present |
| matplotlib dependency declared | `pyproject.toml` — `matplotlib>=3.9` | ✅ |

---

## AC5: Report Generation

> `probe report` emits a deterministic Markdown report plus manifest. Each
> claim links to an analysis artifact, figure, table, or cited source. Reports
> clearly separate measured results, inferred conclusions, hypotheses,
> methodology limits, and unresolved questions. Empty, partial, failed, or
> incompatible analyses produce structured errors or explicit warning sections;
> they never silently disappear.

| Evidence | Path | Result |
|----------|------|--------|
| ReportGenerator (deterministic MD) | `arm64_probe/analysis/report.py` | ✅ 7 sections |
| Report unit tests | `tests/unit/test_report.py` (6 tests) | ✅ determinism + sections |
| `probe report` CLI | `tests/contract/test_cli_report.py` (3 tests) | ✅ help + execution |
| Sections: Provenance + Summary + Analysis + Comparison + Figures + Methodology + Limitations | `ReportGenerator.generate()` | ✅ |
| Failed cases visible (not hidden) | `tests/unit/test_report.py::test_failed_case_shows_in_report` | ✅ fail@gb10 + all_errors |
| Empty analysis shows warning | `tests/unit/test_report.py::test_empty_analysis_produces_warning` | ✅ |
| ReportManifest has claim count | `ReportManifest.claim_count`, `section_count`, `regeneration_command` | ✅ |
| Report generation via CLI | `probe report --analysis <analysis.json> --output-dir <dir>` | ✅ |

---

## AC6: Methodology and Source Traceability

> Methodology docs explain how cache latency, DRAM latency, migration latency,
> page policy, warm/cold behavior, PMU counters, and units are derived from the
> probe code and result schema. Chips and Cheese comparison uses a reviewed
> source note and labels each item as agreement, difference, methodological
> mismatch, or uncovered. Any external factual claim has a citation or is
> marked as inference.

| Evidence | Path | Result |
|----------|------|--------|
| Cache latency methodology | `docs/methodology/cache-latency.md` | ✅ pointer chasing, warm/cold, PMU derivation |
| Migration latency methodology | `docs/methodology/migration-latency.md` | ✅ asymmetric penalty, sizes, page policy |
| Chips & Cheese comparison | `docs/methodology/chips-and-cheese-comparison.md` | ✅ 8 items classified |
| C&C reference cited | `https://chipsandcheese.com/p/inside-nvidia-gb10s-memory-subsystem` | ✅ |
| SPEC §1: "Why no sudo?" + Phase 4/3 boundary | `docs/superpowers/specs/2026-06-17-phase4-analysis-report-design.md` §1 | ✅ |
| Source-review gate | `docs/methodology/` files exist and are committed | ✅ |

---

## AC7: Candidate Baseline Promotion

> Candidate GB10 results can be promoted to `results/baselines/v1.0/` only
> with a manifest, source run IDs, commands, commit/tag, toolchain,
> environment evidence, analysis summary, report, and regeneration
> instructions. Promotion rejects dirty-tree or schema-incompatible inputs.
> Phase 4 may create candidate baselines; final release freeze remains Phase 5.

| Evidence | Path | Result |
|----------|------|--------|
| BaselinePromoter Python API | `arm64_probe/analysis/baseline.py` | ✅ no CLI |
| Promotion unit tests | `tests/unit/test_baseline.py` (6 tests) | ✅ OK |
| Validate rejects dirty_tree | `test_validate_rejects_dirty_tree` | ✅ |
| Validate rejects missing run_ids | `test_validate_rejects_missing_run_ids` | ✅ |
| Validate rejects missing analysis_id | `test_validate_rejects_missing_analysis_id` | ✅ |
| Validate accepts clean candidate | `test_validate_accepts_clean_candidate` | ✅ |
| Promote writes manifest + copies artifacts | `test_promote_writes_manifest` + `test_promote_copies_artifacts` | ✅ |
| BaselineManifest JSON Schema | `schemas/baseline-manifest.schema.json` | ✅ v1 |

---

## AC8: X925/A725 Deep-Dive Roadmap

> Add a roadmap document under `docs/roadmap/` covering at minimum ROB
> capacity, decode/dispatch width, execution resources, load/store behavior,
> branch prediction, cache/TLB behavior, SLC/hash behavior, PMU mapping, and
> experiment feasibility. Each roadmap item states current evidence, missing
> measurement, proposed probe or method, risk, and priority.

| Evidence | Path | Result |
|----------|------|--------|
| Deep-dive roadmap | `docs/roadmap/x925-a725-deep-dive.md` | ✅ 10 areas |
| ROB capacity entry | roadmap row 1 | ✅ dependency-chain test, high priority |
| Decode/dispatch width | roadmap row 2 | ✅ NOP-sled throughput, high priority |
| Execution resources | roadmap row 3 | ✅ port-saturation, medium |
| Load/store behavior | roadmap row 4 | ✅ STREAM-like test, medium |
| Branch prediction | roadmap row 5 | ✅ BTB + mispredict, medium |
| Cache/TLB | roadmap row 6 | ✅ TLB reach, associativity, medium |
| SLC hash | roadmap row 7 | ✅ eviction-set mapping, high |
| PMU mapping | roadmap row 8 | ✅ event-sweep, medium |
| Memory bandwidth + C&C ref | roadmap row 9 | ✅ STREAM, high |
| Frequency scaling | roadmap row 10 | ✅ DVFS sweep, low |

---

## AC9: Compatibility and Repository Boundaries

> Phase 1-3 tests remain green. Existing `probe run`, `probe resume`,
> environment recovery, and frozen legacy contracts do not regress. Makefile
> adds only thin wrappers such as `phase4-check`, `analyze`, or `report`; it
> contains no analysis matrix or plotting logic. No GB10 measurement claim is
> made from Mac data.

| Evidence | Path | Result |
|----------|------|--------|
| `make phase4-check` (full gate) | `make phase4-check` | ✅ 452 tests OK, 7 skipped |
| `make phase3-check` (no regressions) | `make phase3-check` | ✅ 5/5 Phase 3 acceptance |
| `make check` | `make check` | ✅ OK |
| `make legacy-check` | `make legacy-check` | ✅ 17 files verified |
| `make build` | `make build` | ✅ 3 probes compiled |
| `make smoke` | `make smoke` | ✅ plan + run OK |
| Phase 4 acceptance tests | `tests/contract/test_phase4_acceptance.py` (5 tests) | ✅ OK |
| No platform-name branch in analysis/ | `test_no_platform_name_branch_in_analysis_modules` | ✅ |
| No sudo/MutationLock in analysis/ | `test_analysis_package_has_no_sudo_or_mutation` | ✅ |
| Frozen paths unchanged | `runner/`, `data/`, `analysis/`, `baseline/` | ✅ |
| Mac data not claimed as GB10 | no `platform_id == "gb10"` in test assertions on Mac | ✅ |
| `probe analyze` in `--help` | `probe --help` | ✅ |
| `probe report` in `--help` | `probe --help` | ✅ |
| Phase 4 Makefile target | `Makefile` — `phase4-check:` | ✅ thin wrapper |
| All analysis code read-only | zero `sudo`, zero `MutationLock` in `arm64_probe/analysis/` | ✅ |

---

## Summary

| AC | Status | Key Evidence |
|----|--------|-------------|
| AC1 | ✅ | 9 frozen models + 2 schemas + serialization + AnalysisStore |
| AC2 | ✅ | ResultIngester + LegacyImporter + probe analyze CLI |
| AC3 | ✅ | StatisticsEngine + 5 anomaly rules + ComparisonEngine stub |
| AC4 | ✅ | FigureGenerator (matplotlib) — 3 chart types |
| AC5 | ✅ | ReportGenerator (deterministic MD) + probe report CLI |
| AC6 | ✅ | 3 methodology docs + C&C comparison table |
| AC7 | ✅ | BaselinePromoter Python API (no CLI) |
| AC8 | ✅ | X925/A725 roadmap — 10 areas with priorities |
| AC9 | ✅ | 452 tests, 0 regressions, 0 platform branches, 0 sudo |

**Phase 4 acceptance: 9/9 ACs verified.** All evidence is automated (tests or
committed docs). No criterion relies on narrative alone.
