# CPU Topology

## Core Distribution

- 20 cores total
- 2 clusters

| Cluster | CPUs |
|--------|------|
| C0 | 0–9 |
| C1 | 10–19 |

---

## Core Types

| Type | Count |
|------|------|
| A725 | 10 |
| X925 | 10 |

---

## Frequency

| Core | Max Freq |
|-----|----------|
| A725 | 2.8 GHz |
| X925 | 3.9 GHz |

## summary

| Cluster | CPU      | 核型 | L1D  | L1D              | L2          | L2                | L3               | L3                  | Max Freq       |
| ------- | -------- | ---- | ---- | ---------------- | ----------- | ----------------- | ---------------- | ------------------- | -------------- |
| C0      | cpu0-4   | A725 | 64KB | 4-way / 256-sets | 512KB       | 8-way / 1024-sets | 8MB (shared C0)  | 16-way / 8192-sets  | 2808 MHz       |
| C0      | cpu5-9   | X925 | 64KB | 4-way / 256-sets | 2MB         | 8-way / 4096-sets | 8MB (shared C0)  | 16-way / 8192-sets  | 3900 MHz       |
| C1      | cpu10-14 | A725 | 64KB | 4-way / 256-sets | 512KB       | 8-way / 1024-sets | 16MB (shared C1) | 16-way / 16384-sets | 2808 MHz       |
| C1      | cpu15-19 | X925 | 64KB | 4-way / 256-sets | 2MB         | 8-way / 4096-sets | 16MB (shared C1) | 16-way / 16384-sets | 3900 MHz       |
| —       | —        | —    | SLC  | —                | 16MB shared | —                 | DRAM 128GB       | —                   | 273 GB/s       |
