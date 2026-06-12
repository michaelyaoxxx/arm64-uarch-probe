#!/bin/bash
# ================================================================
# GB10 PMU Cache Validation v2.7.9-section8
#
# Section 8:
#   SLC capacity sweep on A725 cores
#
# Goals:
#   1. C0-A725 / C1-A725 SLC warm capacity boundary
#   2. cold validation using evict_slc v1.2 --evict_mb=64
#
# Directory layout:
#   root/
#     runner/section8_slc_capacity.sh
#     tools/bin/chase_pmu
#     tools/bin/evict_slc
#     data/
#
# Usage:
#   cd /home/michaelyao1/gb10-arch/runner
#   chmod +x section8_slc_capacity.sh
#   ./section8_slc_capacity.sh
#
# Optional:
#   MEDIAN_RUNS=5 ./section8_slc_capacity.sh
#   WARM_ONLY=1 ./section8_slc_capacity.sh
#   COLD_ONLY=1 ./section8_slc_capacity.sh
#
# ================================================================

set -o pipefail
set -u

CHASE_BIN="../tools/bin/chase_pmu"
EVICT_BIN="../tools/bin/evict_slc"

DATE_TAG="$(date +%Y%m%d)"
TS="$(date +%Y%m%d_%H%M%S)"

OUTDIR="../data/${DATE_TAG}_v2.7.9_section8_slc/raw"
mkdir -p "$OUTDIR"

OUTFILE="$OUTDIR/run_${TS}.txt"
SUMMARY_FILE="$OUTDIR/summary_${TS}.txt"
ERROR_FILE="$OUTDIR/error_${TS}.txt"

: > "$SUMMARY_FILE"
: > "$ERROR_FILE"

exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation v2.7.9-section8"
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

for c in 0 10; do
    if [ ! -d "/sys/devices/system/cpu/cpu$c" ]; then
        echo "[FATAL] cpu$c does not exist"
        exit 2
    fi
done

NR_HP=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo 0)
echo "# HugePages    : nr_hugepages=$NR_HP"
if [ "$NR_HP" -lt 32 ]; then
    echo "[WARN] nr_hugepages=$NR_HP < 32, hugepage alloc may fallback to 4K"
    echo "[HINT] echo 64 | sudo tee /proc/sys/vm/nr_hugepages"
fi

echo ""
echo "# CPU frequency snapshot:"
for c in 0 10; do
    echo -n "  cpu$c "
    if [ -f "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq" ]; then
        cat "/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq"
    else
        echo "scaling_cur_freq=N/A"
    fi
done

# ------------------------------------------------------------
# Parameters
# ------------------------------------------------------------
SEED="${SEED:-42}"
MEDIAN_RUNS="${MEDIAN_RUNS:-7}"
WARM_PASSES="${WARM_PASSES:-5}"
EVICT_MB="${EVICT_MB:-64}"

# Control switches
WARM_ONLY="${WARM_ONLY:-0}"
COLD_ONLY="${COLD_ONLY:-0}"

echo ""
echo "# MEDIAN_RUNS  : $MEDIAN_RUNS"
echo "# SEED         : $SEED"
echo "# WARM_PASSES  : $WARM_PASSES"
echo "# EVICT_MB     : $EVICT_MB"
echo "# WARM_ONLY    : $WARM_ONLY"
echo "# COLD_ONLY    : $COLD_ONLY"
echo "# force_rounds : <=8192KB -> 38, >8192KB -> 5"
echo "============================================================"

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
pick_fr_kb() {
    local size_kb="$1"
    if [ "$size_kb" -le 8192 ]; then
        echo 38
    else
        echo 5
    fi
}

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
        echo "  (HP)=hugepage/ground-truth"
        echo "  (WARM)=warm=5 SLC/L3 steady-state"
        echo "  (COLD)=evict_slc + warm=0 single-pass"
        echo ""
        printf "  %-48s %8s  %-20s %10s\n" "Label" "Size" "Mode" "Latency"
        printf "  %-48s %8s  %-20s %10s\n" \
            "$(printf '%0.s-' {1..48})" "--------" "--------------------" "----------"
    } >> "$SUMMARY_FILE"
}

append_summary_header

run_chase_block() {
    local cpu="$1"
    local size_kb="$2"
    local label="$3"
    local warm="$4"
    local force_rounds="$5"
    local mode="$6"

    echo ""
    echo "  --- [$label] cpu=$cpu size=${size_kb}KB mode=${mode} warm=$warm fr=$force_rounds ---"

    local -a results=()
    local run
    local out
    local rc
    local fail_count=0

    for run in $(seq 1 "$MEDIAN_RUNS"); do
        out="$(taskset -c "$cpu" "$CHASE_BIN" "$size_kb" "$warm" "$force_rounds" "$SEED" 0 1 2>&1)"
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

    printf "  %-48s %8s  %-20s %8s ns\n" \
        "$label" "${size_kb}KB" "$mode" "$median" >> "$SUMMARY_FILE"

    if [ "$fail_count" -ne 0 ]; then
        echo "[WARN] label='$label' fail_count=$fail_count; check $ERROR_FILE"
    fi
}

run_warm_hp_kb() {
    local cpu="$1"
    local size_kb="$2"
    local label="$3"
    local fr
    fr="$(pick_fr_kb "$size_kb")"

    run_chase_block "$cpu" "$size_kb" "$label" "$WARM_PASSES" "$fr" "warm/hugepage"
}

run_cold_hp_kb_random() {
    local cpu="$1"
    local size_kb="$2"
    local label="$3"

    echo ""
    echo "  --- [$label] cpu=$cpu size=${size_kb}KB mode=cold/random-evict+warm0 ---"

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

    printf "  %-48s %8s  %-20s %8s ns\n" \
        "$label" "${size_kb}KB" "cold/rand+warm0" "$median" >> "$SUMMARY_FILE"

    if [ "$fail_count" -ne 0 ]; then
        echo "[WARN] label='$label' fail_count=$fail_count; check $ERROR_FILE"
    fi
}

# ================================================================
# Section 8.1: Warm SLC sweep
# ================================================================
if [ "$COLD_ONLY" -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "# Section 8.1: A725 HP warm SLC capacity sweep"
    echo "#   C0-A725 cpu0"
    echo "#   C1-A725 cpu10"
    echo "#   range: 10MB~24MB, 256KB step"
    echo "============================================================"

    for size_kb in $(seq 10240 256 24576); do
        run_warm_hp_kb 0  "$size_kb" "C0-A725-SLCwarm ${size_kb}KB"
        run_warm_hp_kb 10 "$size_kb" "C1-A725-SLCwarm ${size_kb}KB"
    done
fi

# ================================================================
# Section 8.2: Cold validation points
# ================================================================
if [ "$WARM_ONLY" -eq 0 ]; then
    echo ""
    echo "============================================================"
    echo "# Section 8.2: A725 HP cold validation"
    echo "#   evict_slc random $EVICT_MB MB + chase_pmu warm=0 fr=1"
    echo "============================================================"

    for size_kb in 12288 14336 16384 18432 20480 24576; do
        run_cold_hp_kb_random 0  "$size_kb" "C0-A725-SLCcold ${size_kb}KB"
        run_cold_hp_kb_random 10 "$size_kb" "C1-A725-SLCcold ${size_kb}KB"
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
