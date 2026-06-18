# Chips and Cheese Comparison

Reference: [Inside NVIDIA GB10's Memory Subsystem](https://chipsandcheese.com/p/inside-nvidia-gb10s-memory-subsystem)

| C&C Measurement | Our Status | Classification | Notes |
|-----------------|-----------|----------------|-------|
| L1 cache latency | Covered | Agreement | chase_pmu 32K warm, 4K pages |
| L2 cache latency | Covered | Difference | C&C uses X925 only; we measure A725 + X925 |
| L3 cache latency | Covered | Difference | C0=8MiB C1=16MiB vs single pool |
| SLC latency | Covered | Methodological mismatch | C&C uses evict; we use evict_slc + cold |
| DRAM latency | Covered | Agreement | 64MiB cold |
| Cross-cluster migration | Covered | Agreement | 12 pairs x 6 sizes |
| Memory bandwidth | Not measured | Uncovered | Deferred to bandwidth probe (Phase 5+) |
| ROB capacity | Not measured | Uncovered | Deferred to deep-dive |
