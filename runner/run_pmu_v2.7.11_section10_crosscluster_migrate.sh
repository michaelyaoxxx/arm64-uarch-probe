#!/bin/bash
# ================================================================
# GB10 PMU Cache Validation v2.7.11-section10
#
# Phase 2B-5:
#   Same-chain cross-core migration / remote-cache behavior
#
# Tool:
#   tools/bin/chase_migrate v1.0
#
# Directory layout:
#   root/
#     runner/section10_migrate.sh
#     tools/bin/chase_migrate
#     data/
#
# Usage:
#   cd /home/michaelyao1/gb10-arch/runner
#   chmod +x section10_migrate.sh
#   ./section10_migrate.sh
#
# Optional:
#   MEDIAN_RUNS=3 ./section10_migrate.sh
#   SIZES_KB="512 2048 8192 16384 32768" ./section10_migrate.sh
#   LOCAL_ONLY=1 ./section10_migrate.sh
#   MIGRATE_ONLY=1 ./section10_migrate.sh
#
# ================================================================

set -o pipefail
set -u

MIGRATE_BIN="../tools/bin/chase_migrate"

DATE_TAG="$(date +%Y%m%d)"
TS="$(date +%Y%m%d_%H%M%S)"

OUTDIR="../data/${DATE_TAG}_v2.7.11_section10_migrate/raw"
mkdir -p "$OUTDIR"

OUTFILE="$OUTDIR/run_${TS}.txt"
SUMMARY_FILE="$OUTDIR/summary_${TS}.txt"
ERROR_FILE="$OUTDIR/error_${TS}.txt"

: > "$SUMMARY_FILE"
: > "$ERROR_FILE"

exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation v2.7.11-section10"
echo "# Phase        : 2B-5 same-chain migration"
echo "# Date         : $(date)"
echo "# PWD          : $(pwd)"
echo "# MIGRATE_BIN  : $MIGRATE_BIN"
echo "# OUTFILE      : $OUTFILE"
echo "# SUMMARY_FILE : $SUMMARY_FILE"
echo "# ERROR_FILE   : $ERROR_FILE"
echo "# ------------------------------------------------------------"

# ------------------------------------------------------------
# Fail-fast checks
# ------------------------------------------------------------
if [ ! -x "$MIGRATE_BIN" ]; then
    echo "[FATAL] MIGRATE_BIN not executable: $MIGRATE_BIN"
    exit 2
fi

if ! "$MIGRATE_BIN" --help >/dev/null 2>&1; then
    echo "[FATAL] chase_migrate --help failed"
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
WARM_SRC="${WARM_SRC:-5}"
MEASURE_ROUNDS="${MEASURE_ROUNDS:-1}"
SLEEP_US="${SLEEP_US:-0}"
HUGEPAGE="${HUGEPAGE:-1}"
STRICT_HUGEPAGE="${STRICT_HUGEPAGE:-1}"

# default: 512KB, 2MB, 8MB, 16MB, 32MB, 64MB
SIZES_KB="${SIZES_KB:-512 2048 8192 16384 32768 65536}"

LOCAL_ONLY="${LOCAL_ONLY:-0}"
MIGRATE_ONLY="${MIGRATE_ONLY:-0}"

NR_HP=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo 0)

MAX_SIZE_KB=0
for s in $SIZES_KB; do
    if [ "$s" -gt "$MAX_SIZE_KB" ]; then
        MAX_SIZE_KB="$s"
    fi
done
REQUIRED_HP=$(( (MAX_SIZE_KB + 2047) / 2048 ))

echo "# HugePages       : nr_hugepages=$NR_HP"
echo "# MaxSizeKB       : $MAX_SIZE_KB"
echo "# Required HP     : >= $REQUIRED_HP x 2MB"
if [ "$HUGEPAGE" -eq 1 ] && [ "$STRICT_HUGEPAGE" -eq 1 ] && [ "$NR_HP" -lt "$REQUIRED_HP" ]; then
    echo "[FATAL] strict hugepage requested but nr_hugepages=$NR_HP < required=$REQUIRED_HP"
    echo "[HINT] sudo sh -c 'echo 128 > /proc/sys/vm/nr_hugepages'"
    exit 2
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
echo "# MEDIAN_RUNS     : $MEDIAN_RUNS"
echo "# SEED            : $SEED"
echo "# WARM_SRC        : $WARM_SRC"
echo "# MEASURE_ROUNDS  : $MEASURE_ROUNDS"
echo "# SLEEP_US        : $SLEEP_US"
echo "# HUGEPAGE        : $HUGEPAGE"
echo "# STRICT_HUGEPAGE : $STRICT_HUGEPAGE"
echo "# SIZES_KB        : $SIZES_KB"
echo "# LOCAL_ONLY      : $LOCAL_ONLY"
echo "# MIGRATE_ONLY    : $MIGRATE_ONLY"
echo "============================================================"

# ------------------------------------------------------------
# Summary header
# ------------------------------------------------------------
{
    echo "Quick Summary (median values):"
    echo "  local: src_cpu == dst_cpu"
    echo "  migrate: same chain warmed on src, measured on dst"
    echo ""
    printf "  %-36s %8s %8s %8s  %-12s %12s %12s %12s\n" \
        "Label" "SrcCPU" "DstCPU" "Size" "Mode" "SrcLat" "MigLat" "Penalty"
    printf "  %-36s %8s %8s %8s  %-12s %12s %12s %12s\n" \
        "$(printf '%0.s-' {1..36})" "--------" "--------" "--------" "------------" "------------" "------------" "------------"
} >> "$SUMMARY_FILE"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
median_from_list() {
    local n="$1"
    sort -n | awk -v n="$n" 'NR==int((n+1)/2){print}'
}

extract_src_lat() {
    grep -oP '(?<=>>> src_latency = )[0-9.]+' | head -1
}

extract_mig_lat() {
    grep -oP '(?<=>>> migrate_latency = )[0-9.]+' | head -1
}

extract_penalty() {
    grep -oP '(?<=>>> migrate_penalty = )[0-9.-]+' | head -1
}

run_one_block() {
    local src_cpu="$1"
    local dst_cpu="$2"
    local size_kb="$3"
    local label="$4"
    local mode="$5"

    echo ""
    echo "  --- [$label] src=$src_cpu dst=$dst_cpu size=${size_kb}KB mode=$mode ---"

    local -a src_lats=()
    local -a mig_lats=()
    local -a penalties=()

    local run
    local out
    local rc
    local fail_count=0

    for run in $(seq 1 "$MEDIAN_RUNS"); do
        out="$("$MIGRATE_BIN" \
            --src-cpu "$src_cpu" \
            --dst-cpu "$dst_cpu" \
            --size-kb "$size_kb" \
            --warm-src "$WARM_SRC" \
            --measure-rounds "$MEASURE_ROUNDS" \
            --measure-src 1 \
            --seed "$SEED" \
            --hugepage "$HUGEPAGE" \
            --strict-hugepage "$STRICT_HUGEPAGE" \
            --sleep-us "$SLEEP_US" \
            --label "$label" 2>&1)"
        rc=$?

        if [ "$rc" -ne 0 ]; then
            echo "[ERROR] run=$run label='$label' rc=$rc"
            echo "$out"
            {
                echo "[ERROR] run=$run label='$label' rc=$rc"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        if ! printf '%s\n' "$out" | grep -q 'hugepage_actual=1'; then
            echo "[ERROR] hugepage_actual != 1 run=$run label='$label'"
            {
                echo "[ERROR] hugepage_actual != 1 run=$run label='$label'"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        local src_lat
        local mig_lat
        local penalty

        src_lat="$(printf '%s\n' "$out" | extract_src_lat)"
        mig_lat="$(printf '%s\n' "$out" | extract_mig_lat)"
        penalty="$(printf '%s\n' "$out" | extract_penalty)"

        if [ -z "$src_lat" ] || [ -z "$mig_lat" ] || [ -z "$penalty" ]; then
            echo "[ERROR] parse latency failed run=$run label='$label'"
            {
                echo "[ERROR] parse latency failed run=$run label='$label'"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        else
            src_lats+=("$src_lat")
            mig_lats+=("$mig_lat")
            penalties+=("$penalty")
        fi

        if [ "$run" -eq 1 ]; then
            echo "  [sample/run1]"
            printf '%s\n' "$out" | grep -E '^(===|label=|src_cpu=|\[src\]|\[dst\]|>>>|\\[alloc\\]|\\[hugepage\\])' || true
        fi
    done

    if [ "${#mig_lats[@]}" -eq 0 ]; then
        echo "[FATAL] no valid latencies for label='$label'"
        exit 3
    fi

    local n="${#mig_lats[@]}"
    local src_med
    local mig_med
    local pen_med

    src_med="$(printf '%s\n' "${src_lats[@]}" | median_from_list "$n")"
    mig_med="$(printf '%s\n' "${mig_lats[@]}" | median_from_list "$n")"
    pen_med="$(printf '%s\n' "${penalties[@]}" | median_from_list "$n")"

    echo "  [median/$n] src_latency     = $src_med ns/access"
    echo "  [median/$n] migrate_latency = $mig_med ns/access"
    echo "  [median/$n] migrate_penalty = $pen_med ns/access"

    printf "  %-36s %8s %8s %8s  %-12s %10s ns %10s ns %10s ns\n" \
        "$label" "$src_cpu" "$dst_cpu" "${size_kb}KB" "$mode" "$src_med" "$mig_med" "$pen_med" \
        >> "$SUMMARY_FILE"

    if [ "$fail_count" -ne 0 ]; then
        echo "[WARN] label='$label' fail_count=$fail_count; check $ERROR_FILE"
    fi
}

# ------------------------------------------------------------
# CPU labels
# ------------------------------------------------------------
# C0-A725 cpu0
# C0-X925 cpu5
# C1-A725 cpu10
# C1-X925 cpu15

# local baseline cores
LOCAL_CORES=(
    "0:C0-A725"
    "5:C0-X925"
    "10:C1-A725"
    "15:C1-X925"
)

# migration pairs: src:dst:label
PAIRS=(
    "0:10:C0A725_to_C1A725"
    "10:0:C1A725_to_C0A725"
    "5:15:C0X925_to_C1X925"
    "15:5:C1X925_to_C0X925"
    "0:5:C0A725_to_C0X925"
    "5:0:C0X925_to_C0A725"
    "10:15:C1A725_to_C1X925"
    "15:10:C1X925_to_C1A725"
)

# ================================================================
# Section 10.1: local baseline
# ================================================================
if [ "$MIGRATE_ONLY" -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "# Section 10.1: Local same-core baseline src==dst"
    echo "============================================================"

    for size_kb in $SIZES_KB; do
        for entry in "${LOCAL_CORES[@]}"; do
            cpu="${entry%%:*}"
            name="${entry#*:}"
            run_one_block "$cpu" "$cpu" "$size_kb" "${name}_local_${size_kb}KB" "local"
        done
    done
fi

# ================================================================
# Section 10.2: migration pairs
# ================================================================
if [ "$LOCAL_ONLY" -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "# Section 10.2: Same-chain migration pairs"
    echo "============================================================"

    for size_kb in $SIZES_KB; do
        for p in "${PAIRS[@]}"; do
            src="${p%%:*}"
            rest="${p#*:}"
            dst="${rest%%:*}"
            label="${rest#*:}"
            run_one_block "$src" "$dst" "$size_kb" "${label}_${size_kb}KB" "migrate"
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
