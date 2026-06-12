/*
 * chase_pmu_v2.7.3.c - Pointer-chase memory latency tool
 * Targets: ARM64 (GB10/M-series SoC)
 * Features:
 *   - warm=N: explicit pre-warm passes (0 = implicit fill via init_chain only)
 *   - force_rounds=1: single-pass cold measurement (SLC/DRAM latency)
 *   - double_evict: external evict called twice (script-level, not here)
 *   - hugepage: 2MB MAP_HUGETLB mmap to eliminate buddy allocator set-skew
 *
 * Changelog v2.7.3 (vs v2.7.2):
 *   - 新增第7参数 hugepage (0=4K page, 1=2MB hugepage, default=0)
 *   - init_chain 支持 MAP_HUGETLB，alloc_size 对齐到 2MB
 *   - hugepage mmap 失败自动 fallback 到 4K page，不影响原有流程
 *   - munmap 使用 alloc_size（hugepage 模式下必须对齐）
 *   - 输出 header 新增 hugepage 标记
 *   - 其余逻辑与 v2.7.2 完全一致，向后兼容
 *
 * Build: gcc -O2 -o chase_pmu chase_pmu_v2.7.3.c
 * Usage: taskset -c <cpu> ./chase_pmu <size_kb> <warm> [force_rounds] [seed] [clflush] [hugepage]
 *
 * Examples:
 *   taskset -c 10 ./chase_pmu 12288 5 25 42 0 0   # 4K page (baseline)
 *   taskset -c 10 ./chase_pmu 12288 5 25 42 0 1   # 2MB hugepage (set-skew test)
 *   taskset -c  5 ./chase_pmu 16384 5  0 42 0 0   # warm L3, 4K page
 *   taskset -c  5 ./chase_pmu 65536 0  1 42 1 0   # cold DRAM, clflush
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>

#ifdef __aarch64__
#include <sys/mman.h>
#endif

#define CACHELINE_BYTES  64UL
#define PTRS_PER_LINE    (CACHELINE_BYTES / sizeof(uintptr_t))
#define HUGEPAGE_SIZE    (2UL * 1024 * 1024)   /* 2MB transparent hugepage */

/* ------------------------------------------------------------------ */
/* Timing: use CLOCK_MONOTONIC_RAW for minimal OS jitter               */
/* ------------------------------------------------------------------ */
static inline uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

/* ------------------------------------------------------------------ */
/* Fisher-Yates shuffle for pointer-chase chain construction           */
/* ------------------------------------------------------------------ */
static void shuffle(size_t *arr, size_t n, uint64_t seed)
{
    uint64_t s = seed ? seed : 0xdeadbeefcafeULL;
    for (size_t i = n - 1; i > 0; i--) {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17;
        size_t j = s % (i + 1);
        size_t tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
    }
}

/* ------------------------------------------------------------------ */
/* DC CIVAC flush: writeback + invalidate L1/L2 to PoC                 */
/* NOTE: flushes to Point of Coherency (PoC), NOT out of L3/SLC.      */
/*       On ARM DSU, PoC is typically the L3 or SLC boundary.         */
/*       Use only to eliminate L1/L2 residue for warm=0 cold tests.   */
/* ------------------------------------------------------------------ */
#ifdef __aarch64__
static void clflush_range(void *addr, size_t size)
{
    uintptr_t p   = (uintptr_t)addr & ~(uintptr_t)(CACHELINE_BYTES - 1);
    uintptr_t end = (uintptr_t)addr + size;
    /* DC CIVAC: Clean and Invalidate by VA to PoC */
    for (; p < end; p += CACHELINE_BYTES) {
        asm volatile("dc civac, %0" :: "r"(p) : "memory");
    }
    asm volatile("dsb sy" ::: "memory");  /* ensure completion */
}
#else
static void clflush_range(void *addr, size_t size)
{
    (void)addr; (void)size;  /* no-op on non-ARM64 */
}
#endif

/* ------------------------------------------------------------------ */
/* Build a random pointer-chase chain (cacheline-stride)               */
/*                                                                      */
/* use_hugepage=1: alloc_size 向上对齐到 2MB，使用 MAP_HUGETLB         */
/*   - 物理地址在 2MB 内连续，PA[17:6] 均匀覆盖所有 L3 set             */
/*   - 消除 buddy allocator 导致的 set-skew（BUG-06 Layer 2 验证）     */
/*   - hugepage mmap 失败自动 fallback 到 4K page                      */
/*   - actual_size_out 返回实际 alloc_size，供 munmap 使用              */
/*                                                                      */
/* use_hugepage=0: 原始 4K page 行为，与 v2.7.2 完全一致               */
/*                                                                      */
/* NOTE: init_chain write-allocates all nodes into cache (last-pass    */
/*       locality). warm=0 does NOT mean data-cold.                    */
/* ------------------------------------------------------------------ */
static uintptr_t *init_chain(size_t size_bytes, uint64_t seed,
                              int use_hugepage, size_t *actual_size_out)
{
    size_t n_lines = size_bytes / CACHELINE_BYTES;
    if (n_lines < 2) { fprintf(stderr, "size too small\n"); exit(1); }

    /* hugepage 模式：alloc_size 向上对齐到 2MB
     * 原因：MAP_HUGETLB 要求 mmap length 是 hugepage_size 的整数倍
     * chain 构建仍按原始 n_lines，padding 区域不参与 chase          */
    size_t alloc_size = size_bytes;
    if (use_hugepage) {
        alloc_size = (size_bytes + HUGEPAGE_SIZE - 1)
                     & ~(HUGEPAGE_SIZE - 1);
    }
    *actual_size_out = alloc_size;

    uintptr_t *buf = NULL;
#ifdef __aarch64__
    if (use_hugepage) {
        buf = (uintptr_t *)mmap(NULL, alloc_size,
                                PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS |
                                MAP_POPULATE | MAP_HUGETLB,
                                -1, 0);
        if (buf == MAP_FAILED) {
            fprintf(stderr,
                "[hugepage] MAP_HUGETLB mmap failed (%s), "
                "fallback to 4K page\n"
                "[hugepage] hint: echo N | sudo tee "
                "/proc/sys/vm/nr_hugepages\n",
                strerror(errno));
            buf = NULL;   /* trigger fallback below */
            alloc_size = size_bytes;
            *actual_size_out = alloc_size;
        } else {
            fprintf(stderr,
                "[hugepage] 2MB hugepage alloc OK: "
                "addr=%p  alloc=%zu KB  chain=%zu KB\n",
                (void *)buf, alloc_size >> 10, size_bytes >> 10);
        }
    }

    if (buf == NULL) {
        /* 4K page path (original v2.7.2 behavior) */
        buf = (uintptr_t *)mmap(NULL, alloc_size,
                                PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS | MAP_POPULATE,
                                -1, 0);
        if (buf == MAP_FAILED) { perror("mmap"); exit(1); }
    }
#else
    (void)use_hugepage;
    alloc_size = size_bytes;
    *actual_size_out = alloc_size;
    if (posix_memalign((void **)&buf, CACHELINE_BYTES, size_bytes)) {
        perror("posix_memalign"); exit(1);
    }
    memset(buf, 0, size_bytes);
#endif

    /* Build pointer-chase chain over n_lines (original size_bytes only) */
    size_t *perm = (size_t *)malloc(n_lines * sizeof(size_t));
    if (!perm) { perror("malloc"); exit(1); }
    for (size_t i = 0; i < n_lines; i++) perm[i] = i;
    shuffle(perm, n_lines, seed);

    for (size_t i = 0; i < n_lines - 1; i++) {
        buf[perm[i] * PTRS_PER_LINE] = (uintptr_t)&buf[perm[i+1] * PTRS_PER_LINE];
    }
    buf[perm[n_lines-1] * PTRS_PER_LINE] = (uintptr_t)&buf[perm[0] * PTRS_PER_LINE];

    free(perm);
    return buf;
}

/* ------------------------------------------------------------------ */
/* Core chase loop                                                      */
/* ------------------------------------------------------------------ */
static uint64_t chase_loop(uintptr_t *head, size_t n_lines,
                           int rounds, volatile uintptr_t *sink)
{
    uintptr_t p = (uintptr_t)head;
    uint64_t t0 = now_ns();

    for (int r = 0; r < rounds; r++) {
        for (size_t i = 0; i < n_lines; i++) {
            p = *(uintptr_t *)p;
        }
    }
    uint64_t t1 = now_ns();
    *sink = p;
    return t1 - t0;
}

/* ------------------------------------------------------------------ */
/* Main                                                                 */
/* ------------------------------------------------------------------ */
int main(int argc, char *argv[])
{
    if (argc < 3) {
        fprintf(stderr,
            "Usage: %s <size_kb> <warm> [force_rounds] [seed] [clflush] [hugepage]\n"
            "  size_kb     : working set in KB\n"
            "  warm        : pre-warm passes (0=init_chain fill only)\n"
            "  force_rounds: 0=auto, 1=single-pass cold\n"
            "  seed        : PRNG seed (0=default)\n"
            "  clflush     : 1=DC CIVAC flush L1/L2 after init (warm=0 cold test)\n"
            "  hugepage    : 1=2MB MAP_HUGETLB (eliminate set-skew), 0=4K page\n"
            "                requires: echo N | sudo tee /proc/sys/vm/nr_hugepages\n"
            "\nExamples:\n"
            "  taskset -c 10 ./chase_pmu 12288 5 25 42 0 0  # 4K page baseline\n"
            "  taskset -c 10 ./chase_pmu 12288 5 25 42 0 1  # 2MB hugepage\n"
            "  taskset -c  5 ./chase_pmu 16384 5  0 42 0 0  # warm L3\n"
            "  taskset -c  5 ./chase_pmu 65536 0  1 42 1 0  # cold DRAM (clflush)\n",
            argv[0]);
        return 1;
    }

    size_t   size_kb      = (size_t)atoll(argv[1]);
    int      warm         = atoi(argv[2]);
    int      force_rounds = (argc >= 4) ? atoi(argv[3]) : 0;
    uint64_t seed         = (argc >= 5) ? (uint64_t)atoll(argv[4]) : 0;
    int      do_clflush   = (argc >= 6) ? atoi(argv[5]) : 0;
    int      use_hugepage = (argc >= 7) ? atoi(argv[6]) : 0;

    size_t size_bytes = size_kb * 1024ULL;
    size_t n_lines    = size_bytes / CACHELINE_BYTES;

    /* Auto-select measurement rounds */
    int meas_rounds;
    if (force_rounds > 0) {
        meas_rounds = force_rounds;
    } else {
        uint64_t est_ns = (uint64_t)n_lines * 100;
        meas_rounds = (int)(500000000ULL / est_ns);
        if (meas_rounds < 1)  meas_rounds = 1;
        if (meas_rounds > 50) meas_rounds = 50;
    }

    /* cold_mode tag for script grep */
    const char *cold_tag = "";
    if (warm == 0 && force_rounds == 1) {
        if (do_clflush)
            cold_tag = "  [COLD-DRAM clflush]";
        else
            cold_tag = "  [COLD-L3residue]";
    }

    printf("=== chase_pmu v2.7.3 ===\n");
    printf("size=%zu KB  n_lines=%zu  warm=%d  meas_rounds=%d  "
           "seed=%llu  hugepage=%d%s\n",
           size_kb, n_lines, warm, meas_rounds,
           (unsigned long long)seed, use_hugepage, cold_tag);

    /* Build chain */
    size_t alloc_size = 0;
    uintptr_t *buf = init_chain(size_bytes, seed, use_hugepage, &alloc_size);

    volatile uintptr_t sink = 0;

    /* Optional: DC CIVAC flush L1/L2 after init_chain */
    if (do_clflush && warm == 0) {
        clflush_range(buf, size_bytes);
        fprintf(stderr, "[clflush] DC CIVAC flushed %zu MB to PoC\n",
                size_bytes >> 20);
    }

    /* Explicit warm passes */
    if (warm > 0) {
        printf("Warming %d pass(es)...\n", warm);
        chase_loop(buf, n_lines, warm, &sink);
    } else {
        printf("warm=0: init_chain fill only%s\n",
               do_clflush ? " + DC CIVAC flush" : " (L3 residue possible)");
    }

    /* Measurement */
    uint64_t elapsed_ns = chase_loop(buf, n_lines, meas_rounds, &sink);

    uint64_t total_accesses = (uint64_t)n_lines * meas_rounds;
    double   lat_ns         = (double)elapsed_ns / (double)total_accesses;

    printf("elapsed=%llu ns  accesses=%llu\n",
           (unsigned long long)elapsed_ns,
           (unsigned long long)total_accesses);
    printf(">>> latency = %.2f ns/access  (sink=%p)\n",
           lat_ns, (void *)sink);

#ifdef __aarch64__
    /* 必须用 alloc_size（hugepage 模式下已对齐到 2MB）*/
    munmap(buf, alloc_size);
#else
    free(buf);
#endif

    return 0;
}
