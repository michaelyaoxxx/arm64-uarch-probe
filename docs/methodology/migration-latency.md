# Migration Latency Measurement Methodology

## Probe

`chase_migrate` v1.0 uses CPU-affinity + pointer chasing.

## Scenarios

- Same-core (local): baseline measurement on a single CPU
- Same-cluster: migration within C0 or C1
- Cross-cluster: migration from C0 to C1 or reverse
- Cross-core-type: migration between A725 and X925

## Asymmetric Penalty

Migration penalties are asymmetric:
- X925 to A725: typically higher (moving from fast core to slow core)
- A725 to X925: typically lower (moving from slow core to fast core)

## Sizes

6 working-set sizes from L2-resident (512 KiB) to DRAM (64 MiB).

## Page Policy

Hugepage (2 MiB) required for migration stability.

## Units

Migration penalty in nanoseconds (ns).
