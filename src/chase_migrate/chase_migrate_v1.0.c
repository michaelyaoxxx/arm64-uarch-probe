/*
 * chase_migrate_v1.0.c - Same-chain cross-core migration latency tool
 *
 * Phase 2B-5:
 *   source CPU builds/warm-measures a pointer chain, then migrates
 *   the same process to destination CPU and measures the same chain.
 *
 * Directory:
 *   src/chase_migrate/chase_migrate_v1.0.c
 *
 * Build:
 *   gcc -O2 -Wall -Wextra -o tools/bin/chase_migrate src/chase_migrate/chase_migrate_v1.0.c
 *
 * Usage:
 *   ./chase_migrate --src-cpu N --dst-cpu N --size-kb N [options]
 *
 * Important methodology:
 *   bind(src) -> mmap/init_chain -> warm(src) -> measure(src)
 *             -> bind(dst) -> measure(dst same chain)
 */

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <errno.h>
#include <sched.h>
#include <getopt.h>
#include <sys/mman.h>
#include <inttypes.h>

#define CACHELINE_BYTES  64UL
#define PTRS_PER_LINE    (CACHELINE_BYTES / sizeof(uintptr_t))
#define HUGEPAGE_SIZE    (2UL * 1024UL * 1024UL)

static inline uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

static int parse_u64(const char *s, uint64_t *out)
{
    if (!s || !*s) return -1;

    errno = 0;
    char *end = NULL;
    unsigned long long v = strtoull(s, &end, 0);
    if (errno != 0 || end == s || *end != '\0') return -1;

    *out = (uint64_t)v;
    return 0;
}

static void shuffle(size_t *arr, size_t n, uint64_t seed)
{
    uint64_t s = seed ? seed : 0xdeadbeefcafeULL;

    if (n < 2) return;

    for (size_t i = n - 1; i > 0; i--) {
        s ^= s << 13;
        s ^= s >> 7;
        s ^= s << 17;

        size_t j = (size_t)(s % (i + 1));
        size_t tmp = arr[i];
        arr[i] = arr[j];
        arr[j] = tmp;
    }
}

static int bind_to_cpu(int cpu)
{
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);

    if (sched_setaffinity(0, sizeof(set), &set) != 0) {
        fprintf(stderr,
                "[affinity][ERROR] sched_setaffinity(cpu=%d) failed: %s\n",
                cpu, strerror(errno));
        return -1;
    }

    for (int i = 0; i < 10000; i++) {
        int cur = sched_getcpu();
        if (cur == cpu) return 0;
        sched_yield();
    }

    fprintf(stderr,
            "[affinity][WARN] requested cpu=%d current=%d after retries\n",
            cpu, sched_getcpu());
    return 0;
}

static uintptr_t *init_chain(size_t size_bytes,
                             uint64_t seed,
                             int use_hugepage,
                             int strict_hugepage,
                             size_t *alloc_size_out,
                             int *hugepage_actual_out)
{
    size_t n_lines = size_bytes / CACHELINE_BYTES;
    if (n_lines < 2) {
        fprintf(stderr, "[init][ERROR] size too small\n");
        exit(1);
    }

    size_t alloc_size = size_bytes;
    if (use_hugepage) {
        alloc_size = (size_bytes + HUGEPAGE_SIZE - 1) & ~(HUGEPAGE_SIZE - 1);
    }

    uintptr_t *buf = NULL;
    int hugepage_actual = 0;

#ifdef __aarch64__
    if (use_hugepage) {
        buf = (uintptr_t *)mmap(NULL,
                                alloc_size,
                                PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS | MAP_POPULATE | MAP_HUGETLB,
                                -1,
                                0);
        if (buf == MAP_FAILED) {
            fprintf(stderr,
                    "[hugepage][ERROR] MAP_HUGETLB mmap failed: %s\n",
                    strerror(errno));
            if (strict_hugepage) {
                fprintf(stderr,
                        "[hugepage][FATAL] strict_hugepage=1, abort\n");
                exit(2);
            }

            fprintf(stderr,
                    "[hugepage][WARN] fallback to 4K page\n");
            buf = NULL;
            alloc_size = size_bytes;
        } else {
            hugepage_actual = 1;
            fprintf(stderr,
                    "[hugepage] 2MB hugepage alloc OK: addr=%p alloc=%zu KB chain=%zu KB\n",
                    (void *)buf,
                    alloc_size >> 10,
                    size_bytes >> 10);
        }
    }

    if (buf == NULL) {
        buf = (uintptr_t *)mmap(NULL,
                                alloc_size,
                                PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS | MAP_POPULATE,
                                -1,
                                0);
        if (buf == MAP_FAILED) {
            fprintf(stderr, "[mmap][ERROR] mmap failed: %s\n", strerror(errno));
            exit(1);
        }
    }
#else
    if (use_hugepage && strict_hugepage) {
        fprintf(stderr, "[hugepage][FATAL] strict hugepage requested on non-aarch64\n");
        exit(2);
    }

    alloc_size = size_bytes;
    if (posix_memalign((void **)&buf, CACHELINE_BYTES, size_bytes) != 0) {
        perror("posix_memalign");
        exit(1);
    }
    memset(buf, 0, size_bytes);
#endif

    *alloc_size_out = alloc_size;
    *hugepage_actual_out = hugepage_actual;

    size_t *perm = (size_t *)malloc(n_lines * sizeof(size_t));
    if (!perm) {
        perror("malloc perm");
        exit(1);
    }

    for (size_t i = 0; i < n_lines; i++) {
        perm[i] = i;
    }

    shuffle(perm, n_lines, seed);

    for (size_t i = 0; i < n_lines - 1; i++) {
        buf[perm[i] * PTRS_PER_LINE] =
            (uintptr_t)&buf[perm[i + 1] * PTRS_PER_LINE];
    }

    buf[perm[n_lines - 1] * PTRS_PER_LINE] =
        (uintptr_t)&buf[perm[0] * PTRS_PER_LINE];

    free(perm);
    return buf;
}

static uint64_t chase_loop(uintptr_t *head,
                           size_t n_lines,
                           int rounds,
                           volatile uintptr_t *sink,
                           int *cpu_before,
                           int *cpu_after)
{
    uintptr_t p = (uintptr_t)head;

    if (cpu_before) *cpu_before = sched_getcpu();

    uint64_t t0 = now_ns();

    for (int r = 0; r < rounds; r++) {
        for (size_t i = 0; i < n_lines; i++) {
            p = *(uintptr_t *)p;
        }
    }

    uint64_t t1 = now_ns();

    if (cpu_after) *cpu_after = sched_getcpu();

    *sink = p;
    return t1 - t0;
}

static void usage(const char *prog)
{
    fprintf(stderr,
        "Usage: %s --src-cpu N --dst-cpu N --size-kb N [options]\n"
        "\nRequired:\n"
        "  --src-cpu N             source CPU for allocation/init/warm\n"
        "  --dst-cpu N             destination CPU for post-migration measurement\n"
        "  --size-kb N             working set size in KB\n"
        "\nOptional:\n"
        "  --warm-src N            warm passes on source CPU. Default: 5\n"
        "  --measure-rounds N      measurement rounds for src/dst. Default: 1\n"
        "  --measure-src 0|1       measure source local latency before migration. Default: 1\n"
        "  --seed N                PRNG seed. Default: 42\n"
        "  --hugepage 0|1          use 2MB MAP_HUGETLB. Default: 1\n"
        "  --strict-hugepage 0|1   abort if hugepage allocation fails. Default: 1\n"
        "  --sleep-us N            sleep after migration before measuring dst. Default: 0\n"
        "  --label STR             label printed in header\n"
        "  --help, -h              show this help\n"
        "\nExamples:\n"
        "  %s --src-cpu 5 --dst-cpu 15 --size-kb 32768 --hugepage 1 --strict-hugepage 1\n"
        "  %s --src-cpu 15 --dst-cpu 5 --size-kb 32768 --warm-src 5 --measure-rounds 1\n"
        "  %s --src-cpu 5 --dst-cpu 5 --size-kb 32768  # local baseline\n",
        prog, prog, prog, prog);
}

int main(int argc, char *argv[])
{
    int src_cpu = -1;
    int dst_cpu = -1;
    size_t size_kb = 0;

    int warm_src = 5;
    int measure_rounds = 1;
    int measure_src = 1;

    uint64_t seed = 42;
    int use_hugepage = 1;
    int strict_hugepage = 1;
    int sleep_us = 0;
    const char *label = "";

    static struct option long_opts[] = {
        {"src-cpu",          required_argument, 0, 1000},
        {"dst-cpu",          required_argument, 0, 1001},
        {"size-kb",          required_argument, 0, 1002},
        {"warm-src",         required_argument, 0, 1003},
        {"measure-rounds",   required_argument, 0, 1004},
        {"measure-src",      required_argument, 0, 1005},
        {"seed",             required_argument, 0, 1006},
        {"hugepage",         required_argument, 0, 1007},
        {"strict-hugepage",  required_argument, 0, 1008},
        {"sleep-us",         required_argument, 0, 1009},
        {"label",            required_argument, 0, 1010},
        {"help",             no_argument,       0, 'h'},
        {0, 0, 0, 0}
    };

    while (1) {
        int opt_idx = 0;
        int c = getopt_long(argc, argv, "h", long_opts, &opt_idx);
        if (c == -1) break;

        uint64_t v = 0;

        switch (c) {
        case 1000:
            if (parse_u64(optarg, &v) != 0) return 2;
            src_cpu = (int)v;
            break;
        case 1001:
            if (parse_u64(optarg, &v) != 0) return 2;
            dst_cpu = (int)v;
            break;
        case 1002:
            if (parse_u64(optarg, &v) != 0) return 2;
            size_kb = (size_t)v;
            break;
        case 1003:
            if (parse_u64(optarg, &v) != 0) return 2;
            warm_src = (int)v;
            break;
        case 1004:
            if (parse_u64(optarg, &v) != 0) return 2;
            measure_rounds = (int)v;
            break;
        case 1005:
            if (parse_u64(optarg, &v) != 0) return 2;
            measure_src = (int)v;
            break;
        case 1006:
            if (parse_u64(optarg, &v) != 0) return 2;
            seed = v;
            break;
        case 1007:
            if (parse_u64(optarg, &v) != 0) return 2;
            use_hugepage = (int)v;
            break;
        case 1008:
            if (parse_u64(optarg, &v) != 0) return 2;
            strict_hugepage = (int)v;
            break;
        case 1009:
            if (parse_u64(optarg, &v) != 0) return 2;
            sleep_us = (int)v;
            break;
        case 1010:
            label = optarg;
            break;
        case 'h':
            usage(argv[0]);
            return 0;
        default:
            usage(argv[0]);
            return 2;
        }
    }

    if (src_cpu < 0 || dst_cpu < 0 || size_kb == 0) {
        usage(argv[0]);
        return 2;
    }

    if (warm_src < 0) warm_src = 0;
    if (measure_rounds < 1) measure_rounds = 1;
    if (measure_src != 0) measure_src = 1;
    if (use_hugepage != 0) use_hugepage = 1;
    if (strict_hugepage != 0) strict_hugepage = 1;
    if (sleep_us < 0) sleep_us = 0;

    size_t size_bytes = size_kb * 1024ULL;
    size_t n_lines = size_bytes / CACHELINE_BYTES;

    if (n_lines < 2) {
        fprintf(stderr, "[ERROR] size_kb too small\n");
        return 2;
    }

    printf("=== chase_migrate v1.0 ===\n");
    printf("label=%s\n", label && label[0] ? label : "(none)");
    printf("src_cpu=%d dst_cpu=%d size=%zu KB n_lines=%zu "
           "warm_src=%d measure_rounds=%d measure_src=%d "
           "seed=%" PRIu64 " hugepage=%d strict_hugepage=%d sleep_us=%d\n",
           src_cpu,
           dst_cpu,
           size_kb,
           n_lines,
           warm_src,
           measure_rounds,
           measure_src,
           seed,
           use_hugepage,
           strict_hugepage,
           sleep_us);

    /*
     * Critical methodology:
     * Bind to source before allocation and chain construction.
     */
    if (bind_to_cpu(src_cpu) != 0) {
        return 3;
    }

    printf("[src] bound before alloc/init: requested=%d current=%d\n",
           src_cpu, sched_getcpu());

    size_t alloc_size = 0;
    int hugepage_actual = 0;

    uintptr_t *buf = init_chain(size_bytes,
                                seed,
                                use_hugepage,
                                strict_hugepage,
                                &alloc_size,
                                &hugepage_actual);

    printf("[alloc] buf=%p alloc_size=%zu KB chain_size=%zu KB hugepage_actual=%d\n",
           (void *)buf,
           alloc_size >> 10,
           size_kb,
           hugepage_actual);

    volatile uintptr_t sink = 0;

    if (warm_src > 0) {
        int cb = -1, ca = -1;
        uint64_t warm_ns = chase_loop(buf, n_lines, warm_src, &sink, &cb, &ca);
        uint64_t warm_accesses = (uint64_t)n_lines * (uint64_t)warm_src;
        double warm_lat = (double)warm_ns / (double)warm_accesses;

        printf("[src] warm elapsed=%" PRIu64 " ns accesses=%" PRIu64
               " lat=%.2f ns/access cpu_before=%d cpu_after=%d sink=%p\n",
               warm_ns,
               warm_accesses,
               warm_lat,
               cb,
               ca,
               (void *)sink);

        if (cb != src_cpu || ca != src_cpu) {
            fprintf(stderr,
                    "[src][WARN] CPU changed during warm: before=%d after=%d expected=%d\n",
                    cb, ca, src_cpu);
        }
    } else {
        printf("[src] warm skipped warm_src=0\n");
    }

    double src_lat = -1.0;

    if (measure_src) {
        int cb = -1, ca = -1;
        uint64_t src_ns = chase_loop(buf, n_lines, measure_rounds, &sink, &cb, &ca);
        uint64_t src_accesses = (uint64_t)n_lines * (uint64_t)measure_rounds;
        src_lat = (double)src_ns / (double)src_accesses;

        printf("[src] measure elapsed=%" PRIu64 " ns accesses=%" PRIu64
               " cpu_before=%d cpu_after=%d\n",
               src_ns,
               src_accesses,
               cb,
               ca);
        printf(">>> src_latency = %.2f ns/access  (sink=%p)\n",
               src_lat,
               (void *)sink);

        if (cb != src_cpu || ca != src_cpu) {
            fprintf(stderr,
                    "[src][WARN] CPU changed during measure: before=%d after=%d expected=%d\n",
                    cb, ca, src_cpu);
        }
    } else {
        printf("[src] measure skipped measure_src=0\n");
    }

    if (bind_to_cpu(dst_cpu) != 0) {
        return 4;
    }

    printf("[dst] bound after migration: requested=%d current=%d\n",
           dst_cpu, sched_getcpu());

    if (sleep_us > 0) {
        usleep((useconds_t)sleep_us);
        printf("[dst] slept %d us before measure\n", sleep_us);
    }

    int cb = -1, ca = -1;
    uint64_t dst_ns = chase_loop(buf, n_lines, measure_rounds, &sink, &cb, &ca);
    uint64_t dst_accesses = (uint64_t)n_lines * (uint64_t)measure_rounds;
    double dst_lat = (double)dst_ns / (double)dst_accesses;

    printf("[dst] measure elapsed=%" PRIu64 " ns accesses=%" PRIu64
           " cpu_before=%d cpu_after=%d\n",
           dst_ns,
           dst_accesses,
           cb,
           ca);
    printf(">>> migrate_latency = %.2f ns/access  (sink=%p)\n",
           dst_lat,
           (void *)sink);

    if (src_lat >= 0.0) {
        printf(">>> migrate_penalty = %.2f ns/access\n",
               dst_lat - src_lat);
    }

    if (cb != dst_cpu || ca != dst_cpu) {
        fprintf(stderr,
                "[dst][WARN] CPU changed during measure: before=%d after=%d expected=%d\n",
                cb, ca, dst_cpu);
    }

#ifdef __aarch64__
    munmap(buf, alloc_size);
#else
    free(buf);
#endif

    return 0;
}
