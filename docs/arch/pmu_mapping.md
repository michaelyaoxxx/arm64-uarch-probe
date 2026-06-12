# PMU Mapping

| PMU | CPUs |
|-----|------|
| armv8_pmuv3_0 | 0–4, 10–14 |
| armv8_pmuv3_1 | 5–9, 15–19 |

---

## PMU信息

```
# 查看所有 PMU 实例名称
ls /sys/bus/event_source/devices/
armv8_pmuv3_0  smmuv3_pmcg_13002  smmuv3_pmcg_130a2  smmuv3_pmcg_13842  smmuv3_pmcg_138c2  smmuv3_pmcg_14962
armv8_pmuv3_1  smmuv3_pmcg_13042  smmuv3_pmcg_130c2  smmuv3_pmcg_13862  smmuv3_pmcg_138e2  software
breakpoint     smmuv3_pmcg_13062  smmuv3_pmcg_130e2  smmuv3_pmcg_13882  smmuv3_pmcg_14902  tracepoint
kprobe         smmuv3_pmcg_13082  smmuv3_pmcg_13802  smmuv3_pmcg_138a2  smmuv3_pmcg_14942  uprobe

# 列出 DSU PMU 支持的 events
perf list | grep -i "dsu\|cluster\|l3\|slc\|uncore"
  l3d_cache OR armv8_pmuv3_0/l3d_cache/              [Kernel PMU event]
  l3d_cache_allocate OR armv8_pmuv3_0/l3d_cache_allocate/[Kernel PMU event]
  l3d_cache_lmiss_rd OR armv8_pmuv3_0/l3d_cache_lmiss_rd/[Kernel PMU event]
  l3d_cache_refill OR armv8_pmuv3_0/l3d_cache_refill/[Kernel PMU event]
  btrfs:btrfs_failed_cluster_setup                   [Tracepoint event]
  btrfs:btrfs_find_cluster                           [Tracepoint event]
  btrfs:btrfs_reserve_extent_cluster                 [Tracepoint event]
  btrfs:btrfs_setup_cluster                          [Tracepoint event]
  ext4:ext4_get_implied_cluster_alloc_exit           [Tracepoint event]
  
# 或者直接查看 sysfs
ls /sys/bus/event_source/devices/ | grep -v "^armv8\|^software\|^tracepoint\|^breakpoint"
```

可以执行的命令

```
echo "=== 4MB (L3 range, iters=65536) ==="
sudo perf stat \
  -e armv8_pmuv3_1/l1d_cache_refill/,\
armv8_pmuv3_1/l1d_cache_lmiss_rd/,\
armv8_pmuv3_1/l2d_cache_refill/,\
armv8_pmuv3_1/l2d_cache_lmiss_rd/,\
armv8_pmuv3_1/l3d_cache_refill/,\
armv8_pmuv3_1/l3d_cache_lmiss_rd/ \
  -C 5 \
  taskset -c 5 ./chase_pmu 5 4 65536 2>&1

echo ""
echo "=== 8MB (L3 boundary, iters=131072) ==="
sudo perf stat \
  -e armv8_pmuv3_1/l1d_cache_refill/,\
armv8_pmuv3_1/l1d_cache_lmiss_rd/,\
armv8_pmuv3_1/l2d_cache_refill/,\
armv8_pmuv3_1/l2d_cache_lmiss_rd/,\
armv8_pmuv3_1/l3d_cache_refill/,\
armv8_pmuv3_1/l3d_cache_lmiss_rd/ \
  -C 5 \
  taskset -c 5 ./probe_single 5 8 131072 2>&1

echo ""
echo "=== 16MB (SLC range, iters=262144) ==="
sudo perf stat \
  -e armv8_pmuv3_1/l1d_cache_refill/,\
armv8_pmuv3_1/l1d_cache_lmiss_rd/,\
armv8_pmuv3_1/l2d_cache_refill/,\
armv8_pmuv3_1/l2d_cache_lmiss_rd/,\
armv8_pmuv3_1/l3d_cache_refill/,\
armv8_pmuv3_1/l3d_cache_lmiss_rd/ \
  -C 5 \
  taskset -c 5 ./probe_single 5 16 262144 2>&1

echo ""
echo "=== 128MB (DRAM range, iters=2097152) ==="
sudo perf stat \
  -e armv8_pmuv3_1/l1d_cache_refill/,\
armv8_pmuv3_1/l1d_cache_lmiss_rd/,\
armv8_pmuv3_1/l2d_cache_refill/,\
armv8_pmuv3_1/l2d_cache_lmiss_rd/,\
armv8_pmuv3_1/l3d_cache_refill/,\
armv8_pmuv3_1/l3d_cache_lmiss_rd/ \
  -C 5 \
  taskset -c 5 ./probe_single 5 128 2097152 2>&1
echo ""
echo "=== 8MB (L3 boundary, iters=131072) ==="
sudo perf stat \
  -e armv8_pmuv3_1/l1d_cache_refill/,\
armv8_pmuv3_1/l1d_cache_lmiss_rd/,\
armv8_pmuv3_1/l2d_cache_refill/,\
armv8_pmuv3_1/l2d_cache_lmiss_rd/,\
armv8_pmuv3_1/l3d_cache_refill/,\
armv8_pmuv3_1/l3d_cache_lmiss_rd/ \
  -C 5 \
  taskset -c 5 ./probe_single 5 8 131072 2>&1

echo ""
echo "=== 16MB (SLC range, iters=262144) ==="
sudo perf stat \
  -e armv8_pmuv3_1/l1d_cache_refill/,\
armv8_pmuv3_1/l1d_cache_lmiss_rd/,\
armv8_pmuv3_1/l2d_cache_refill/,\
armv8_pmuv3_1/l2d_cache_lmiss_rd/,\
armv8_pmuv3_1/l3d_cache_refill/,\
armv8_pmuv3_1/l3d_cache_lmiss_rd/ \
  -C 5 \
  taskset -c 5 ./probe_single 5 128 2097152 2>&1
=== 4MB (L3 range, iters=65536) ===
[probe] sz=4MB iters=65536 lat=17.49ns (68.2cy)

 Performance counter stats for 'CPU(s) 5':

           194,917      armv8_pmuv3_1/l1d_cache_refill/
           121,743      armv8_pmuv3_1/l1d_cache_lmiss_rd/
           186,590      armv8_pmuv3_1/l2d_cache_refill/
            66,764      armv8_pmuv3_1/l2d_cache_lmiss_rd/
             8,502      armv8_pmuv3_1/l3d_cache_refill/
             8,508      armv8_pmuv3_1/l3d_cache_lmiss_rd/

       0.002837640 seconds time elapsed


=== 8MB (L3 boundary, iters=131072) ===
[probe] sz=8MB iters=131072 lat=32.08ns (125.1cy)

 Performance counter stats for 'CPU(s) 5':

           392,892      armv8_pmuv3_1/l1d_cache_refill/
           250,735      armv8_pmuv3_1/l1d_cache_lmiss_rd/
           409,420      armv8_pmuv3_1/l2d_cache_refill/
           156,308      armv8_pmuv3_1/l2d_cache_lmiss_rd/
            43,853      armv8_pmuv3_1/l3d_cache_refill/
            43,861      armv8_pmuv3_1/l3d_cache_lmiss_rd/

       0.006524942 seconds time elapsed


=== 16MB (SLC range, iters=262144) ===
[probe] sz=16MB iters=262144 lat=65.74ns (256.4cy)

 Performance counter stats for 'CPU(s) 5':

           818,395      armv8_pmuv3_1/l1d_cache_refill/
           533,272      armv8_pmuv3_1/l1d_cache_lmiss_rd/
           826,097      armv8_pmuv3_1/l2d_cache_refill/
           353,046      armv8_pmuv3_1/l2d_cache_lmiss_rd/
           226,438      armv8_pmuv3_1/l3d_cache_refill/
           226,449      armv8_pmuv3_1/l3d_cache_lmiss_rd/

       0.021601396 seconds time elapsed


=== 128MB (DRAM range, iters=2097152) ===
[probe] sz=128MB iters=2097152 lat=114.43ns (446.3cy)

 Performance counter stats for 'CPU(s) 5':

         6,550,378      armv8_pmuv3_1/l1d_cache_refill/
         4,321,946      armv8_pmuv3_1/l1d_cache_lmiss_rd/
         9,143,621      armv8_pmuv3_1/l2d_cache_refill/
         3,774,410      armv8_pmuv3_1/l2d_cache_lmiss_rd/
         2,671,787      armv8_pmuv3_1/l3d_cache_refill/
         2,671,796      armv8_pmuv3_1/l3d_cache_lmiss_rd/

       0.266986719 seconds time elapsed
```

## PMU Event 可用清单（已确认）

**PMU Driver**: `armv8_pmuv3_1`（对应 C0 cluster, cpu5 = A725）

| Event                | 含义                                      |
| -------------------- | ----------------------------------------- |
| `l1d_cache_refill`   | L1D miss → 向下层请求                     |
| `l1d_cache_lmiss_rd` | L1D long-latency miss（真正打到下层的读） |
| `l2d_cache_refill`   | L2 miss → 向下层请求                      |
| `l2d_cache_lmiss_rd` | L2 long-latency miss                      |
| `l3d_cache_refill`   | L3 miss → 向下层（SLC/DRAM）请求          |
| `l3d_cache_lmiss_rd` | L3 long-latency miss                      |

**绑定方式**：`-C 5` + `taskset -c 5`（cpu5, A725 核）

## Notes

- PMU mapped by core type
- Not cluster-based

