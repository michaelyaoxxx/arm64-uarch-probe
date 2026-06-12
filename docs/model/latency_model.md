## A725 SLC/LLC Effective Capacity Model

### C0-A725

```text
size <= 12.5MB:
  SLC-near hit: 5.3~7.9ns

13MB <= size <= 16MB:
  SLC tail: 9.2~15.8ns

16MB < size < 18MB:
  SLC overflow transition: 17.7~26.0ns

size >= 18MB:
  DRAM-mixed/dominant: 30~60ns
```

### C1-A725

```text
size <= 14MB:
  SLC-near hit: 4.7~8.7ns

14MB <= size <= 20MB:
  SLC tail: 9.4~16.4ns

size >= 20MB:
  DRAM-mixed: 16~27ns up to 24MB
```

### Cold Path

```text
C0-A725 cold/rand+warm0:
  12~24MB: 70.9~101.5ns

C1-A725 cold/rand+warm0:
  12~24MB: 61.2~90.4ns
```
## DRAM Pointer-Chase Latency Envelope

### Cold DRAM Envelope

```text
C0-A725:
  32~128MB cold: 110~125ns

C1-A725:
  32~128MB cold: 102~124ns

C0-X925:
  32~128MB cold: 90~112ns

C1-X925:
  32~128MB cold: 77~104ns
```

### Warm Large-Working-Set Envelope

```text
C0-A725:
  32MB: 69.67ns
  64MB: 98.05ns
  128MB: 115.24ns

C1-A725:
  32MB: 57.92ns
  64MB: 92.15ns
  128MB: 110.26ns

C0-X925:
  32MB: 4.84ns  cache-dominated
  48MB: 27.08ns transition
  64MB: 55.99ns DRAM-mixed
  128MB: 85.36ns DRAM-mixed

C1-X925:
  32MB: 4.28ns  cache-dominated
  48MB: 27.35ns transition
  64MB: 49.44ns DRAM-mixed
  128MB: 81.58ns DRAM-mixed
```
## Phase 2B-5: Same-chain Migration Latency Model

### Platform Topology

| Cluster | CPU | Core Type | L2 | Shared L3 | Max Freq |
|---|---|---|---:|---:|---:|
| C0 | cpu0-4 | A725 | 512KB/core | 8MB shared | 2808MHz |
| C0 | cpu5-9 | X925 | 2MB/core | 8MB shared | 3900MHz |
| C1 | cpu10-14 | A725 | 512KB/core | 16MB shared | 2808MHz |
| C1 | cpu15-19 | X925 | 2MB/core | 16MB shared | 3900MHz |

Additional hierarchy:

```text
L1D: 64KB/core, 4-way, 256 sets
SLC: 16MB shared
DRAM: 128GB, measured platform bandwidth 273GB/s
```

### Methodology

```text
bind(src_cpu)
  -> allocate hugepage buffer
  -> build random pointer-chain on src_cpu
  -> warm source cache with 5 passes
  -> measure src_latency
bind(dst_cpu)
  -> measure same chain on dst_cpu
```

Definitions:

```text
L_src:
  source local latency after warm.

L_mig:
  destination latency after migration.

Penalty:
  L_mig - L_src

R_cold:
  L_mig / L_dst_cold
```

Rendered formulas:

$$
L_\text{penalty} = L_\text{mig} - L_\text{src}
\tag{1}
$$

$$
R_\text{cold} = \frac{L_\text{mig}}{L_\text{dst,cold}}
\tag{2}
$$

### Local Same-core Latency

| Size | C0-A725 | C0-X925 | C1-A725 | C1-X925 |
|---:|---:|---:|---:|---:|
| 512KB | 5.41ns | 1.41ns | 5.60ns | 1.41ns |
| 2MB | 3.59ns | 3.49ns | 3.56ns | 3.44ns |
| 8MB | 3.84ns | 5.24ns | 3.77ns | 4.91ns |
| 16MB | 22.02ns | 4.32ns | 10.48ns | 4.04ns |
| 32MB | 77.21ns | 4.67ns | 62.46ns | 4.66ns |
| 64MB | 101.66ns | 56.51ns | 96.41ns | 48.93ns |

Model interpretation:

```text
A725:
  C0:
    <=8MB: cache-dominated
    16MB : transition
    32MB+: DRAM-mixed/dominant

  C1:
    <=16MB: stronger cache/shared-domain behavior than C0
    32MB+ : DRAM-mixed/dominant

X925:
  <=32MB: cache-dominated local warm path
  64MB  : DRAM-mixed
```

### Cross-cluster Migration Latency

| Size | C0A725->C1A725 | C1A725->C0A725 | C0X925->C1X925 | C1X925->C0X925 |
|---:|---:|---:|---:|---:|
| 512KB | 55.52ns | 53.94ns | 52.46ns | 49.14ns |
| 2MB | 63.66ns | 71.85ns | 66.28ns | 68.10ns |
| 8MB | 74.95ns | 87.60ns | 60.31ns | 65.09ns |
| 16MB | 88.01ns | 91.05ns | 66.84ns | 75.98ns |
| 32MB | 111.01ns | 113.58ns | 87.84ns | 95.63ns |
| 64MB | 118.80ns | 122.82ns | 103.42ns | 108.35ns |

Model:

```text
Cross-cluster migration latency is high even for small working sets.

512KB~16MB:
  local latency: 1~28ns
  cross-cluster migrated latency: 49~91ns

Therefore, source private/local cache residency is not preserved as a
low-latency destination-visible state across clusters.
```

### Same-cluster A725/X925 Migration Latency

| Size | C0A725->C0X925 | C0X925->C0A725 | C1A725->C1X925 | C1X925->C1A725 |
|---:|---:|---:|---:|---:|
| 512KB | 12.49ns | 24.32ns | 11.42ns | 20.61ns |
| 2MB | 13.49ns | 39.82ns | 12.12ns | 31.25ns |
| 8MB | 20.90ns | 30.37ns | 14.11ns | 25.85ns |
| 16MB | 56.10ns | 60.43ns | 18.44ns | 22.81ns |
| 32MB | 92.04ns | 98.11ns | 74.22ns | 103.53ns |
| 64MB | 105.46ns | 118.37ns | 95.44ns | 101.62ns |

Model:

```text
C0 same-cluster:
  512KB~8MB:
    A725->X925: 12~21ns
    X925->A725: 24~40ns
  16MB:
    56~60ns, already high-latency mixed
  Boundary:
    between 8MB and 16MB

C1 same-cluster:
  512KB~16MB:
    A725->X925: 11~18ns
    X925->A725: 20~23ns
  32MB:
    transition to cold-like path
  Boundary:
    between 16MB and 32MB
```

### Destination Cold Ratio

2B-4 destination cold baseline:

| Destination | 32MB Cold | 64MB Cold |
|---|---:|---:|
| C0-A725 | 110.27ns | 120.67ns |
| C1-A725 | 102.46ns | 116.65ns |
| C0-X925 | 89.65ns | 103.86ns |
| C1-X925 | 77.29ns | 94.53ns |

Classification:

| R_cold | Class |
|---:|---|
| < 0.40 | strong local/shared-cache benefit |
| 0.40~0.75 | remote/shared/SLC mixed |
| 0.75~0.95 | DRAM-mixed |
| 0.95~1.10 | cold-equivalent |
| > 1.10 | worse-than-cold / coherence overhead / noise |

#### 32MB

| Path | Destination | R_cold | Class |
|---|---|---:|---|
| C0A725->C1A725 | C1-A725 | 1.08 | cold-equivalent |
| C1A725->C0A725 | C0-A725 | 1.03 | cold-equivalent |
| C0X925->C1X925 | C1-X925 | 1.14 | worse-than-cold |
| C1X925->C0X925 | C0-X925 | 1.07 | cold-equivalent |
| C0A725->C0X925 | C0-X925 | 1.03 | cold-equivalent |
| C0X925->C0A725 | C0-A725 | 0.89 | DRAM-mixed |
| C1A725->C1X925 | C1-X925 | 0.96 | cold-equivalent |
| C1X925->C1A725 | C1-A725 | 1.01 | cold-equivalent |

#### 64MB

| Path | Destination | R_cold | Class |
|---|---|---:|---|
| C0A725->C1A725 | C1-A725 | 1.02 | cold-equivalent |
| C1A725->C0A725 | C0-A725 | 1.02 | cold-equivalent |
| C0X925->C1X925 | C1-X925 | 1.09 | cold-equivalent |
| C1X925->C0X925 | C0-X925 | 1.04 | cold-equivalent |
| C0A725->C0X925 | C0-X925 | 1.02 | cold-equivalent |
| C0X925->C0A725 | C0-A725 | 0.98 | cold-equivalent |
| C1A725->C1X925 | C1-X925 | 1.01 | cold-equivalent |
| C1X925->C1A725 | C1-A725 | 0.87 | DRAM-mixed |

### Final Migration Model

```text
1. Same-core:
   second measurement is stable, with penalty mostly within +/-1ns.

2. Cross-cluster:
   source cache residency does not survive as low-latency state.
   512KB~16MB migration immediately enters 49~91ns path.

3. Same-cluster:
   shorter path exists for A725<->X925 migration.
   Direction is asymmetric:
     A725->X925 is faster than X925->A725.

4. C1 vs C0:
   C1 same-cluster has a larger migration-visible locality domain.
   C0 boundary: 8MB~16MB.
   C1 boundary: 16MB~32MB.

5. 32MB:
   mostly destination-cold-equivalent.
   X925 local 32MB low latency does not survive migration.

6. 64MB:
   destination-cold-envelope dominated for nearly all paths.
```

### Frequency-aware Notes

```text
A725 max frequency: 2808MHz
X925 max frequency: 3900MHz

Approximate cycle conversion:
  A725 cycles = ns * 2.808
  X925 cycles = ns * 3.900

Do not compare only ns latency across A725 and X925.
For microarchitecture modeling, keep both:
  - user-visible latency in ns
  - core pipeline stall cost in cycles
```

Example:

```text
C1-X925 local 32MB:
  4.66ns * 3.9GHz ~= 18 cycles

C1-A725 local 32MB:
  62.46ns * 2.808GHz ~= 175 cycles
```

This highlights that X925 32MB local warm behavior is a very strong cache-dominated path,
but it is not migration-stable across clusters.

### Summary Tablet
 Label                                  SrcCPU   DstCPU     Size  Mode               SrcLat       MigLat      Penalty
  ------------------------------------ -------- -------- --------  ------------ ------------ ------------ ------------
  C0-A725_local_512KB                         0        0    512KB  local              4.45 ns       5.41 ns       0.91 ns
  C0-X925_local_512KB                         5        5    512KB  local              1.35 ns       1.41 ns       0.04 ns
  C1-A725_local_512KB                        10       10    512KB  local              4.14 ns       5.60 ns       0.73 ns
  C1-X925_local_512KB                        15       15    512KB  local              1.37 ns       1.41 ns       0.07 ns
  C0-A725_local_2048KB                        0        0   2048KB  local              3.58 ns       3.59 ns       0.02 ns
  C0-X925_local_2048KB                        5        5   2048KB  local              3.41 ns       3.49 ns       0.10 ns
  C1-A725_local_2048KB                       10       10   2048KB  local              3.54 ns       3.56 ns       0.01 ns
  C1-X925_local_2048KB                       15       15   2048KB  local              3.35 ns       3.44 ns       0.09 ns
  C0-A725_local_8192KB                        0        0   8192KB  local              3.85 ns       3.84 ns      -0.02 ns
  C0-X925_local_8192KB                        5        5   8192KB  local              5.38 ns       5.24 ns      -0.13 ns
  C1-A725_local_8192KB                       10       10   8192KB  local              3.77 ns       3.77 ns       0.00 ns
  C1-X925_local_8192KB                       15       15   8192KB  local              5.08 ns       4.91 ns      -0.19 ns
  C0-A725_local_16384KB                       0        0  16384KB  local             25.07 ns      22.02 ns      -1.86 ns
  C0-X925_local_16384KB                       5        5  16384KB  local              4.23 ns       4.32 ns      -0.00 ns
  C1-A725_local_16384KB                      10       10  16384KB  local             10.44 ns      10.48 ns      -0.06 ns
  C1-X925_local_16384KB                      15       15  16384KB  local              4.06 ns       4.04 ns       0.02 ns
  C0-A725_local_32768KB                       0        0  32768KB  local             78.00 ns      77.21 ns      -0.87 ns
  C0-X925_local_32768KB                       5        5  32768KB  local              4.82 ns       4.67 ns      -0.15 ns
  C1-A725_local_32768KB                      10       10  32768KB  local             63.97 ns      62.46 ns      -0.87 ns
  C1-X925_local_32768KB                      15       15  32768KB  local              4.70 ns       4.66 ns      -0.09 ns
  C0-A725_local_65536KB                       0        0  65536KB  local            102.46 ns     101.66 ns      -1.12 ns
  C0-X925_local_65536KB                       5        5  65536KB  local             56.63 ns      56.51 ns      -0.12 ns
  C1-A725_local_65536KB                      10       10  65536KB  local             97.82 ns      96.41 ns      -1.23 ns
  C1-X925_local_65536KB                      15       15  65536KB  local             49.37 ns      48.93 ns      -0.76 ns
  C0A725_to_C1A725_512KB                      0       10    512KB  migrate            4.46 ns      55.52 ns      51.21 ns
  C1A725_to_C0A725_512KB                     10        0    512KB  migrate            4.08 ns      53.94 ns      49.92 ns
  C0X925_to_C1X925_512KB                      5       15    512KB  migrate            1.34 ns      52.46 ns      51.14 ns
  C1X925_to_C0X925_512KB                     15        5    512KB  migrate            1.37 ns      49.14 ns      47.77 ns
  C0A725_to_C0X925_512KB                      0        5    512KB  migrate            4.43 ns      12.49 ns       8.09 ns
  C0X925_to_C0A725_512KB                      5        0    512KB  migrate            1.34 ns      24.32 ns      22.98 ns
  C1A725_to_C1X925_512KB                     10       15    512KB  migrate            4.16 ns      11.42 ns       7.24 ns
  C1X925_to_C1A725_512KB                     15       10    512KB  migrate            1.38 ns      20.61 ns      19.27 ns
  C0A725_to_C1A725_2048KB                     0       10   2048KB  migrate            3.57 ns      63.66 ns      60.08 ns
  C1A725_to_C0A725_2048KB                    10        0   2048KB  migrate            3.54 ns      71.85 ns      68.32 ns
  C0X925_to_C1X925_2048KB                     5       15   2048KB  migrate            3.67 ns      66.28 ns      61.96 ns
  C1X925_to_C0X925_2048KB                    15        5   2048KB  migrate            3.33 ns      68.10 ns      64.59 ns
  C0A725_to_C0X925_2048KB                     0        5   2048KB  migrate            3.62 ns      13.49 ns       9.71 ns
  C0X925_to_C0A725_2048KB                     5        0   2048KB  migrate            3.41 ns      39.82 ns      36.48 ns
  C1A725_to_C1X925_2048KB                    10       15   2048KB  migrate            3.55 ns      12.12 ns       8.58 ns
  C1X925_to_C1A725_2048KB                    15       10   2048KB  migrate            3.33 ns      31.25 ns      27.87 ns
  C0A725_to_C1A725_8192KB                     0       10   8192KB  migrate            3.84 ns      74.95 ns      71.10 ns
  C1A725_to_C0A725_8192KB                    10        0   8192KB  migrate            3.78 ns      87.60 ns      83.74 ns
  C0X925_to_C1X925_8192KB                     5       15   8192KB  migrate            5.38 ns      60.31 ns      55.06 ns
  C1X925_to_C0X925_8192KB                    15        5   8192KB  migrate            5.07 ns      65.09 ns      60.02 ns
  C0A725_to_C0X925_8192KB                     0        5   8192KB  migrate            3.85 ns      20.90 ns      16.86 ns
  C0X925_to_C0A725_8192KB                     5        0   8192KB  migrate            5.43 ns      30.37 ns      24.86 ns
  C1A725_to_C1X925_8192KB                    10       15   8192KB  migrate            3.79 ns      14.11 ns      10.36 ns
  C1X925_to_C1A725_8192KB                    15       10   8192KB  migrate            5.03 ns      25.85 ns      20.82 ns
  C0A725_to_C1A725_16384KB                    0       10  16384KB  migrate           27.71 ns      88.01 ns      60.03 ns
  C1A725_to_C0A725_16384KB                   10        0  16384KB  migrate           10.67 ns      91.05 ns      80.03 ns
  C0X925_to_C1X925_16384KB                    5       15  16384KB  migrate            4.24 ns      66.84 ns      62.51 ns
  C1X925_to_C0X925_16384KB                   15        5  16384KB  migrate            4.00 ns      75.98 ns      71.89 ns
  C0A725_to_C0X925_16384KB                    0        5  16384KB  migrate           19.43 ns      56.10 ns      37.43 ns
  C0X925_to_C0A725_16384KB                    5        0  16384KB  migrate            4.22 ns      60.43 ns      56.22 ns
  C1A725_to_C1X925_16384KB                   10       15  16384KB  migrate           11.01 ns      18.44 ns       7.10 ns
  C1X925_to_C1A725_16384KB                   15       10  16384KB  migrate            4.04 ns      22.81 ns      18.77 ns
  C0A725_to_C1A725_32768KB                    0       10  32768KB  migrate           72.59 ns     111.01 ns      38.25 ns
  C1A725_to_C0A725_32768KB                   10        0  32768KB  migrate           59.03 ns     113.58 ns      53.15 ns
  C0X925_to_C1X925_32768KB                    5       15  32768KB  migrate            4.93 ns      87.84 ns      83.25 ns
  C1X925_to_C0X925_32768KB                   15        5  32768KB  migrate            4.59 ns      95.63 ns      91.27 ns
  C0A725_to_C0X925_32768KB                    0        5  32768KB  migrate           77.72 ns      92.04 ns      15.01 ns
  C0X925_to_C0A725_32768KB                    5        0  32768KB  migrate            5.06 ns      98.11 ns      92.53 ns
  C1A725_to_C1X925_32768KB                   10       15  32768KB  migrate           62.43 ns      74.22 ns      12.19 ns
  C1X925_to_C1A725_32768KB                   15       10  32768KB  migrate            4.46 ns     103.53 ns      98.79 ns
  C0A725_to_C1A725_65536KB                    0       10  65536KB  migrate          103.88 ns     118.80 ns      15.03 ns
  C1A725_to_C0A725_65536KB                   10        0  65536KB  migrate           92.79 ns     122.82 ns      30.33 ns
  C0X925_to_C1X925_65536KB                    5       15  65536KB  migrate           55.96 ns     103.42 ns      48.39 ns
  C1X925_to_C0X925_65536KB                   15        5  65536KB  migrate           47.30 ns     108.35 ns      60.91 ns
  C0A725_to_C0X925_65536KB                    0        5  65536KB  migrate          102.87 ns     105.46 ns       2.56 ns
  C0X925_to_C0A725_65536KB                    5        0  65536KB  migrate           56.04 ns     118.37 ns      62.33 ns
  C1A725_to_C1X925_65536KB                   10       15  65536KB  migrate           96.10 ns      95.44 ns      -1.16 ns
  C1X925_to_C1A725_65536KB                   15       10  65536KB  migrate           49.69 ns     101.62 ns      55.29 ns
