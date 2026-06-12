---
data_ref: data/20260610_v2.7.3/raw/run_20260610_215517.txt
tool_ver: chase_pmu v2.7.3
date: 2026-06-10
status: SUPERSEDED_PARTIAL
note: |
  C1-A725 warm 数据（8MB/12MB/16MB）已被 hugepage+隔离 基准修正。
  旧值（4K page 多核未隔离）：8MB=6.52ns 12MB=10.47ns 16MB=16.97ns
  新值（hugepage 单核隔离）：  8MB=3.82ns 12MB=6.85ns  16MB=12.91ns
  其余 cluster 数据（C0-X925 / C0-A725 / C1-X925）仍有效。
---

# Memory / Cache Latency Notes

## Scope
This document records latency observations collected from:

- `runner/run_pmu_v2.7.3.sh`
- `results/v2.7.3/raw/run_20260610_215517.txt`
- PMU single-pass verification on `cpu5` (`armv8_pmuv3_1`)

---

## Important: measurement modes are different

### 1) warm
- explicit warm passes
- multi-round timing
- median-of-3
- measures steady-state residency latency

### 2) cold/dbl-evict
- v2.7.3 flow:
  - `evict -> warm=1 -> measure`
- only valid if `size <= local L3`
- approximates local-L3 path after forcing SLC clean

### 3) cold/warm0
- flow:
  - `evict -> measure(warm=0)`
- **not absolute cold**
- must be interpreted as:
  - `init_chain residue + partial SLC hits`

---

## Latest runner medians (2026-06-10)

### C0-X925 (cpu5, L2=2MB, L3=8MB)

#### warm
- 1MB  -> 4.11 ns
- 2MB  -> 5.31 ns
- 4MB  -> 5.93 ns
- 6MB  -> 6.03 ns
- 8MB  -> 5.87 ns

#### cold/dbl-evict
- 4MB  -> 15.78 ns
- 6MB  -> 19.64 ns
- 8MB  -> 29.17 ns

#### cold/warm0
- 10MB -> 48.22 ns
- 12MB -> 54.33 ns
- 16MB -> 69.27 ns
- 20MB -> 77.06 ns
- 32MB -> 99.07 ns
- 64MB -> 112.54 ns

---

### C0-A725 (cpu0, L2=512KB, L3=8MB)

#### warm
- 1MB  -> 5.37 ns
- 4MB  -> 7.31 ns
- 6MB  -> 6.61 ns
- 8MB  -> 6.52 ns

#### cold/dbl-evict
- 4MB  -> 27.58 ns
- 6MB  -> 36.49 ns
- 8MB  -> 53.53 ns

#### cold/warm0
- 10MB -> 66.43 ns
- 12MB -> 72.05 ns
- 16MB -> 88.18 ns
- 20MB -> 100.03 ns
- 32MB -> 119.95 ns
- 64MB -> 134.62 ns

---

### C1-X925 (cpu15, L2=2MB, L3=16MB)

#### warm
- 1MB  -> 3.94 ns
- 2MB  -> 5.12 ns
- 4MB  -> 5.80 ns
- 8MB  -> 5.59 ns
- 12MB -> 5.61 ns
- 16MB -> 5.07 ns

#### cold/dbl-evict
- 8MB  -> 15.70 ns
- 12MB -> 22.35 ns
- 16MB -> 32.09 ns

#### cold/warm0
- 18MB -> 43.56 ns
- 20MB -> 47.53 ns
- 24MB -> 58.66 ns
- 28MB -> 65.91 ns
- 32MB -> 75.10 ns
- 64MB -> 102.80 ns

---

### C1-A725 (cpu10, L2=512KB, L3=16MB)

#### warm
- 1MB  -> 5.32 ns
- 4MB  -> 7.64 ns
- 8MB  -> 6.52 ns
- 12MB -> 10.47 ns
- 16MB -> 16.97 ns

#### cold/dbl-evict
- 8MB  -> 28.84 ns
- 12MB -> 37.93 ns
- 16MB -> 50.85 ns

#### cold/warm0
- 18MB -> 60.26 ns
- 20MB -> 69.67 ns
- 24MB -> 86.58 ns
- 28MB -> 93.45 ns
- 32MB -> 101.40 ns
- 64MB -> 127.76 ns

---

## PMU single-pass latency buckets (cpu5 / X925)

### PMU-observed values
- 4MB   -> 17.49 ns
- 8MB   -> 32.08 ns
- 16MB  -> 65.74 ns
- 128MB -> 114.43 ns

### Interpretation
- `~17–32 ns` : local-L3 regime / boundary
- `~65 ns`    : SLC regime
- `~114 ns`   : DRAM regime

---

## Key observations

### X925
- warm steady-state local-cache plateau is very flat:
  - roughly `5–6 ns`
- local-L3 path bucket under PMU lands around:
  - `~17–32 ns`
- SLC bucket under PMU / warm0 transition lands around:
  - `~65–70 ns`
- DRAM tail lands around:
  - `~103–114 ns`

### A725
- warm steady-state values are consistently above X925
- C1-A725 shows visible growth already at 12MB and 16MB
- A725 cold-path and warm0 tails are materially slower than X925
- A725 L2 boundary is not yet scanned finely enough (current runner uses MB granularity)

---

## Caveats

1. `warm=0` is not absolute cold
2. `clflush=1` is only flush-to-PoC, not guaranteed flush-beyond-L3/SLC
3. `cold/warm0` is a mixed state, not pure DRAM
4. `dbl-evict` numbers are only meaningful when `size <= local L3`
5. warm steady-state latency must not be directly merged with single-pass PMU path-latency

## Revision History

| Date       | Cluster  | Metric | Old Value | New Value | Reason |
|------------|----------|--------|-----------|-----------|--------|
| 2026-06-10 | C1-A725  | warm 8MB  | 6.52 ns | 3.82 ns | hugepage+单核隔离，BUG-06 Layer2修正 |
| 2026-06-10 | C1-A725  | warm 12MB | 10.47 ns | 6.85 ns | 同上 |
| 2026-06-10 | C1-A725  | warm 16MB | 16.97 ns | 12.91 ns | 同上 |
