# Cache Latency Measurement Methodology

## Probe

`chase_pmu` v2.7.3 uses pointer-chasing linked-list traversal.

## Working-Set Sizing

Working-set sizes are chosen relative to cache capacity:
- L1: 4 KiB to 64 KiB (within L1D = 64 KiB)
- L2: 128 KiB to 512 KiB (A725 L2 = 512 KiB) or 2 MiB (X925 L2 = 2 MiB)
- L3: 4 MiB to 16 MiB (C0 L3 = 8 MiB, C1 L3 = 16 MiB)
- SLC: 18 MiB to 32 MiB (SLC = 16 MiB + overflow)
- DRAM: 64 MiB (always misses all caches)

## Page Policies

- Default (4 KiB): standard kernel page size
- Hugepage (2 MiB): reduces TLB pressure on large working sets

## Warm vs Cold

- Warm: working set is first accessed, then re-traversed (cache-resident)
- Cold: cache is evicted between runs (cache-miss measurement)

## PMU Derivation

Latency (ns/access) = elapsed_ns / accesses

## Units

All latency values are in nanoseconds (ns). All cycle counts are in CPU cycles.
