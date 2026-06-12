#!/bin/bash
# ================================================================
# GB10 PMU Cache Validation v2.7.8-section7-fixed
#
# Section 7 only:
#   X925 L2 fine scan + L3 distributed-slice fine scan
#
# Fixes vs previous section7:
#   FIX-01: use absolute SCRIPT_DIR / ROOT_DIR paths, no fragile ../
#   FIX-02: fail-fast if chase_pmu missing or not executable
#   FIX-03: summary is written online into SUMMARY_FILE, no awk on OUTFILE
#   FIX-04: raw/summary filenames share the same timestamp
#   FIX-05: validate each run output; empty median => block failure
#   FIX-06: print exact binary path and output paths
#
# Usage:
#   chmod +x run_v2.7.8_section7_fixed.sh
#   ./run_v2.7.8_section7_fixed.sh
#
# Optional:
#   CHASE_BIN=/absolute/path/to/chase_pmu ./run_v2.7.8_section7_fixed.sh
#
# ================================================================

set -o pipefail
set -u

cd "$(dirname "$0")"

CHASE_BIN="../tools/bin/chase_pmu"
EVICT_BIN="../tools/bin/evict_slc"
EVICT_MB=32
SEED=42
MEDIAN_RUNS=7   # BUG-09 FIX: 3 → 7

# ------------------------------------------------------------
# Path resolution
# ------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_PWD="$(pwd)"

# Timestamp shared by raw + summary
DATE_TAG="$(date +%Y%m%d)"
TS="$(date +%Y%m%d_%H%M%S)"

# ------------------------------------------------------------
# Locate chase_pmu
# ------------------------------------------------------------
if [ -n "${CHASE_BIN:-}" ]; then
    CHASE_BIN_ABS="$CHASE_BIN"
else
    CANDIDATES=(
        "$SCRIPT_DIR/../tools/bin/chase_pmu"
        "$SCRIPT_DIR/tools/bin/chase_pmu"
        "$SCRIPT_DIR/../../tools/bin/chase_pmu"
        "$RUN_PWD/../tools/bin/chase_pmu"
        "$RUN_PWD/tools/bin/chase_pmu"
    )

    CHASE_BIN_ABS=""
    for p in "${CANDIDATES[@]}"; do
        if [ -x "$p" ]; then
            CHASE_BIN_ABS="$(cd "$(dirname "$p")" && pwd)/$(basename "$p")"
            break
        fi
    done
fi

# ------------------------------------------------------------
# Determine project root for data output
# Priority:
#   1. If chase_pmu found at <root>/tools/bin/chase_pmu, root=<root>
#   2. Else fallback to SCRIPT_DIR/..
# ------------------------------------------------------------
if [ -n "${CHASE_BIN_ABS:-}" ] && [[ "$CHASE_BIN_ABS" == */tools/bin/chase_pmu ]]; then
    ROOT_DIR="$(dirname "$(dirname "$(dirname "$CHASE_BIN_ABS")")")"
else
    ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

OUTDIR="$ROOT_DIR/data/${DATE_TAG}_v2.7.8_section7/raw"
mkdir -p "$OUTDIR"

OUTFILE="$OUTDIR/run_${TS}.txt"
SUMMARY_FILE="$OUTDIR/summary_${TS}.txt"
ERROR_FILE="$OUTDIR/error_${TS}.txt"

: > "$SUMMARY_FILE"
: > "$ERROR_FILE"

# ------------------------------------------------------------
# Logging: tee raw log
# ------------------------------------------------------------
exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation v2.7.8-section7-fixed"
echo "# Date         : $(date)"
echo "# SCRIPT_DIR   : $SCRIPT_DIR"
echo "# RUN_PWD      : $RUN_PWD"
echo "# ROOT_DIR     : $ROOT_DIR"
echo "# OUTFILE      : $OUTFILE"
echo "# SUMMARY_FILE : $SUMMARY_FILE"
echo "# ERROR_FILE   : $ERROR_FILE"
echo "# ------------------------------------------------------------"

# ------------------------------------------------------------
# Fail-fast checks
# ------------------------------------------------------------
if [ -z "${CHASE_BIN_ABS:-}" ]; then
    echo "[FATAL] chase_pmu binary not found."
    echo "[FATAL] Tried candidates:"
    printf '  %s\n' "${CANDIDATES[@]:-}"
    echo ""
    echo "Fix options:"
    echo "  1) Put script under the same project layout as v2.7.7"
    echo "  2) Or run with explicit path:"
    echo "       CHASE_BIN=/absolute/path/to/chase_pmu $0"
    exit 2
fi

if [ ! -e "$CHASE_BIN_ABS" ]; then
    echo "[FATAL] CHASE_BIN does not exist: $CHASE_BIN_ABS"
    exit 2
fi

if [ ! -x "$CHASE_BIN_ABS" ]; then
    echo "[FATAL] CHASE_BIN is not executable: $CHASE_BIN_ABS"
    echo "Try:"
    echo "  chmod +x \"$CHASE_BIN_ABS\""
    exit 2
fi

echo "# Binary       : $CHASE_BIN_ABS"

# taskset availability
if ! command -v taskset >/dev/null 2>&1; then
    echo "[FATAL] taskset not found. Install util-linux."
    exit 2
fi

# Quick smoke test: do not use taskset yet, just test binary launches
echo ""
echo "# Smoke test: $CHASE_BIN_ABS 4 1 1 42 0 0"
if ! "$CHASE_BIN_ABS" 4 1 1 42 0 0 >/tmp/chase_pmu_smoke_${TS}.log 2>&1; then
    echo "[FATAL] chase_pmu smoke test failed."
    echo "---- smoke log ----"
    cat /tmp/chase_pmu_smoke_${TS}.log
    echo "-------------------"
    exit 2
fi
rm -f /tmp/chase_pmu_smoke_${TS}.log

# CPU availability
for c in 5 15; do
    if [ ! -d "/sys/devices/system/cpu/cpu$c" ]; then
        echo "[FATAL] cpu$c does not exist on this system."
        exit 2
    fi
done

# Hugepage check
NR_HP=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo 0)
echo "# HugePages    : nr_hugepages=$NR_HP"
if [ "$NR_HP" -lt 32 ]; then
    echo "[WARN] nr_hugepages=$NR_HP < 32, hugepage alloc may fallback to 4K."
    echo "[HINT] echo 64 | sudo tee /proc/sys/vm/nr_hugepages"
fi

# Frequency record
echo ""
echo "# CPU frequency snapshot:"
for c in 5 15; do
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

echo ""
echo "# MEDIAN_RUNS  : $MEDIAN_RUNS"
echo "# SEED         : $SEED"
echo "# WARM_PASSES  : $WARM_PASSES"
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
        echo "  [anomaly]=cross-slice structural artifact, excluded from boundary analysis"
        echo ""
        printf "  %-56s %8s  %-22s %10s\n" "Label" "Size" "Mode" "Latency"
        printf "  %-56s %8s  %-22s %10s\n" \
            "$(printf '%0.s-' {1..56})" "--------" "----------------------" "----------"
    } >> "$SUMMARY_FILE"
}

append_summary_header

# ------------------------------------------------------------
# Core runner
# ------------------------------------------------------------
run_warm_hp_kb_common() {
    local cpu="$1"
    local size_kb="$2"
    local label="$3"
    local warm_passes="$4"
    local anomaly="${5:-0}"

    local fr
    fr="$(pick_fr_kb "$size_kb")"

    echo ""
    if [ "$anomaly" -eq 1 ]; then
        echo "  --- [$label]  cpu=$cpu  size=${size_kb}KB  mode=warm/hugepage  fr=$fr  [anomaly/cross-slice] ---"
    else
        echo "  --- [$label]  cpu=$cpu  size=${size_kb}KB  mode=warm/hugepage  fr=$fr ---"
    fi

    local -a results=()
    local run
    local out
    local fail_count=0

    for run in $(seq 1 "$MEDIAN_RUNS"); do
        out="$(taskset -c "$cpu" "$CHASE_BIN_ABS" "$size_kb" "$warm_passes" "$fr" "$SEED" 0 1 2>&1)"
        local rc=$?

        # Print full error immediately if command failed
        if [ "$rc" -ne 0 ]; then
            echo "[ERROR] run=$run label='$label' cpu=$cpu size=${size_kb}KB rc=$rc"
            echo "$out"
            {
                echo "[ERROR] run=$run label='$label' cpu=$cpu size=${size_kb}KB rc=$rc"
                echo "$out"
            } >> "$ERROR_FILE"
            fail_count=$((fail_count + 1))
        fi

        # Validate output contains latency
        if ! printf '%s\n' "$out" | grep -q 'latency = '; then
            echo "[ERROR] no latency parsed: run=$run label='$label'"
            {
                echo "[ERROR] no latency parsed: run=$run label='$label'"
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
        echo "[FATAL] Median is empty for label='$label'. Stop to avoid garbage data."
        echo "[FATAL] Check ERROR_FILE: $ERROR_FILE"
        exit 3
    fi

    if [ "$anomaly" -eq 1 ]; then
        echo "  [median/$MEDIAN_RUNS] latency = $median ns/access  [anomaly/cross-slice]"
        printf "  %-56s %8s  %-22s %8s ns%s\n" \
            "$label" "${size_kb}KB" "warm/hugepage" "$median" " [anomaly]" >> "$SUMMARY_FILE"
    else
        echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
        printf "  %-56s %8s  %-22s %8s ns\n" \
            "$label" "${size_kb}KB" "warm/hugepage" "$median" >> "$SUMMARY_FILE"
    fi

    if [ "$fail_count" -ne 0 ]; then
        echo "[WARN] label='$label' had fail_count=$fail_count, but median parsed. Check $ERROR_FILE"
    fi
}

run_warm_hp_kb() {
    run_warm_hp_kb_common "$1" "$2" "$3" "$4" 0
}

run_warm_hp_kb_anomaly() {
    run_warm_hp_kb_common "$1" "$2" "$3" "$4" 1
}

# ================================================================
# Section 7
# ================================================================
echo ""
echo "============================================================"
echo "# Section 7: X925 L3 Distributed Slice fine scan"
echo "#   C0-X925 cpu5  @3.9GHz  L2=2MB  L3=8MB"
echo "#   C1-X925 cpu15 @3.9GHz  L2=2MB  L3=16MB"
echo "#   Mode: hugepage/warm"
echo "#   4096KB = [anomaly/cross-slice], excluded from boundary"
echo "#   force_rounds: <=8192KB -> 38, >8192KB -> 5"
echo "============================================================"

# ------------------------------------------------------------
# 7.1 X925 L2 fine scan
# ------------------------------------------------------------
echo ""
echo "  -- Section 7.1: X925 L2 fine scan (HP, KB granularity) --"

for size_kb in 256 384 512 640 768 1024 1536 2048; do
    run_warm_hp_kb 5  "$size_kb" "C0-X925-L2fine ${size_kb}KB(HP)" "$WARM_PASSES"
    run_warm_hp_kb 15 "$size_kb" "C1-X925-L2fine ${size_kb}KB(HP)" "$WARM_PASSES"
done

# ------------------------------------------------------------
# 7.2 C0-X925 L3 distributed-slice scan
# ------------------------------------------------------------
echo ""
echo "  -- Section 7.2: C0-X925 L3 distributed-slice scan (HP) --"

for size_kb in 1024 2048 3072; do
    run_warm_hp_kb 5 "$size_kb" "C0-X925-L3slice ${size_kb}KB(HP)" "$WARM_PASSES"
done

run_warm_hp_kb_anomaly 5 4096 "C0-X925-L3slice 4096KB(HP)[anomaly]" "$WARM_PASSES"

for size_kb in 5120 6144 7168 8192 9216 10240 11264 12288; do
    run_warm_hp_kb 5 "$size_kb" "C0-X925-L3slice ${size_kb}KB(HP)" "$WARM_PASSES"
done

# ------------------------------------------------------------
# 7.3 C1-X925 L3 distributed-slice scan
# ------------------------------------------------------------
echo ""
echo "  -- Section 7.3: C1-X925 L3 distributed-slice scan (HP) --"

for size_kb in 1024 2048 3072; do
    run_warm_hp_kb 15 "$size_kb" "C1-X925-L3slice ${size_kb}KB(HP)" "$WARM_PASSES"
done

run_warm_hp_kb_anomaly 15 4096 "C1-X925-L3slice 4096KB(HP)[anomaly]" "$WARM_PASSES"

for size_kb in 5120 6144 7168 8192 9216 10240 11264 12288 14336 16384 18432 20480; do
    run_warm_hp_kb 15 "$size_kb" "C1-X925-L3slice ${size_kb}KB(HP)" "$WARM_PASSES"
done

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

# Final file existence check
echo ""
echo "# File check:"
ls -lh "$OUTFILE" "$SUMMARY_FILE" "$ERROR_FILE" 2>/dev/null || true

# Warn if error file non-empty
if [ -s "$ERROR_FILE" ]; then
    echo ""
    echo "[WARN] ERROR_FILE is not empty: $ERROR_FILE"
    echo "       Please inspect it before accepting results."
else
    echo ""
    echo "[OK] No command-level errors recorded."
fi
