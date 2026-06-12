# 2B-2 result:
- X925 L2 clean hit: 1.23ns / 4.8c
- X925 L2 tail: 1.37ns / 5.3c @512KB
- X925 L2→L3 boundary: 512~640KB
- X925 L3 near: 2.95~3.13ns / 11.5~12.2c
- C0-X925 distributed L3: 4.5~4.7ns @5~8MB
- C1-X925 distributed L3: 4.3~4.4ns @5~8MB
- No sharp SLC cliff on X925 up to 20MB

# Phase 2B-3: A725-visible SLC/LLC Effective Capacity

## Environment

- Platform: GB10
- Tool: chase_pmu v2.7.3
- Eviction tool: evict_slc v1.2
- Date: 2026-06-11
- Cores:
  - C0-A725: cpu0
  - C1-A725: cpu10
- Memory mode: hugepage
- Warm mode: warm=5
- Cold mode: evict_slc --evict_mb=64 + chase_pmu warm=0 fr=1
- Median: 7 runs

## Warm Sweep

Range:

```text
10MB ~ 24MB, 256KB step
```

### C0-A725

| Size | Warm Latency |
|---:|---:|
| 12MB | 7.38 ns |
| 14MB | 11.93 ns |
| 16MB | 15.75 ns |
| 18MB | 30.16 ns |
| 20MB | 43.73 ns |
| 24MB | 58.57 ns |

Result:

```text
C0-A725 effective SLC/LLC warm capacity:
- low-latency SLC region : <=12.5MB
- SLC tail region        : 13~16MB
- hard boundary          : ~16MB
- DRAM-mixed onset       : 16~18MB
- DRAM-dominant warm     : >=20MB
```

### C1-A725

| Size | Warm Latency |
|---:|---:|
| 12MB | 6.79 ns |
| 14MB | 8.70 ns |
| 16MB | 11.29 ns |
| 18MB | 12.37 ns |
| 20MB | 16.36 ns |
| 24MB | 27.32 ns |

Result:

```text
C1-A725 effective SLC/LLC warm capacity:
- low-latency SLC region : <=14MB
- SLC tail region        : 14~20MB
- hard boundary          : ~20MB
- DRAM-mixed onset       : >=20MB
- fully DRAM-dominant    : not reached by 24MB warm sweep
```

## Cold Validation

### Cold Results

| Size | C0-A725 Cold | C1-A725 Cold |
|---:|---:|---:|
| 12MB | 70.90 ns | 61.21 ns |
| 14MB | 79.73 ns | 69.28 ns |
| 16MB | 80.48 ns | 67.61 ns |
| 18MB | 86.45 ns | 76.46 ns |
| 20MB | 94.71 ns | 80.27 ns |
| 24MB | 101.49 ns | 90.43 ns |

Validation:

```text
Cold latencies are 3x~10x higher than warm latencies.
evict_slc --evict_mb=64 is effective for SLC/L3 eviction validation.
```

## Final Baseline

```text
A725-visible SLC/LLC effective warm capacity:
- C0-A725: ~16MB
- C1-A725: ~20MB

These are pointer-chase effective capacities, not physical cache-size claims.
```

## Notes

- C1-A725 is consistently faster than C0-A725 in both warm and cold paths.
- C1 advantage is likely due to topology, slice affinity, or system-noise difference.
- Do not interpret the measured boundary as direct physical SLC capacity.

# Phase 2B-4: DRAM HP Cold/Warm Baseline

## Environment

- Platform: GB10
- Tool: chase_pmu v2.7.3
- Eviction tool: evict_slc v1.2
- Date: 2026-06-11
- Mode: hugepage
- Cold mode: evict_slc --evict_mb=64 + chase_pmu warm=0 fr=1
- Warm mode: chase_pmu warm=5 fr=1
- Median: 7 runs

## Cores

| Label | CPU |
|---|---:|
| C0-A725 | cpu0 |
| C1-A725 | cpu10 |
| C0-X925 | cpu5 |
| C1-X925 | cpu15 |

## Sizes

```text
32MB, 48MB, 64MB, 96MB, 128MB
```

## Cold DRAM Baseline

| Size | C0-A725 | C1-A725 | C0-X925 | C1-X925 |
|---:|---:|---:|---:|---:|
| 32MB | 110.27 ns | 102.46 ns | 89.65 ns | 77.29 ns |
| 48MB | 118.25 ns | 112.91 ns | 99.83 ns | 86.26 ns |
| 64MB | 120.67 ns | 116.65 ns | 103.86 ns | 94.53 ns |
| 96MB | 123.77 ns | 122.38 ns | 110.05 ns | 102.30 ns |
| 128MB | 125.09 ns | 123.51 ns | 112.08 ns | 104.16 ns |

## Warm Large-Working-Set Baseline

| Size | C0-A725 | C1-A725 | C0-X925 | C1-X925 |
|---:|---:|---:|---:|---:|
| 32MB | 69.67 ns | 57.92 ns | 4.84 ns | 4.28 ns |
| 48MB | 89.47 ns | 81.51 ns | 27.08 ns | 27.35 ns |
| 64MB | 98.05 ns | 92.15 ns | 55.99 ns | 49.44 ns |
| 96MB | 109.76 ns | 104.17 ns | 73.66 ns | 70.22 ns |
| 128MB | 115.24 ns | 110.26 ns | 85.36 ns | 81.58 ns |

## Final Baseline

```text
Cold DRAM pointer-chase envelope:
- C0-A725: 110~125 ns
- C1-A725: 102~124 ns
- C0-X925: 90~112 ns
- C1-X925: 77~104 ns

Warm large-WS envelope:
- C0-A725: 70~115 ns
- C1-A725: 58~110 ns
- C0-X925: cache-dominated at 32MB, DRAM-mixed by 64~128MB
- C1-X925: cache-dominated at 32MB, DRAM-mixed by 64~128MB
```

## Key Observations

```text
1. A725 warm path converges toward cold DRAM by 96~128MB.
2. X925 warm path remains cache/SLC dominated at 32MB.
3. X925 warm 64~128MB is DRAM-mixed but still below cold.
4. X925 cold ns latency is lower than A725, but cycles should be interpreted with core frequency.
5. C1 path is consistently faster than C0, especially on X925.
```

## Relation to Phase 2B-3

```text
2B-3 A725 24MB cold:
- C0-A725: 101.49ns
- C1-A725: 90.43ns

2B-4 A725 32MB+ cold:
- C0-A725: 110.27ns @32MB -> 125.09ns @128MB
- C1-A725: 102.46ns @32MB -> 123.51ns @128MB

This confirms that Phase 2B-3 SLC overflow cold validation aligns with the large-working-set DRAM envelope.
```

## Notes

```text
- These are pointer-chase effective latencies, not peak bandwidth.
- warm=0 includes init_chain fill effects and should be interpreted as cold/mixed DRAM path.
- X925 32MB warm behavior must not be interpreted as physical 32MB L3 claim.
- Physical cache/SLC size should not be inferred directly from this benchmark alone.
```
# Phase 2B-5: Same-chain Cross-core Migration Baseline

## Environment

- Platform: GB10
- Date: 2026-06-11
- Tool: `chase_migrate v1.0`
- Runner: `section10_migrate.sh`
- Mode: 2MB hugepage
- Hugepage mode: `--hugepage 1 --strict-hugepage 1`
- Warm source passes: `warm_src=5`
- Measurement rounds: `measure_rounds=1`
- Median: 7 runs
- Sleep after migration: `sleep_us=0`

## Topology

| Cluster | CPU | Core Type | L1D | L2 | Shared L3 | Max Freq |
|---|---|---|---:|---:|---:|---:|
| C0 | cpu0-4 | A725 | 64KB, 4-way, 256 sets | 512KB, 8-way, 1024 sets | 8MB, 16-way, 8192 sets | 2808 MHz |
| C0 | cpu5-9 | X925 | 64KB, 4-way, 256 sets | 2MB, 8-way, 4096 sets | 8MB, 16-way, 8192 sets | 3900 MHz |
| C1 | cpu10-14 | A725 | 64KB, 4-way, 256 sets | 512KB, 8-way, 1024 sets | 16MB, 16-way, 16384 sets | 2808 MHz |
| C1 | cpu15-19 | X925 | 64KB, 4-way, 256 sets | 2MB, 8-way, 4096 sets | 16MB, 16-way, 16384 sets | 3900 MHz |

Additional shared hierarchy:

```text
SLC: 16MB shared
DRAM: 128GB unified memory, measured platform bandwidth 273GB/s
```

## Methodology

The migration test measures the same pointer-chase chain across source and destination CPUs.

```text
bind(src_cpu)
  -> allocate hugepage buffer
  -> build random pointer chain on src_cpu
  -> warm source with 5 passes
  -> measure src_latency on src_cpu
bind(dst_cpu)
  -> measure migrate_latency on dst_cpu using the same chain
```

Definitions:

```text
src_latency:
  Latency measured on the source CPU after source warm.

migrate_latency:
  Latency measured on the destination CPU after process migration.

migrate_penalty:
  migrate_latency - src_latency
```

Important note:

```text
The migration measurement is performed after source warm + source local measurement.
Therefore it represents a best-case source-resident state before migration.
If the destination still observes cold-like latency, the source-resident cache state is not effectively preserved as a low-latency destination-visible state.
```

## Tested Cores

| Label | CPU |
|---|---:|
| C0-A725 | cpu0 |
| C0-X925 | cpu5 |
| C1-A725 | cpu10 |
| C1-X925 | cpu15 |

## Tested Sizes

```text
512KB, 2MB, 8MB, 16MB, 32MB, 64MB
```

## Local Baseline

| Size | C0-A725 | C0-X925 | C1-A725 | C1-X925 |
|---:|---:|---:|---:|---:|
| 512KB | 5.41 ns | 1.41 ns | 5.60 ns | 1.41 ns |
| 2MB | 3.59 ns | 3.49 ns | 3.56 ns | 3.44 ns |
| 8MB | 3.84 ns | 5.24 ns | 3.77 ns | 4.91 ns |
| 16MB | 22.02 ns | 4.32 ns | 10.48 ns | 4.04 ns |
| 32MB | 77.21 ns | 4.67 ns | 62.46 ns | 4.66 ns |
| 64MB | 101.66 ns | 56.51 ns | 96.41 ns | 48.93 ns |

## Migration Latency Baseline

### Cross-cluster Same-type Migration

| Size | C0A725->C1A725 | C1A725->C0A725 | C0X925->C1X925 | C1X925->C0X925 |
|---:|---:|---:|---:|---:|
| 512KB | 55.52 ns | 53.94 ns | 52.46 ns | 49.14 ns |
| 2MB | 63.66 ns | 71.85 ns | 66.28 ns | 68.10 ns |
| 8MB | 74.95 ns | 87.60 ns | 60.31 ns | 65.09 ns |
| 16MB | 88.01 ns | 91.05 ns | 66.84 ns | 75.98 ns |
| 32MB | 111.01 ns | 113.58 ns | 87.84 ns | 95.63 ns |
| 64MB | 118.80 ns | 122.82 ns | 103.42 ns | 108.35 ns |

### Same-cluster A725/X925 Migration

| Size | C0A725->C0X925 | C0X925->C0A725 | C1A725->C1X925 | C1X925->C1A725 |
|---:|---:|---:|---:|---:|
| 512KB | 12.49 ns | 24.32 ns | 11.42 ns | 20.61 ns |
| 2MB | 13.49 ns | 39.82 ns | 12.12 ns | 31.25 ns |
| 8MB | 20.90 ns | 30.37 ns | 14.11 ns | 25.85 ns |
| 16MB | 56.10 ns | 60.43 ns | 18.44 ns | 22.81 ns |
| 32MB | 92.04 ns | 98.11 ns | 74.22 ns | 103.53 ns |
| 64MB | 105.46 ns | 118.37 ns | 95.44 ns | 101.62 ns |

## Migration Penalty

### Cross-cluster Same-type Penalty

| Size | C0A725->C1A725 | C1A725->C0A725 | C0X925->C1X925 | C1X925->C0X925 |
|---:|---:|---:|---:|---:|
| 512KB | 51.21 ns | 49.92 ns | 51.14 ns | 47.77 ns |
| 2MB | 60.08 ns | 68.32 ns | 61.96 ns | 64.59 ns |
| 8MB | 71.10 ns | 83.74 ns | 55.06 ns | 60.02 ns |
| 16MB | 60.03 ns | 80.03 ns | 62.51 ns | 71.89 ns |
| 32MB | 38.25 ns | 53.15 ns | 83.25 ns | 91.27 ns |
| 64MB | 15.03 ns | 30.33 ns | 48.39 ns | 60.91 ns |

### Same-cluster A725/X925 Penalty

| Size | C0A725->C0X925 | C0X925->C0A725 | C1A725->C1X925 | C1X925->C1A725 |
|---:|---:|---:|---:|---:|
| 512KB | 8.09 ns | 22.98 ns | 7.24 ns | 19.27 ns |
| 2MB | 9.71 ns | 36.48 ns | 8.58 ns | 27.87 ns |
| 8MB | 16.86 ns | 24.86 ns | 10.36 ns | 20.82 ns |
| 16MB | 37.43 ns | 56.22 ns | 7.10 ns | 18.77 ns |
| 32MB | 15.01 ns | 92.53 ns | 12.19 ns | 98.79 ns |
| 64MB | 2.56 ns | 62.33 ns | -1.16 ns | 55.29 ns |

## Destination Cold Ratio

Definition:

```text
R_cold = migrate_latency / destination_cold_latency
```

2B-4 destination cold baseline:

| Destination | 32MB Cold | 64MB Cold |
|---|---:|---:|
| C0-A725 | 110.27 ns | 120.67 ns |
| C1-A725 | 102.46 ns | 116.65 ns |
| C0-X925 | 89.65 ns | 103.86 ns |
| C1-X925 | 77.29 ns | 94.53 ns |

Classification:

```text
R_cold < 0.40     : strong local/shared-cache benefit
0.40 ~ 0.75       : remote/shared/SLC mixed
0.75 ~ 0.95       : DRAM-mixed
0.95 ~ 1.10       : cold-equivalent
R_cold > 1.10     : worse-than-cold / coherence overhead / noise
```

### 32MB

| Path | Destination | MigLat | Dst Cold | R_cold | Class |
|---|---|---:|---:|---:|---|
| C0A725->C1A725 | C1-A725 | 111.01 | 102.46 | 1.08 | cold-equivalent |
| C1A725->C0A725 | C0-A725 | 113.58 | 110.27 | 1.03 | cold-equivalent |
| C0X925->C1X925 | C1-X925 | 87.84 | 77.29 | 1.14 | worse-than-cold |
| C1X925->C0X925 | C0-X925 | 95.63 | 89.65 | 1.07 | cold-equivalent |
| C0A725->C0X925 | C0-X925 | 92.04 | 89.65 | 1.03 | cold-equivalent |
| C0X925->C0A725 | C0-A725 | 98.11 | 110.27 | 0.89 | DRAM-mixed |
| C1A725->C1X925 | C1-X925 | 74.22 | 77.29 | 0.96 | cold-equivalent |
| C1X925->C1A725 | C1-A725 | 103.53 | 102.46 | 1.01 | cold-equivalent |

### 64MB

| Path | Destination | MigLat | Dst Cold | R_cold | Class |
|---|---|---:|---:|---:|---|
| C0A725->C1A725 | C1-A725 | 118.80 | 116.65 | 1.02 | cold-equivalent |
| C1A725->C0A725 | C0-A725 | 122.82 | 120.67 | 1.02 | cold-equivalent |
| C0X925->C1X925 | C1-X925 | 103.42 | 94.53 | 1.09 | cold-equivalent |
| C1X925->C0X925 | C0-X925 | 108.35 | 103.86 | 1.04 | cold-equivalent |
| C0A725->C0X925 | C0-X925 | 105.46 | 103.86 | 1.02 | cold-equivalent |
| C0X925->C0A725 | C0-A725 | 118.37 | 120.67 | 0.98 | cold-equivalent |
| C1A725->C1X925 | C1-X925 | 95.44 | 94.53 | 1.01 | cold-equivalent |
| C1X925->C1A725 | C1-A725 | 101.62 | 116.65 | 0.87 | DRAM-mixed |

## Final Findings

```text
1. Local same-core baseline is stable:
   local second-measurement penalty is mostly within +/-1ns.

2. Cross-cluster migration destroys low-latency cache residency:
   512KB~16MB local latency is 1~28ns,
   but cross-cluster migration latency becomes 49~91ns.

3. Same-cluster migration is much faster than cross-cluster migration:
   C0 A725->X925 512KB~8MB: 12~21ns.
   C1 A725->X925 512KB~16MB: 11~18ns.

4. C1 same-cluster locality is better than C0:
   C0 A725<->X925 16MB: 56~60ns.
   C1 A725<->X925 16MB: 18~23ns.

5. Migration-visible locality boundary:
   C0 same-cluster: between 8MB and 16MB.
   C1 same-cluster: between 16MB and 32MB.

6. 64MB migration is destination-cold-envelope dominated:
   most paths have R_cold = 0.98~1.09.

7. X925 32MB local cache-dominated behavior does not survive migration:
   local X925 32MB: ~4.7ns.
   cross-cluster migrated X925 32MB: ~88~96ns.
```

## Notes

```text
- These are pointer-chase effective latencies.
- These data should not be interpreted as direct physical cache-size claims.
- The observed C0/C1 difference is consistent with the known shared L3 topology:
  C0 shared L3 = 8MB, C1 shared L3 = 16MB.
- Exact coherency protocol, slice mapping, and snoop-filter behavior require PMU/coherency counter evidence.
- A725 and X925 have different maximum frequencies:
  A725 = 2808MHz, X925 = 3900MHz.
  Therefore ns latency and cycles latency must both be considered.
```
