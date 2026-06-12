#!/bin/bash
# GB10 PMU Cache Validation  v2.7.3
# Changelog:
#   v2.7.1 - BUG-01 FIX: evict only in cold mode
#   v2.7.2 - BUG-02 FIX: 双模式框架（warm0 + double-evict）
#   v2.7.3 - BUG-03 FIX: 多次采样取中位数（消除单点噪声）
#            BUG-04 FIX: double-evict 流程修正
#              旧流程：evict→warm=1→evict→measure（第二次evict清掉L3，失效）
#              新流程：evict→warm=1→measure（evict已保证SLC干净，warm只填L3）
#              适用约束：size ≤ L3（SLC不会被warm污染）
#              size > L3：warm溢出进SLC，改用 warm0+evict 模式
# ============================================================

cd "$(dirname "$0")"

CHASE_BIN="../tools/bin/chase_pmu"
EVICT_BIN="../tools/bin/evict_slc"
EVICT_MB=32
SEED=42
MEDIAN_RUNS=3   # BUG-03：每个测试点采样次数，取中位数

# 拓扑
SLC_MB=16

OUTDIR="../data/$(date +%Y%m%d)_v2.7.3/raw"
mkdir -p $OUTDIR
OUTFILE="$OUTDIR/run_$(date +%Y%m%d_%H%M%S).txt"

exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation  v2.7.3"
echo "# Binary    : $(pwd)/$CHASE_BIN"
echo "# Evict     : $(pwd)/$EVICT_BIN  (evict_mb=$EVICT_MB)"
echo "# Date      : $(date)"
echo "# BUG-03 FIX: 多次采样取中位数 (MEDIAN_RUNS=$MEDIAN_RUNS)"
echo "# BUG-04 FIX: double-evict 流程修正（去掉第二次 evict）"
echo "#   新 dbl-evict 流程：evict(全清) → warm=1(填L3) → measure"
echo "#   适用：size ≤ L3（SLC 保持干净）"
echo "#   size > L3 时：warm 溢出进 SLC，改用 warm0 模式"
echo "# Topology:"
echo "#   C0-X925 cpu5  3900MHz L2=2MB  L3=8MB"
echo "#   C0-A725 cpu0  2808MHz L2=512KB L3=8MB"
echo "#   C1-X925 cpu15 3900MHz L2=2MB  L3=16MB"
echo "#   C1-A725 cpu10 2808MHz L2=512KB L3=16MB"
echo "#   SLC=16MB (shared)  DRAM=128GB LPDDR5X"
echo "============================================================"

# ----------------------------------------------------------------
# 中位数工具函数
# 输入：多行 ">>> latency = X.XX ns/access" 的输出
# 输出：中位数延迟值（ns）
# ----------------------------------------------------------------
get_median_lat() {
    # 从多次运行结果中提取延迟，排序取中位数
    local -a lats=("$@")
    local n=${#lats[@]}
    # 用 awk 排序取中位数
    printf '%s\n' "${lats[@]}" | \
        grep -oP '(?<=latency = )[0-9.]+' | \
        sort -n | \
        awk -v n=$n 'NR==int((n+1)/2){print}'
}

# ----------------------------------------------------------------
# warm 模式（BUG-03：多次采样取中位数）
# ----------------------------------------------------------------
run_warm() {
    local cpu=$1 size_mb=$2 label=$3 warm_passes=$4 force_rounds=$5
    local size_kb=$((size_mb * 1024))
    echo ""
    echo "  --- [$label]  cpu$cpu  size=${size_mb}MB  mode=warm ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $force_rounds $SEED)")
    done
    local median=$(get_median_lat "${results[@]}")
    # 打印第一次完整输出（含 header）
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# warm 模式 KB 精度版（用于 L2=512KB 等小容量 cache 边界扫描）
# ----------------------------------------------------------------
run_warm_kb() {
    local cpu=$1 size_kb=$2 label=$3 warm_passes=$4 force_rounds=$5
    echo ""
    echo "  --- [$label]  cpu$cpu  size=${size_kb}KB  mode=warm ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $force_rounds $SEED)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# ----------------------------------------------------------------
# BUG-04 修正后的 double-evict（新流程：去掉第二次 evict）
# 适用：size ≤ L3（SLC 不被 warm 污染）
# 流程：evict(全清) → warm=1(填L3) → measure(warm=0)
# ----------------------------------------------------------------
run_cold_double_evict() {
    local cpu=$1 size_mb=$2 l3_mb=$3 label=$4
    local size_kb=$((size_mb * 1024))

    echo ""
    echo "  --- [$label]  cpu$cpu  size=${size_mb}MB  mode=cold/dbl-evict(v2.7.3) ---"

    # size > L3：warm 会溢出到 SLC，dbl-evict 无法保证 SLC 干净，降级为 warm0
    if [ $size_mb -gt $l3_mb ]; then
        echo "  [SKIP dbl-evict] size(${size_mb}MB) > L3(${l3_mb}MB), SLC would be polluted"
        echo "  [FALLBACK to warm0]"
        run_cold_warm0 $cpu $size_mb "$label(fallback-warm0)"
        return
    fi

    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        # Step1: 全清 L3+SLC
        taskset -c $cpu $EVICT_BIN --evict_mb=$EVICT_MB > /dev/null 2>&1
        # Step2: warm=1 填 L3（size≤L3，不溢出 SLC）
        taskset -c $cpu $CHASE_BIN $size_kb 1 0 $SEED 0 > /dev/null 2>&1
        # Step3: 直接测量（SLC 干净，L3 有数据）
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb 0 1 $SEED 0)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# ----------------------------------------------------------------
# warm0 模式（BUG-03：多次采样取中位数）
# 流程：evict(全清) → measure(warm=0)
# 物理含义：init_chain 残留 + SLC 部分命中的混合延迟
# ----------------------------------------------------------------
run_cold_warm0() {
    local cpu=$1 size_mb=$2 label=$3
    local size_kb=$((size_mb * 1024))
    echo ""
    echo "  --- [$label]  cpu$cpu  size=${size_mb}MB  mode=cold/warm0 ---"
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

# warm 区
run_warm $CPU 1  "C0-X925 L2-hit"          5 0
run_warm $CPU 2  "C0-X925 L2->L3 boundary" 5 0
run_warm $CPU 4  "C0-X925 L3-hit"          5 0
run_warm $CPU 6  "C0-X925 L3-hit+"         5 0
run_warm $CPU 8  "C0-X925 L3-tail"         5 38

# BUG-04 修正的 dbl-evict（size ≤ L3=8MB，全部有效）
# 注：size=8MB 恰好等于 L3，warm=1 可能有少量溢出，保留观察
for size in 4 6 8; do
    run_cold_double_evict $CPU $size $L3 "C0-X925 ${size}MB dbl-evict"
done

# size > L3：warm0 模式（SLC hit rate 衰减曲线）
for size in 10 12 16 20 32 64; do
    run_cold_warm0 $CPU $size "C0-X925 ${size}MB cold/warm0"
done

# ================================================================
# Section 2: C0-A725  cpu0  L3=8MB
# ================================================================
CPU=0; L3=8
echo ""
echo "============================================================"
echo "# Section 2: C0-A725  cpu0 @ 2.808GHz  L2=512KB  L3=${L3}MB"
echo "============================================================"

# A725 L2=512KB，warm 区用 KB 级 size（脚本传 MB 有精度损失，此处用近似）
# A725 L2=512KB KB 粒度边界扫描
echo ""
echo "  -- C0-A725 L2 KB-granularity boundary scan --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C0-A725 L2-scan ${size_kb}KB" 5 0
done
run_warm $CPU 4  "C0-A725 L3-hit"          5 0
run_warm $CPU 6  "C0-A725 L3-hit+"         5 0
run_warm $CPU 8  "C0-A725 L3-tail"         5 38

for size in 4 6 8; do
    run_cold_double_evict $CPU $size $L3 "C0-A725 ${size}MB dbl-evict"
done
for size in 10 12 16 20 32 64; do
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

# dbl-evict 有效区：size ≤ L3=16MB
for size in 8 12 16; do
    run_cold_double_evict $CPU $size $L3 "C1-X925 ${size}MB dbl-evict"
done
# size > L3：warm0
for size in 18 20 24 28 32 64; do
    run_cold_warm0 $CPU $size "C1-X925 ${size}MB cold/warm0"
done

# ================================================================
# Section 4: C1-A725  cpu10  L3=16MB
# ================================================================
CPU=10; L3=16
echo ""
echo "============================================================"
echo "# Section 4: C1-A725  cpu10 @ 2.808GHz  L2=512KB  L3=${L3}MB"
echo "============================================================"

# A725 L2=512KB KB 粒度边界扫描
echo ""
echo "  -- C1-A725 L2 KB-granularity boundary scan --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C1-A725 L2-scan ${size_kb}KB" 5 0
done
run_warm $CPU 4  "C1-A725 L3-hit"          5 0
run_warm $CPU 8  "C1-A725 L3-hit+"         5 38
run_warm $CPU 12 "C1-A725 L3-hit++"        5 25
run_warm $CPU 16 "C1-A725 L3-tail"         5 19

for size in 8 12 16; do
    run_cold_double_evict $CPU $size $L3 "C1-A725 ${size}MB dbl-evict"
done
for size in 18 20 24 28 32 64; do
    run_cold_warm0 $CPU $size "C1-A725 ${size}MB cold/warm0"
done

echo ""
echo "============================================================"
echo "=== Done: $OUTFILE ==="
echo "============================================================"

# ----------------------------------------------------------------
# Quick Summary：提取 label + median 配对输出
# ----------------------------------------------------------------
echo ""
echo "Quick Summary (median values):"
echo "  (W)=warm  (W0)=cold/warm0  (DE)=cold/dbl-evict"
echo ""
printf "  %-52s %10s\n" "Label" "Latency"
printf "  %-52s %10s\n" "$(printf '%0.s-' {1..52})" "----------"
awk '
    /--- \[/         { match($0, /\[([^\]]+)\]/, a); label=a[1] }
    /\[median\/[0-9]/ { match($0, /latency = ([0-9.]+)/, b); 
                        printf "  %-52s %8s ns\n", label, b[1] }
' "$OUTFILE"
