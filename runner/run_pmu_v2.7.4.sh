#!/bin/bash
# GB10 PMU Cache Validation  v2.7.4
# Changelog:
#   v2.7.1 - BUG-01 FIX: evict only in cold mode
#   v2.7.2 - BUG-02 FIX: 双模式框架（warm0 + double-evict）
#   v2.7.3 - BUG-03 FIX: 多次采样取中位数（消除单点噪声）
#            BUG-04 FIX: double-evict 流程修正
#              旧流程：evict→warm=1→evict→measure（第二次evict清掉L3，失效）
#              新流程：evict→warm=1→measure（evict已保证SLC干净，warm只填L3）
#              适用约束：size ≤ L3（SLC不会被warm污染）
#              size > L3：warm溢出进SLC，改用 warm0+evict 模式
#   v2.7.4 - BUG-05 FIX: A725 L3 有效容量标签修正（hugepage 实测）
#              C0-A725 cpu0:  L3 有效容量 ~8MB，>8MB 直接溢出 SLC (~15ns)
#              C1-A725 cpu10: L3 有效容量 ~8MB（近端 slice），8~16MB 远端 slice (~10ns)
#              Section 2/4 标签修正：L3-hit++/L3-tail → SLC-hit/SLC-hit+
#              新增 Section 5: 四核 hugepage L3 boundary 对比扫描
#            BUG-06 FIX: Quick Summary 补全 size 字段
# ============================================================

cd "$(dirname "$0")"

CHASE_BIN="../tools/bin/chase_pmu"
EVICT_BIN="../tools/bin/evict_slc"
EVICT_MB=32
SEED=42
MEDIAN_RUNS=3

SLC_MB=16

OUTDIR="../data/$(date +%Y%m%d)_v2.7.4/raw"
mkdir -p $OUTDIR
OUTFILE="$OUTDIR/run_$(date +%Y%m%d_%H%M%S).txt"

exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation  v2.7.4"
echo "# Binary    : $(pwd)/$CHASE_BIN"
echo "# Evict     : $(pwd)/$EVICT_BIN  (evict_mb=$EVICT_MB)"
echo "# Date      : $(date)"
echo "# BUG-03 FIX: 多次采样取中位数 (MEDIAN_RUNS=$MEDIAN_RUNS)"
echo "# BUG-04 FIX: double-evict 流程修正（去掉第二次 evict）"
echo "#   新 dbl-evict 流程：evict(全清) → warm=1(填L3) → measure"
echo "#   适用：size ≤ L3（SLC 保持干净）"
echo "#   size > L3 时：warm 溢出进 SLC，改用 warm0 模式"
echo "# BUG-05 FIX: A725 L3 有效容量修正"
echo "#   C0-A725 cpu0:  effective L3 ~8MB，>8MB → SLC (~15ns)"
echo "#   C1-A725 cpu10: effective L3 ~8MB (near-slice)，8~16MB → far-slice (~10ns)"
echo "# BUG-06 FIX: Quick Summary 补全 size 字段"
echo "# Topology:"
echo "#   C0-X925 cpu5  3900MHz L2=2MB   L3=8MB"
echo "#   C0-A725 cpu0  2808MHz L2=512KB  L3=8MB  (effective ~8MB, spills to SLC)"
echo "#   C1-X925 cpu15 3900MHz L2=2MB   L3=16MB"
echo "#   C1-A725 cpu10 2808MHz L2=512KB  L3=16MB (effective ~8MB near-slice)"
echo "#   SLC=16MB (shared)  DRAM=128GB LPDDR5X"
echo "============================================================"

# ----------------------------------------------------------------
# 中位数工具函数
# ----------------------------------------------------------------
get_median_lat() {
    local -a lats=("$@")
    local n=${#lats[@]}
    printf '%s\n' "${lats[@]}" | \
        grep -oP '(?<=latency = )[0-9.]+' | \
        sort -n | \
        awk -v n=$n 'NR==int((n+1)/2){print}'
}

# ----------------------------------------------------------------
# warm 模式
# ----------------------------------------------------------------
run_warm() {
    local cpu=$1 size_mb=$2 label=$3 warm_passes=$4 force_rounds=$5
    local size_kb=$((size_mb * 1024))
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_mb}MB  mode=warm ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $force_rounds $SEED)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# warm 模式 KB 精度版
run_warm_kb() {
    local cpu=$1 size_kb=$2 label=$3 warm_passes=$4 force_rounds=$5
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_kb}KB  mode=warm ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $force_rounds $SEED)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# hugepage warm 模式
run_warm_hugepage() {
    local cpu=$1 size_mb=$2 label=$3 warm_passes=$4 force_rounds=$5
    local size_kb=$((size_mb * 1024))
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_mb}MB  mode=warm/hugepage ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $force_rounds $SEED 0 1)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# hugepage warm 模式 KB 精度版
run_warm_hugepage_kb() {
    local cpu=$1 size_kb=$2 label=$3 warm_passes=$4 force_rounds=$5
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_kb}KB  mode=warm/hugepage ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $force_rounds $SEED 0 1)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# ----------------------------------------------------------------
# BUG-04 修正后的 double-evict
# ----------------------------------------------------------------
run_cold_double_evict() {
    local cpu=$1 size_mb=$2 l3_mb=$3 label=$4
    local size_kb=$((size_mb * 1024))

    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_mb}MB  mode=cold/dbl-evict ---"

    if [ $size_mb -gt $l3_mb ]; then
        echo "  [SKIP dbl-evict] size(${size_mb}MB) > L3(${l3_mb}MB), SLC would be polluted"
        echo "  [FALLBACK to warm0]"
        run_cold_warm0 $cpu $size_mb "$label(fallback-warm0)"
        return
    fi

    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        taskset -c $cpu $EVICT_BIN --evict_mb=$EVICT_MB > /dev/null 2>&1
        taskset -c $cpu $CHASE_BIN $size_kb 1 0 $SEED 0 > /dev/null 2>&1
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb 0 1 $SEED 0)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# ----------------------------------------------------------------
# warm0 模式
# ----------------------------------------------------------------
run_cold_warm0() {
    local cpu=$1 size_mb=$2 label=$3
    local size_kb=$((size_mb * 1024))
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_mb}MB  mode=cold/warm0 ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        taskset -c $cpu $EVICT_BIN --evict_mb=$EVICT_MB > /dev/null 2>&1
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb 0 1 $SEED 0)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# ================================================================
# Section 1: C0-X925  cpu5  L3=8MB
# ================================================================
CPU=5; L3=8
echo ""
echo "============================================================"
echo "# Section 1: C0-X925  cpu5 @ 3.9GHz  L2=2MB  L3=${L3}MB"
echo "============================================================"

run_warm $CPU 1  "C0-X925 L2-hit"          5 0
run_warm $CPU 2  "C0-X925 L2->L3 boundary" 5 0
run_warm $CPU 4  "C0-X925 L3-hit"          5 0
run_warm $CPU 6  "C0-X925 L3-hit+"         5 0
run_warm $CPU 8  "C0-X925 L3-tail"         5 38

for size in 4 6 8; do
    run_cold_double_evict $CPU $size $L3 "C0-X925 ${size}MB dbl-evict"
done
for size in 10 12 16 20 32 64; do
    run_cold_warm0 $CPU $size "C0-X925 ${size}MB cold/warm0"
done

# ================================================================
# Section 2: C0-A725  cpu0  L3=8MB
# BUG-05: hugepage 实测 A725 L3 有效容量 ~8MB
#         >8MB 直接溢出 SLC (~15ns)，C0 无远端 slice 中间台阶
# ================================================================
CPU=0; L3=8
echo ""
echo "============================================================"
echo "# Section 2: C0-A725  cpu0 @ 2.808GHz  L2=512KB  L3=${L3}MB"
echo "#   BUG-05: effective L3 ~8MB; >8MB spills directly to SLC (~15ns)"
echo "============================================================"

echo ""
echo "  -- C0-A725 L2 KB-granularity boundary scan --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C0-A725 L2-scan ${size_kb}KB" 5 0
done

run_warm $CPU 4  "C0-A725 L3-hit"   5 0
run_warm $CPU 6  "C0-A725 L3-hit+"  5 0
run_warm $CPU 8  "C0-A725 L3-tail"  5 38
run_warm $CPU 12 "C0-A725 SLC-hit"  5 25
run_warm $CPU 16 "C0-A725 SLC-hit+" 5 19

for size in 4 6 8; do
    run_cold_double_evict $CPU $size $L3 "C0-A725 ${size}MB dbl-evict"
done
for size in 10 16 32 64; do
    run_cold_warm0 $CPU $size "C0-A725 ${size}MB cold/warm0"
done

# ================================================================
# Section 3: C1-X925  cpu15  L3=16MB
# ================================================================
CPU=15; L3=16
echo ""
echo "============================================================"
echo "# Section 3: C1-X925  cpu15 @ 3.9GHz  L2=2MB  L3=${L3}MB"
echo "============================================================"

run_warm $CPU 1  "C1-X925 L2-hit"          5 0
run_warm $CPU 2  "C1-X925 L2->L3 boundary" 5 0
run_warm $CPU 4  "C1-X925 L3-hit"          5 0
run_warm $CPU 8  "C1-X925 L3-hit+"         5 38
run_warm $CPU 12 "C1-X925 L3-hit++"        5 25
run_warm $CPU 16 "C1-X925 L3-tail"         5 19

for size in 8 12 16; do
    run_cold_double_evict $CPU $size $L3 "C1-X925 ${size}MB dbl-evict"
done
for size in 18 20 24 28 32 64; do
    run_cold_warm0 $CPU $size "C1-X925 ${size}MB cold/warm0"
done

# ================================================================
# Section 4: C1-A725  cpu10  L3=16MB
# BUG-05: hugepage 实测 A725 L3 有效容量 ~8MB（近端 slice）
#         8~16MB 命中远端 slice (~10ns)，非真实 L3-hit
# ================================================================
CPU=10; L3=16
echo ""
echo "============================================================"
echo "# Section 4: C1-A725  cpu10 @ 2.808GHz  L2=512KB  L3=${L3}MB"
echo "#   BUG-05: effective L3 ~8MB (near-slice); 8~16MB = far-slice (~10ns)"
echo "============================================================"

echo ""
echo "  -- C1-A725 L2 KB-granularity boundary scan --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C1-A725 L2-scan ${size_kb}KB" 5 0
done

run_warm $CPU 4  "C1-A725 L3-hit"   5 0
run_warm $CPU 6  "C1-A725 L3-hit+"  5 0
run_warm $CPU 8  "C1-A725 L3-tail"  5 38
run_warm $CPU 12 "C1-A725 SLC-hit"  5 25
run_warm $CPU 16 "C1-A725 SLC-hit+" 5 19

for size in 8 12 16; do
    run_cold_double_evict $CPU $size $L3 "C1-A725 ${size}MB dbl-evict"
done
for size in 18 24 32 64; do
    run_cold_warm0 $CPU $size "C1-A725 ${size}MB cold/warm0"
done

# ================================================================
# Section 5: 四核 hugepage L3 boundary 对比扫描
# ================================================================
echo ""
echo "============================================================"
echo "# Section 5: hugepage L3 boundary scan (4-core comparison)"
echo "#   C0-A725 cpu0 / C0-X925 cpu5 / C1-A725 cpu10 / C1-X925 cpu15"
echo "#   Expected: A725 boundary ~8MB; X925 no boundary up to 16MB"
echo "============================================================"

NR_HP=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo 0)
if [ "$NR_HP" -lt 16 ]; then
    echo "  [WARN] nr_hugepages=$NR_HP < 16, hugepage alloc may fallback to 4K"
    echo "  [HINT] echo 32 | sudo tee /proc/sys/vm/nr_hugepages"
fi

BOUNDARY_SIZES_KB="4096 6144 7168 7680 8192 8704 9216 9728 10240 12288 14336 16384"

echo ""
echo "  -- Section 5.1: C0-A725 cpu0 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hugepage_kb 0  $size_kb "C0-A725-HP ${size_kb}KB" 5 1
done

echo ""
echo "  -- Section 5.2: C0-X925 cpu5 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hugepage_kb 5  $size_kb "C0-X925-HP ${size_kb}KB" 5 1
done

echo ""
echo "  -- Section 5.3: C1-A725 cpu10 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hugepage_kb 10 $size_kb "C1-A725-HP ${size_kb}KB" 5 1
done

echo ""
echo "  -- Section 5.4: C1-X925 cpu15 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hugepage_kb 15 $size_kb "C1-X925-HP ${size_kb}KB" 5 1
done

echo ""
echo "============================================================"
echo "=== Done: $OUTFILE ==="
echo "============================================================"

# ----------------------------------------------------------------
# Quick Summary：提取 label + size + mode + median 四列输出
# BUG-06 FIX: 从 --- [...] cpu=X size=Y mode=Z 行同时抓 size 和 mode
# ----------------------------------------------------------------
echo ""
echo "Quick Summary (median values):"
echo "  (W)=warm  (W0)=cold/warm0  (DE)=cold/dbl-evict  (HP)=hugepage"
echo ""
printf "  %-44s %8s  %-18s %10s\n" "Label" "Size" "Mode" "Latency"
printf "  %-44s %8s  %-18s %10s\n" \
    "$(printf '%0.s-' {1..44})" "--------" "------------------" "----------"
awk '
    /--- \[/ {
        # 抓 label
        match($0, /\[([^\]]+)\]/, a); label = a[1]
        # 抓 size（支持 MB 和 KB）
        if (match($0, /size=([0-9]+)(M|K)B/, s))
            size = s[1] s[2] "B"
        else
            size = "-"
        # 抓 mode
        if (match($0, /mode=([^ ]+)/, m))
            mode = m[1]
        else
            mode = "-"
    }
    /\[median\/[0-9]/ {
        match($0, /latency = ([0-9.]+)/, b)
        printf "  %-44s %8s  %-18s %8s ns\n", label, size, mode, b[1]
    }
' "$OUTFILE"
