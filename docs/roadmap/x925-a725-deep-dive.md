# X925/A725 Deep-Dive Roadmap

| Area | Current Evidence | Missing Measurement | Proposed Method | Priority |
|------|-----------------|--------------------|--------------------|----------|
| ROB capacity | None | ROB size (X925 vs A725) | Dependency-chain latency test | High |
| Decode/dispatch width | None | Instructions/cycle | NOP-sled throughput | High |
| Execution resources | None | ALU/FPU/SIMD ports | Port-saturation tests | Medium |
| Load/store behavior | None | LS bandwidth, buffers | STREAM-like pointer test | Medium |
| Branch prediction | None | BTB size, mispredict penalty | Branch-pattern tests | Medium |
| Cache/TLB | L1/L2/L3 latency | TLB reach, associativity | Page-stride tests | Medium |
| SLC hash | Latency cliff at capacity | SLC hash function | Eviction-set mapping | High |
| PMU mapping | PMU type=10 detected | Per-core event mapping | Event-sweep tests | Medium |
| Memory bandwidth | None | STREAM copy/scale/add/triad | Bandwidth probe | High |
| Frequency scaling | A725=2.8GHz X925=3.9GHz | DVFS latency impact | cpufreq sweep | Low |

## Memory Bandwidth Reference

See [Chips and Cheese: Inside NVIDIA GB10's Memory Subsystem](https://chipsandcheese.com/p/inside-nvidia-gb10s-memory-subsystem)

## Status

Phase 4 provides cache/migration latency baseline. Bandwidth, microarchitecture
deep-dive, and C&C validation are Phase 5+ work.
