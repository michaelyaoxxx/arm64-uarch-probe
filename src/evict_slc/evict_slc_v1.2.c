/*
 * evict_slc_v1.2.c — L3/SLC Cache Eviction Utility
 *
 * Targets:
 *   ARM64 GB10 / M-series-like SoC
 *
 * Purpose:
 *   Generate controlled cache pressure to evict private/shared LLC/SLC
 *   before pointer-chase latency measurement.
 *
 * Modes:
 *   random (default):
 *     - random cacheline order
 *     - read + write each line
 *     - good for defeating stride prefetchers and stressing set/slice hash
 *
 *   sequential (--seq):
 *     - linear cacheline order
 *     - read-only by default
 *     - useful as a control experiment
 *     - may be less effective if HW prefetchers/SLC insertion policy differ
 *
 * Version:
 *   v1.2
 *
 * Changes vs v1.1:
 *   - add --help / -h
 *   - add --verbose / -v
 *   - add --quiet / -q
 *   - add --no-touch-init to disable explicit page fault-in
 *   - add runtime/bandwidth report in verbose mode
 *   - fail-fast argument validation
 *   - use clock_gettime(CLOCK_MONOTONIC_RAW)
 *   - use posix_memalign(64B)
 *
 * Usage:
 *   evict_slc [--evict_mb=N] [--seq] [--seed=N] [--verbose] [--quiet]
 *   evict_slc [evict_mb] [seed]
 *
 * Examples:
 *   evict_slc --evict_mb=64 --verbose
 *   evict_slc --evict_mb=64 --seq --verbose
 *   evict_slc 64 42
 *
 * Build:
 *   gcc -O2 -Wall -Wextra -o evict_slc evict_slc_v1.2.c
 */

#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <errno.h>
#include <inttypes.h>

#define DEFAULT_EVICT_MB  64UL
#define CACHELINE_BYTES   64UL
#define MIN_EVICT_MB      1UL
#define MAX_EVICT_MB      4096UL

static inline uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

static void print_usage(const char *prog)
{
    fprintf(stdout,
        "Usage: %s [options] [evict_mb] [seed]\n"
        "\n"
        "Options:\n"
        "  --evict_mb=N       Eviction buffer size in MB. Default: %lu\n"
        "  --seed=N           Random seed. Default: 42\n"
        "  --seq              Sequential read-only eviction mode. Default: random read+write\n"
        "  --random           Random read+write eviction mode. Explicit default\n"
        "  --no-touch-init    Do not pre-touch/fault-in eviction buffer before eviction\n"
        "  --verbose, -v      Print configuration and runtime statistics\n"
        "  --quiet, -q        Suppress non-error output. Default unless --verbose\n"
        "  --help, -h         Show this help message\n"
        "\n"
        "Positional compatibility:\n"
        "  %s 64 42           Equivalent to --evict_mb=64 --seed=42\n"
        "\n"
        "Recommended for GB10 Phase 2B:\n"
        "  %s --evict_mb=64 --verbose\n"
        "  %s --evict_mb=64 --seq --verbose\n"
        "\n"
        "Notes:\n"
        "  random mode touches each 64B cacheline in shuffled order with read+write.\n"
        "  sequential mode touches each 64B cacheline linearly with read-only access.\n"
        "  For full L3+SLC eviction, evict_mb should be greater than max(L3+SLC).\n"
        "\n",
        prog,
        DEFAULT_EVICT_MB,
        prog,
        prog,
        prog);
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

static void shuffle(uint32_t *arr, size_t n, uint64_t seed)
{
    uint64_t s = seed ? seed : 12345678ULL;

    for (size_t i = n - 1; i > 0; i--) {
        s ^= s << 13;
        s ^= s >> 7;
        s ^= s << 17;
        size_t j = (size_t)(s % (i + 1));

        uint32_t tmp = arr[i];
        arr[i] = arr[j];
        arr[j] = tmp;
    }
}

int main(int argc, char *argv[])
{
    size_t   evict_mb       = DEFAULT_EVICT_MB;
    uint64_t seed           = 42;
    int      seq_mode       = 0;
    int      verbose        = 0;
    int      touch_init     = 1;

    int pos = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return 0;
        } else if (strcmp(argv[i], "--verbose") == 0 || strcmp(argv[i], "-v") == 0) {
            verbose = 1;
        } else if (strcmp(argv[i], "--quiet") == 0 || strcmp(argv[i], "-q") == 0) {
            verbose = 0;
        } else if (strcmp(argv[i], "--seq") == 0) {
            seq_mode = 1;
        } else if (strcmp(argv[i], "--random") == 0) {
            seq_mode = 0;
        } else if (strcmp(argv[i], "--no-touch-init") == 0) {
            touch_init = 0;
        } else if (strncmp(argv[i], "--evict_mb=", 11) == 0) {
            uint64_t v = 0;
            if (parse_u64(argv[i] + 11, &v) != 0) {
                fprintf(stderr, "[evict_slc][ERROR] invalid --evict_mb: %s\n", argv[i] + 11);
                return 2;
            }
            evict_mb = (size_t)v;
        } else if (strncmp(argv[i], "--seed=", 7) == 0) {
            uint64_t v = 0;
            if (parse_u64(argv[i] + 7, &v) != 0) {
                fprintf(stderr, "[evict_slc][ERROR] invalid --seed: %s\n", argv[i] + 7);
                return 2;
            }
            seed = v;
        } else if (argv[i][0] != '-') {
            uint64_t v = 0;
            if (parse_u64(argv[i], &v) != 0) {
                fprintf(stderr, "[evict_slc][ERROR] invalid positional argument: %s\n", argv[i]);
                return 2;
            }

            if (pos == 0) {
                evict_mb = (size_t)v;
            } else if (pos == 1) {
                seed = v;
            } else {
                fprintf(stderr, "[evict_slc][ERROR] too many positional arguments\n");
                print_usage(argv[0]);
                return 2;
            }
            pos++;
        } else {
            fprintf(stderr, "[evict_slc][ERROR] unknown option: %s\n", argv[i]);
            print_usage(argv[0]);
            return 2;
        }
    }

    if (evict_mb < MIN_EVICT_MB || evict_mb > MAX_EVICT_MB) {
        fprintf(stderr,
            "[evict_slc][ERROR] evict_mb=%zu out of range [%lu, %lu]\n",
            evict_mb, MIN_EVICT_MB, MAX_EVICT_MB);
        return 2;
    }

    size_t buf_bytes = evict_mb * 1024UL * 1024UL;
    size_t n_lines   = buf_bytes / CACHELINE_BYTES;

    if (n_lines == 0 || n_lines > UINT32_MAX) {
        fprintf(stderr,
            "[evict_slc][ERROR] n_lines=%zu invalid or exceeds uint32_t range\n",
            n_lines);
        return 2;
    }

    volatile uint8_t *buf = NULL;
    int rc = posix_memalign((void **)&buf, CACHELINE_BYTES, buf_bytes);
    if (rc != 0 || buf == NULL) {
        fprintf(stderr,
            "[evict_slc][ERROR] posix_memalign(%zu MB) failed: %s\n",
            evict_mb, strerror(rc ? rc : errno));
        return 1;
    }

    volatile uint64_t sink = 0;

    uint64_t t_alloc_done = now_ns();

    /*
     * Explicit fault-in / initialization.
     * This isolates page-fault noise from the actual eviction pass.
     *
     * memset() is not used because buf is volatile; touch one byte per
     * cacheline to allocate physical pages and establish cache residency.
     */
    if (touch_init) {
        for (size_t i = 0; i < n_lines; i++) {
            buf[i * CACHELINE_BYTES] = (uint8_t)i;
        }
    }

    uint64_t t_touch_done = now_ns();

    if (verbose) {
        fprintf(stderr,
            "[evict_slc] version=v1.2 mode=%s evict_mb=%zu bytes=%zu "
            "n_lines=%zu seed=%" PRIu64 " touch_init=%d\n",
            seq_mode ? "seq" : "random",
            evict_mb,
            buf_bytes,
            n_lines,
            seed,
            touch_init);
    }

    uint64_t t0 = now_ns();

    if (seq_mode) {
        /*
         * Sequential read-only pass.
         */
        for (size_t i = 0; i < n_lines; i++) {
            sink += *(volatile uint64_t *)(buf + i * CACHELINE_BYTES);
        }
    } else {
        /*
         * Random read+write pass.
         */
        uint32_t *idx = NULL;
        rc = posix_memalign((void **)&idx, CACHELINE_BYTES, n_lines * sizeof(uint32_t));
        if (rc != 0 || idx == NULL) {
            fprintf(stderr,
                "[evict_slc][ERROR] idx allocation failed: %s\n",
                strerror(rc ? rc : errno));
            free((void *)buf);
            return 1;
        }

        for (size_t i = 0; i < n_lines; i++)
            idx[i] = (uint32_t)i;

        shuffle(idx, n_lines, seed);

        for (size_t i = 0; i < n_lines; i++) {
            size_t offset = (size_t)idx[i] * CACHELINE_BYTES;
            sink += *(volatile uint64_t *)(buf + offset);
            *(volatile uint64_t *)(buf + offset) = sink;
        }

        free(idx);
    }

    uint64_t t1 = now_ns();

    double elapsed_ms = (double)(t1 - t0) / 1e6;
    double gb         = (double)buf_bytes / (1024.0 * 1024.0 * 1024.0);
    double bw_gbs     = gb / ((double)(t1 - t0) / 1e9);

    if (verbose) {
        double touch_ms = (double)(t_touch_done - t_alloc_done) / 1e6;
        fprintf(stderr,
            "[evict_slc] touch_ms=%.3f evict_ms=%.3f approx_bw=%.2f GB/s sink=%" PRIu64 "\n",
            touch_ms,
            elapsed_ms,
            bw_gbs,
            sink);
        fprintf(stderr, "[evict_slc] done\n");
    }

    /*
     * Keep sink live. This branch is never expected to trigger.
     */
    if (sink == 0xdeadbeefULL)
        fprintf(stderr, "sink=%" PRIu64 "\n", sink);

    free((void *)buf);
    return 0;
}
