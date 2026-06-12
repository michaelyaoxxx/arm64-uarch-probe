#!/bin/bash
# ================================================================
# GB10 PMU Cache Validation v2.7.10-section9
#
# Section 9 / Phase 2B-4:
#   DRAM HP cold baseline
#
# Goals:
#   1. DRAM cold envelope for A725/X925 on C0/C1
#   2. Compare cold/rand+warm0 vs warm/hugepage large working set
#   3. Validate Phase 2B-3 SLC overflow against true large-WS DRAM path
#
# Directory layout:
#   root/
#     runner/section9_dram_cold.sh
#     tools/bin/chase_pmu
#     tools/bin/evict_slc
#     data/
#
# Usage:
#   cd /home/michaelyao1/gb10-arch/runner
#   chmod +x section9_dram_cold.sh
#   ./section9_dram_cold.sh
#
# Optional:
#   MEDIAN_RUNS=3 ./section9_dram_cold.sh
#   SIZES_KB="32768 49152 65536" ./section9_dram_cold.sh
#   COLD_ONLY=1 ./section9_dram_cold.sh
#   WARM_ONLY=1 ./section9_dram_cold.sh
#   EVICT_MB=64 ./section9_dram_cold.sh
#
# ================================================================

set -o pipefail
set -u

CHASE_BIN="../tools/bin/chase_pmu"
EVICT_BIN="../tools/bin/evict_slc"

DATE_TAG="$(date +%Y%m%d)"
TS="$(date +%Y%m%d_%H%M%S)"

OUTDIR="../data/${DATE_TAG}_v2.7.10_section9_dram/raw"
mkdir -p "$OUTDIR"

OUTFILE="$OUTDIR/run_${TS}.txt"
SUMMARY_FILE="$OUTDIR/summary_${TS}.txt"
ERROR_FILE="$OUTDIR/error_${TS}.txt"

: > "$SUMMARY_FILE"
: > "$ERROR_FILE"

exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation v2.7.10-section9"
echo "# Phase        : 2B-4 DRAM HP cold baseline"
echo "# Date         : $(date)"
echo "# PWD          : $(pwd)"
echo "# CHASE_BIN    : $CHASE_BIN"
echo "# EVICT_BIN    : $EVICT_BIN"
echo "# OUTFILE      : $OUTFILE"
echo "# SUMMARY_FILE : $SUMMARY_FILE"
echo "# ERROR_FILE   : $ERROR_FILE"
echo "# ------------------------------------------------------------"

# ------------------------------------------------------------
# Fail-fast checks
# ------------------------------------------------------------
if [ ! -x "$CHASE_BIN" ]; then
    echo "[FATAL] CHASE_BIN not executable: $CHASE_BIN"
    exit 2
fi

if [ ! -x "$EVICT_BIN" ]; then
    echo "[FATAL] EVICT_BIN not executable: $EVICT_BIN"
    exit 2
fi

if ! "$EVICT_BIN" --help >/dev/null 2>&1; then
    echo "[FATAL] evict_slc --help failed"
    exit 2
fi

for c in 0 5 10 15; do
    if [ ! -d "/sys/devices/system/cpu/cpu$c" ]; then
        echo "[FATAL] cpu$c does not exist"
        exit 2
    fi
done

# ------------------------------------------------------------
# Parameters
# ------------------------------------------------------------
SEED="${SEED:-42}"
MEDIAN_RUNS="${MEDIAN_RUNS:-7}"
WARM_PASSES="${WARM_PASSES:-5}"
EVICT_MB="${EVICT_MB:-64}"

# Default sizes: 32MB, 48MB, 64MB, 96MB, 128MB
SIZES_KB="${SIZES_KB:-32768 49152 65536 98304 131072}"

# Control switches
WARM_ONLY="${WARM_ONLY:-0}"
COLD_ONLY="${COLD_ONLY:-0}"

# Hugepage check
NR_HP=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo 0)
MAX_SIZE_KB=0
for s in $SIZES_KB; do
    if [ "$s" -gt "$MAX_SIZE_KB" ]; then
        MAX_SIZE_KB="$s"
    fi
done

REQUIRED_HP=$(( (MAX_SIZE_KB + 2047) / 2048 ))

echo "# HugePages    : nr_hugepages=$NR_HP"
echo "# MaxSizeKB    : $MAX_SIZE_KB"
echo "# Required HP  : >= $REQUIRED_HP x 2MB hugepages for max chain"
if [ "$NR_HP" -lt "$REQUIRED_HP" ]; then
    echo "[WARN] nr_hugepages=$NR_HP < required=$REQUIRED_HP for max size ${MAX_SIZE_KB}KB"
    echo "[WARN] Some HP allocations may fail or fallback depending on chase_pmu behavior."
    echo "[HINT] sudo sh -c 'echo 128 > /proc/sys/vm/nr_hugepages'"
fi

echo ""
echo "# CPU frequency snapshot:"
for c in 0 5 10 15; do
    echo -n "  cpu$c "
    if [ -f "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq" ]; then
        cat "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq"
    else
        echo "scaling_cur_freq=N/A"
    fi
done

echo ""
echo "# MEDIAN_RUNS  : $MEDIAN_RUNS"
echo "# SEED         : $SEED"
echo "# WARM_PASSES  : $WARM_PASSES"
echo "# EVICT_MB     : $EVICT_MB"
echo "# SIZES_KB     : $SIZES_KB"
echo "# WARM_ONLY    : $WARM_ONLY"
echo "# COLD_ONLY    : $COLD_ONLY"
echo "# force_rounds : 1 for all DRAM baseline sizes"
echo "============================================================"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
get_median_lat() {
    local -a lats=("$@")
    local n="${#lats[@]}"

    printf '%s\n' "${lats[@]}" | \
        grep -oP '(?<=latency = )[0-9.]+' | \
        sort -n | \
        awk -v n="$n" 'NR==int((n+1)/2){print}'
}

append_summary_header() {
    {
        echo "Quick Summary (median values):"
        echo "  (HP)=hugepage"
        echo "  (WARM)=warm=5 steady-state large working set"
        echo "  (COLD)=evict_slc random + warm=0 single-pass"
        echo ""
        printf "  %-48s %9s  %-20s %10s\n" "Label" "Size" "Mode" "Latency"
        printf "  %-48s %9s  %-20s %10s\n" \
            "$(printf '%0.s-' {1..48})" "---------" "--------------------" "----------"
    } >> "$SUMMARY_FILE"
}

append_summary_header

run_chase_median() {
    local cpu="$1"
    local size_kb="$2"
    local label="$3"
    local warm="$4"
    local fr="$5"
    local mode="$6"

    echo ""
    echo "  --- [$label] cpu=$cpu size=${size_kb}KB mode=${mode} warm=$warm fr=$fr ---"

    local -a results=()
    local run
    local out
    local rc
    local fail_count=0

    for run in $(seq 1 "$MEDIAN_RUNS"); do
        out="$(taskset -c "$cpu" "$CHASE_BIN" "$size_kb" "$warm" "$fr" "$SEED" 0 1 2>&1)"
        rc=$?

        if [ "$rc" -ne 0 ]; then
            echo "[ERROR] chase failed run=$run label='$label' rc=$rc"
            echo "$out"
            {
                echo "[ERROR] chase failed run=$run label='$label' rc=$rc"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        if ! printf '%s\n' "$out" | grep -q 'latency = '; then
            echo "[ERROR] no latency parsed run=$run label='$label'"
            {
                echo "[ERROR] no latency parsed run=$run label='$label'"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        results+=("$out")
    done

    local median
    median="$(get_median_lat "${results[@]}")"

    echo "  [lat]" "${results[0]}"

    if [ -z "$median" ]; then
        echo "  [median/$MEDIAN_RUNS] latency = INVALID ns/access"
        echo "[FATAL] empty median for label='$label'"
        exit 3
    fi

    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"

    printf "  %-48s %9s  %-20s %8s ns\n" \
        "$label" "${size_kb}KB" "$mode" "$median" >> "$SUMMARY_FILE"

    if [ "$fail_count" -ne 0 ]; then
        echo "[WARN] label='$label' fail_count=$fail_count; check $ERROR_FILE"
    fi
}

run_cold_median() {
    local cpu="$1"
    local size_kb="$2"
    local label="$3"

    echo ""
    echo "  --- [$label] cpu=$cpu size=${size_kb}KB mode=cold/rand+warm0 ---"

    local -a results=()
    local run
    local out
    local rc
    local fail_count=0

    for run in $(seq 1 "$MEDIAN_RUNS"); do
        echo "    [evict] run=$run taskset -c $cpu $EVICT_BIN --evict_mb=$EVICT_MB --verbose"
        taskset -c "$cpu" "$EVICT_BIN" --evict_mb="$EVICT_MB" --verbose
        rc=$?
        if [ "$rc" -ne 0 ]; then
            echo "[ERROR] evict failed run=$run label='$label' rc=$rc"
            echo "[ERROR] evict failed run=$run label='$label' rc=$rc" >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        out="$(taskset -c "$cpu" "$CHASE_BIN" "$size_kb" 0 1 "$SEED" 0 1 2>&1)"
        rc=$?

        if [ "$rc" -ne 0 ]; then
            echo "[ERROR] chase cold failed run=$run label='$label' rc=$rc"
            echo "$out"
            {
                echo "[ERROR] chase cold failed run=$run label='$label' rc=$rc"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        if ! printf '%s\n' "$out" | grep -q 'latency = '; then
            echo "[ERROR] no cold latency parsed run=$run label='$label'"
            {
                echo "[ERROR] no cold latency parsed run=$run label='$label'"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        results+=("$out")
    done

    local median
    median="$(get_median_lat "${results[@]}")"

    echo "  [lat]" "${results[0]}"

    if [ -z "$median" ]; then
        echo "  [median/$MEDIAN_RUNS] latency = INVALID ns/access"
        echo "[FATAL] empty cold median for label='$label'"
        exit 3
    fi

    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"

    printf "  %-48s %9s  %-20s %8s ns\n" \
        "$label" "${size_kb}KB" "cold/rand+warm0" "$median" >> "$SUMMARY_FILE"

    if [ "$fail_count" -ne 0 ]; then
        echo "[WARN] label='$label' fail_count=$fail_count; check $ERROR_FILE"
    fi
}

# ------------------------------------------------------------
# Core list
# Format: cpu:name
# ------------------------------------------------------------
CORES=(
    "0:C0-A725"
    "10:C1-A725"
    "5:C0-X925"
    "15:C1-X925"
)

# ================================================================
# Section 9.1: Cold DRAM baseline
# ================================================================
if [ "$WARM_ONLY" -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "# Section 9.1: DRAM HP cold baseline"
    echo "#   evict_slc random $EVICT_MB MB + chase_pmu warm=0 fr=1"
    echo "============================================================"

    for size_kb in $SIZES_KB; do
        for entry in "${CORES[@]}"; do
            cpu="${entry%%:*}"
            name="${entry#*:}"
            run_cold_median "$cpu" "$size_kb" "${name}-DRAMcold ${size_kb}KB"
        done
    done
fi

# ================================================================
# Section 9.2: Warm large-WS baseline
# ================================================================
if [ "$COLD_ONLY" -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "# Section 9.2: DRAM HP warm large working-set baseline"
    echo "#   chase_pmu warm=5 fr=1"
    echo "============================================================"

    for size_kb in $SIZES_KB; do
        for entry in "${CORES[@]}"; do
            cpu="${entry%%:*}"
            name="${entry#*:}"
            run_chase_median "$cpu" "$size_kb" "${name}-DRAMwarm ${size_kb}KB" "$WARM_PASSES" 1 "warm/hugepage"
        done
    done
fi

# ================================================================
# Done
# ================================================================
echo ""
echo "============================================================"
echo "=== Done ==="
echo "OUTFILE      : $OUTFILE"
echo "SUMMARY_FILE : $SUMMARY_FILE"
echo "ERROR_FILE   : $ERROR_FILE"
echo "============================================================"

echo ""
cat "$SUMMARY_FILE"

echo ""
echo "# File check:"
ls -lh "$OUTFILE" "$SUMMARY_FILE" "$ERROR_FILE" 2>/dev/null || true

if [ -s "$ERROR_FILE" ]; then
    echo ""
    echo "[WARN] ERROR_FILE is not empty: $ERROR_FILE"
else
    echo ""
    echo "[OK] No command-level errors recorded."
fi
