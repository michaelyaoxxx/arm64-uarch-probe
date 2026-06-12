#!/bin/bash
# GB10 PMU Cache Validation  v2.7.6
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
#   v2.7.5 - BUG-07 FIX: force_rounds 统一（消除 meas_rounds 变量干扰）
#              问题：force_rounds=0 时 binary 内部默认 meas_rounds=50，
#                    4K page 下 meas_rounds 过多导致 L3 set conflict 累积
#              修正1: Section 2/4 L3-hit/L3-hit+ force_rounds: 0 → 5
#              修正2: Section 5 X925 hugepage force_rounds: 1 → 5
#   v2.7.6 - BUG-08 FIX: 4K page warm 测量包含结构性 TLB miss 开销
#              根因：A725 L2 DTLB ~1024 entries，4MB/4K page = 1024 PTE，
#                    pointer chase 随机访问导致 DTLB thrashing
#              实测：C1-A725 4MB, 4K page, fr=38: ~8.4ns (7次稳定, σ≈0.4ns)
#                    C1-A725 4MB, hugepage,  fr=5:   4.17ns
#                    delta = 4.2ns = 纯 TLB miss 开销，force_rounds 无法消除
#              修正：Section 1~4 warm 点双轨测量
#                    (HP) hugepage：纯 cache 结构延迟（ground truth）
#                    (4K) 4K page ：实际软件访问延迟（含 TLB 开销，作对比参考）
#              force_rounds 策略：
#                    size ≤ 8MB → force_rounds=38（保证任意物理地址下 warm 收敛）
#                    size >  8MB → force_rounds=5 （大 size 单轮已充分）
#            BUG-09 FIX: MEDIAN_RUNS 3 → 7
#                    3次中位数无法覆盖物理地址随机性（bank/slice 亲和性随机）
#                    7次取第4个中位数，可过滤偶发 bank conflict 高点和 warm 不足低点
# ============================================================

cd "$(dirname "$0")"

CHASE_BIN="../tools/bin/chase_pmu"
EVICT_BIN="../tools/bin/evict_slc"
EVICT_MB=32
SEED=42
MEDIAN_RUNS=7   # BUG-09 FIX: 3 → 7

SLC_MB=16

OUTDIR="../data/$(date +%Y%m%d)_v2.7.6/raw"
mkdir -p $OUTDIR
OUTFILE="$OUTDIR/run_$(date +%Y%m%d_%H%M%S).txt"

exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation  v2.7.6"
echo "# Binary    : $(pwd)/$CHASE_BIN"
echo "# Evict     : $(pwd)/$EVICT_BIN  (evict_mb=$EVICT_MB)"
echo "# Date      : $(date)"
echo "# MEDIAN_RUNS=$MEDIAN_RUNS (BUG-09 FIX: 3→7, 覆盖物理地址随机性)"
echo "# force_rounds 策略 (BUG-08 FIX):"
echo "#   size ≤ 8MB → force_rounds=38 (保证任意地址 warm 收敛)"
echo "#   size >  8MB → force_rounds=5  (大size单轮充分)"
echo "# 双轨测量 (BUG-08 FIX):"
echo "#   (HP) hugepage = 纯 cache 结构延迟 (ground truth, 无 TLB 噪声)"
echo "#   (4K) 4K page  = 实际软件访问延迟 (含 TLB 开销, 对比参考)"
echo "#   TLB delta 参考: C1-A725 4MB: 4K~8.4ns vs HP~4.2ns, delta=4.2ns"
echo "# Topology:"
echo "#   C0-X925 cpu5  3900MHz L2=2MB    L3=8MB"
echo "#   C0-A725 cpu0  2808MHz L2=512KB  L3=8MB  (effective ~8MB, spills to SLC)"
echo "#   C1-X925 cpu15 3900MHz L2=2MB    L3=16MB"
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
# force_rounds 选择器
# BUG-08 FIX: size ≤ 8MB → 38, size > 8MB → 5
# ----------------------------------------------------------------
pick_fr_mb() {
    local size_mb=$1
    if [ $size_mb -le 8 ]; then echo 38; else echo 5; fi
}
pick_fr_kb() {
    local size_kb=$1
    if [ $size_kb -le 8192 ]; then echo 38; else echo 5; fi
}

# ----------------------------------------------------------------
# warm 模式（4K page, MB 粒度）
# ----------------------------------------------------------------
run_warm() {
    local cpu=$1 size_mb=$2 label=$3 warm_passes=$4
    local size_kb=$((size_mb * 1024))
    local fr=$(pick_fr_mb $size_mb)
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_mb}MB  mode=warm  fr=$fr ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $fr $SEED)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# warm 模式（4K page, KB 粒度）
run_warm_kb() {
    local cpu=$1 size_kb=$2 label=$3 warm_passes=$4
    local fr=$(pick_fr_kb $size_kb)
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_kb}KB  mode=warm  fr=$fr ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $fr $SEED)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# hugepage warm 模式（MB 粒度）
run_warm_hp() {
    local cpu=$1 size_mb=$2 label=$3 warm_passes=$4
    local size_kb=$((size_mb * 1024))
    local fr=$(pick_fr_mb $size_mb)
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_mb}MB  mode=warm/hugepage  fr=$fr ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $fr $SEED 0 1)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# hugepage warm 模式（KB 粒度）
run_warm_hp_kb() {
    local cpu=$1 size_kb=$2 label=$3 warm_passes=$4
    local fr=$(pick_fr_kb $size_kb)
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_kb}KB  mode=warm/hugepage  fr=$fr ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $fr $SEED 0 1)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access"
}

# ----------------------------------------------------------------
# BUG-04 修正后的 double-evict（cold 模式，4K page）
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
# warm0 模式（cold，4K page）
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
# 双轨：(HP) hugepage ground truth + (4K) 含 TLB 对比
# ================================================================
CPU=5; L3=8
echo ""
echo "============================================================"
echo "# Section 1: C0-X925  cpu5 @ 3.9GHz  L2=2MB  L3=${L3}MB"
echo "# (HP)=hugepage ground truth  (4K)=4K page incl. TLB cost"
echo "============================================================"

echo ""
echo "  -- Section 1a: C0-X925 hugepage (HP) --"
run_warm_hp $CPU 1  "C0-X925 L2-hit(HP)"          5
run_warm_hp $CPU 2  "C0-X925 L2->L3 boundary(HP)" 5
run_warm_hp $CPU 4  "C0-X925 L3-hit(HP)"          5
run_warm_hp $CPU 6  "C0-X925 L3-hit+(HP)"         5
run_warm_hp $CPU 8  "C0-X925 L3-tail(HP)"         5

echo ""
echo "  -- Section 1b: C0-X925 4K page (4K) --"
run_warm $CPU 1  "C0-X925 L2-hit(4K)"          5
run_warm $CPU 2  "C0-X925 L2->L3 boundary(4K)" 5
run_warm $CPU 4  "C0-X925 L3-hit(4K)"          5
run_warm $CPU 6  "C0-X925 L3-hit+(4K)"         5
run_warm $CPU 8  "C0-X925 L3-tail(4K)"         5

echo ""
echo "  -- Section 1c: C0-X925 cold --"
for size in 4 6 8; do
    run_cold_double_evict $CPU $size $L3 "C0-X925 ${size}MB dbl-evict"
done
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
echo "#   effective L3 ~8MB; >8MB spills directly to SLC (~15ns)"
echo "# (HP)=hugepage ground truth  (4K)=4K page incl. TLB cost"
echo "#   TLB delta ref: 4MB 4K~8.4ns vs HP~4.2ns, delta=4.2ns"
echo "============================================================"

echo ""
echo "  -- Section 2a: C0-A725 L2 boundary scan (4K, KB granularity) --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C0-A725 L2-scan ${size_kb}KB(4K)" 5
done

echo ""
echo "  -- Section 2b: C0-A725 hugepage (HP) --"
run_warm_hp $CPU 4  "C0-A725 L3-hit(HP)"   5
run_warm_hp $CPU 6  "C0-A725 L3-hit+(HP)"  5
run_warm_hp $CPU 8  "C0-A725 L3-tail(HP)"  5
run_warm_hp $CPU 12 "C0-A725 SLC-hit(HP)"  5
run_warm_hp $CPU 16 "C0-A725 SLC-hit+(HP)" 5

echo ""
echo "  -- Section 2c: C0-A725 4K page (4K) --"
run_warm $CPU 4  "C0-A725 L3-hit(4K)"   5
run_warm $CPU 6  "C0-A725 L3-hit+(4K)"  5
run_warm $CPU 8  "C0-A725 L3-tail(4K)"  5
run_warm $CPU 12 "C0-A725 SLC-hit(4K)"  5
run_warm $CPU 16 "C0-A725 SLC-hit+(4K)" 5

echo ""
echo "  -- Section 2d: C0-A725 cold --"
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
echo "# (HP)=hugepage ground truth  (4K)=4K page incl. TLB cost"
echo "============================================================"

echo ""
echo "  -- Section 3a: C1-X925 hugepage (HP) --"
run_warm_hp $CPU 1  "C1-X925 L2-hit(HP)"          5
run_warm_hp $CPU 2  "C1-X925 L2->L3 boundary(HP)" 5
run_warm_hp $CPU 4  "C1-X925 L3-hit(HP)"          5
run_warm_hp $CPU 8  "C1-X925 L3-hit+(HP)"         5
run_warm_hp $CPU 12 "C1-X925 L3-hit++(HP)"        5
run_warm_hp $CPU 16 "C1-X925 L3-tail(HP)"         5

echo ""
echo "  -- Section 3b: C1-X925 4K page (4K) --"
run_warm $CPU 1  "C1-X925 L2-hit(4K)"          5
run_warm $CPU 2  "C1-X925 L2->L3 boundary(4K)" 5
run_warm $CPU 4  "C1-X925 L3-hit(4K)"          5
run_warm $CPU 8  "C1-X925 L3-hit+(4K)"         5
run_warm $CPU 12 "C1-X925 L3-hit++(4K)"        5
run_warm $CPU 16 "C1-X925 L3-tail(4K)"         5

echo ""
echo "  -- Section 3c: C1-X925 cold --"
for size in 8 12 16; do
    run_cold_double_evict $CPU $size $L3 "C1-X925 ${size}MB dbl-evict"
done
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
echo "#   effective L3 ~8MB (near-slice); 8~16MB = far-slice (~10ns)"
echo "# (HP)=hugepage ground truth  (4K)=4K page incl. TLB cost"
echo "#   TLB delta ref: 4MB 4K~8.4ns vs HP~4.2ns, delta=4.2ns"
echo "============================================================"

echo ""
echo "  -- Section 4a: C1-A725 L2 boundary scan (4K, KB granularity) --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C1-A725 L2-scan ${size_kb}KB(4K)" 5
done

echo ""
echo "  -- Section 4b: C1-A725 hugepage (HP) --"
run_warm_hp $CPU 4  "C1-A725 L3-hit(HP)"   5
run_warm_hp $CPU 6  "C1-A725 L3-hit+(HP)"  5
run_warm_hp $CPU 8  "C1-A725 L3-tail(HP)"  5
run_warm_hp $CPU 12 "C1-A725 SLC-hit(HP)"  5
run_warm_hp $CPU 16 "C1-A725 SLC-hit+(HP)" 5

echo ""
echo "  -- Section 4c: C1-A725 4K page (4K) --"
run_warm $CPU 4  "C1-A725 L3-hit(4K)"   5
run_warm $CPU 6  "C1-A725 L3-hit+(4K)"  5
run_warm $CPU 8  "C1-A725 L3-tail(4K)"  5
run_warm $CPU 12 "C1-A725 SLC-hit(4K)"  5
run_warm $CPU 16 "C1-A725 SLC-hit+(4K)" 5

echo ""
echo "  -- Section 4d: C1-A725 cold --"
for size in 8 12 16; do
    run_cold_double_evict $CPU $size $L3 "C1-A725 ${size}MB dbl-evict"
done
for size in 18 24 32 64; do
    run_cold_warm0 $CPU $size "C1-A725 ${size}MB cold/warm0"
done

# ================================================================
# Section 5: 四核 hugepage L3 boundary 对比扫描
# force_rounds: ≤8MB→38, >8MB→5 (由 run_warm_hp_kb 内部 pick_fr_kb 决定)
# ================================================================
echo ""
echo "============================================================"
echo "# Section 5: hugepage L3 boundary scan (4-core comparison)"
echo "#   C0-A725 cpu0 / C0-X925 cpu5 / C1-A725 cpu10 / C1-X925 cpu15"
echo "#   A725: boundary ~8MB (C0直溢SLC ~15ns, C1有far-slice台阶 ~10ns)"
echo "#   X925: 无边界跳变，单调递减（Slice均匀分布效应）"
echo "#   force_rounds: ≤8192KB→38, >8192KB→5 (自动选择)"
echo "============================================================"

NR_HP=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo 0)
if [ "$NR_HP" -lt 16 ]; then
    echo "  [WARN] nr_hugepages=$NR_HP < 16, hugepage alloc may fallback to 4K"
    echo "  [HINT] echo 32 | sudo tee /proc/sys/vm/nr_hugepages"
fi

# ≤8192KB 用 fr=38，>8192KB 用 fr=5（pick_fr_kb 自动处理）
BOUNDARY_SIZES_KB="4096 6144 7168 7680 8192 8704 9216 9728 10240 12288 14336 16384"

echo ""
echo "  -- Section 5.1: C0-A725 cpu0 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hp_kb 0  $size_kb "C0-A725-HP ${size_kb}KB" 5
done

echo ""
echo "  -- Section 5.2: C0-X925 cpu5 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hp_kb 5  $size_kb "C0-X925-HP ${size_kb}KB" 5
done

echo ""
echo "  -- Section 5.3: C1-A725 cpu10 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hp_kb 10 $size_kb "C1-A725-HP ${size_kb}KB" 5
done

echo ""
echo "  -- Section 5.4: C1-X925 cpu15 hugepage boundary --"
for size_kb in $BOUNDARY_SIZES_KB; do
    run_warm_hp_kb 15 $size_kb "C1-X925-HP ${size_kb}KB" 5
done

echo ""
echo "============================================================"
echo "=== Done: $OUTFILE ==="
echo "============================================================"

# ----------------------------------------------------------------
# Quick Summary
# ----------------------------------------------------------------
echo ""
echo "Quick Summary (median values):"
echo "  (HP)=hugepage/ground-truth  (4K)=4K-page/incl-TLB"
echo "  (W0)=cold/warm0  (DE)=cold/dbl-evict"
echo ""
printf "  %-52s %8s  %-20s %10s\n" "Label" "Size" "Mode" "Latency"
printf "  %-52s %8s  %-20s %10s\n" \
    "$(printf '%0.s-' {1..52})" "--------" "--------------------" "----------"
awk '
    /--- \[/ {
        match($0, /\[([^\]]+)\]/, a); label = a[1]
        if (match($0, /size=([0-9]+)(M|K)B/, s))
            size = s[1] s[2] "B"
        else
            size = "-"
        if (match($0, /mode=([^ ]+)/, m))
            mode = m[1]
        else
            mode = "-"
    }
    /\[median\/[0-9]/ {
        match($0, /latency = ([0-9.]+)/, b)
        printf "  %-52s %8s  %-20s %8s ns\n", label, size, mode, b[1]
    }
' "$OUTFILE"
