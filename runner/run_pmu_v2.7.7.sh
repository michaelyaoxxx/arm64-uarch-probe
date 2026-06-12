#!/bin/bash
# GB10 PMU Cache Validation  v2.7.7
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
#   v2.7.7 - BUG-10 FIX: 4MB hugepage 测量点结构性异常
#              根因：4MB = 2个 2MB hugepage，物理地址恰好跨两个 L3 Slice，
#                    pointer chain head/tail 各在一个 Slice，latency 为混合值
#              实测：C0-A725 3MB HP=3.56ns, 4MB HP=5.98ns, 5MB HP=3.70ns
#                    4MB 比相邻点高 ~2.4ns，是结构性异常非随机噪声
#              修正：Section 5 boundary scan 起始点从 4096KB 改为 5120KB
#                    4096KB 保留但标注 [anomaly/cross-slice]，不参与边界判断
#                    Section 2b/4b hugepage warm 点同步处理
#            BUG-11 FIX: C1-A725 L3 boundary 精度不足
#              根因：v2.7.6 Section 5.3 步长 ~2MB，无法分辨 near/far-slice 过渡区
#              实测：C1-A725 far-slice 过渡区在 9~11MB（渐变，非锐利边界）
#                    9216KB=4.25ns → 10752KB=4.82ns → 11264KB=5.63ns
#              修正：C1-A725 Section 5.3 在 9~12MB 区间增加 256KB 步长细粒度扫描
#                    其余三核（C0-A725/C0-X925/C1-X925）保持原粗粒度步长
# ============================================================

cd "$(dirname "$0")"

CHASE_BIN="../tools/bin/chase_pmu"
EVICT_BIN="../tools/bin/evict_slc"
EVICT_MB=32
SEED=42
MEDIAN_RUNS=7   # BUG-09 FIX: 3 → 7

SLC_MB=16

OUTDIR="../data/$(date +%Y%m%d)_v2.7.7/raw"
mkdir -p $OUTDIR
OUTFILE="$OUTDIR/run_$(date +%Y%m%d_%H%M%S).txt"

exec > >(tee "$OUTFILE") 2>&1

echo "# GB10 PMU Cache Validation  v2.7.7"
echo "# Binary    : $(pwd)/$CHASE_BIN"
echo "# Evict     : $(pwd)/$EVICT_BIN  (evict_mb=$EVICT_MB)"
echo "# Date      : $(date)"
echo "# MEDIAN_RUNS=$MEDIAN_RUNS"
echo "# force_rounds: ≤8MB→38, >8MB→5"
echo "# 双轨: (HP)=hugepage ground truth  (4K)=4K page incl. TLB"
echo "# 4MB HP [anomaly/cross-slice]: 跨Slice结构性异常，不参与边界判断"
echo "#   实测: C0-A725 3MB=3.56ns, 4MB=5.98ns, 5MB=3.70ns"
echo "# C1-A725 L3 三段式 (BUG-11):"
echo "#   near-slice ≤9MB ~3.8ns | far-slice 9~11MB 4.2~5.6ns | SLC >11MB 6.9ns+"
echo "# Topology:"
echo "#   C0-X925 cpu5  3900MHz L2=2MB   L3=8MB"
echo "#   C0-A725 cpu0  2808MHz L2=512KB L3=8MB  (effective ~10MB)"
echo "#   C1-X925 cpu15 3900MHz L2=2MB   L3=16MB"
echo "#   C1-A725 cpu10 2808MHz L2=512KB L3=16MB (near≤9MB, far 9~11MB)"
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

# hugepage warm 模式（KB 粒度）+ anomaly 标注
# BUG-10: 4MB 等已知 cross-slice 异常点：测量保留，Summary 中标注 [anomaly]
run_warm_hp_kb_anomaly() {
    local cpu=$1 size_kb=$2 label=$3 warm_passes=$4
    local fr=$(pick_fr_kb $size_kb)
    echo ""
    echo "  --- [$label]  cpu=$cpu  size=${size_kb}KB  mode=warm/hugepage  fr=$fr  [anomaly/cross-slice] ---"
    local -a results=()
    for run in $(seq 1 $MEDIAN_RUNS); do
        results+=("$(taskset -c $cpu $CHASE_BIN $size_kb $warm_passes $fr $SEED 0 1)")
    done
    local median=$(get_median_lat "${results[@]}")
    echo "  [lat]" "${results[0]}"
    echo "  [median/$MEDIAN_RUNS] latency = $median ns/access  [anomaly/cross-slice]"
}

# ----------------------------------------------------------------
# double-evict（cold 模式，4K page）
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
echo "#   effective L3 ~10MB; >10MB spills to SLC"
echo "# (HP)=hugepage ground truth  (4K)=4K page incl. TLB cost"
echo "============================================================"

echo ""
echo "  -- Section 2a: C0-A725 L2 boundary scan (4K, KB granularity) --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C0-A725 L2-scan ${size_kb}KB(4K)" 5
done

echo ""
echo "  -- Section 2b: C0-A725 hugepage (HP) --"
echo "  -- NOTE: 4MB point is [anomaly/cross-slice], kept for reference only --"
run_warm_hp_kb_anomaly $CPU 4096 "C0-A725 4MB(HP)[anomaly]" 5
run_warm_hp $CPU 5  "C0-A725 L3-hit(HP)"   5
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
echo "#   near-slice: ≤9MB ~3.8ns"
echo "#   far-slice:  9~11MB 4.2~5.6ns (渐变)"
echo "#   SLC:        >11MB 6.9ns+"
echo "# (HP)=hugepage ground truth  (4K)=4K page incl. TLB cost"
echo "============================================================"

echo ""
echo "  -- Section 4a: C1-A725 L2 boundary scan (4K, KB granularity) --"
for size_kb in 128 256 384 448 480 512 576 640 768 1024; do
    run_warm_kb $CPU $size_kb "C1-A725 L2-scan ${size_kb}KB(4K)" 5
done

echo ""
echo "  -- Section 4b: C1-A725 hugepage (HP) --"
echo "  -- NOTE: 4MB point is [anomaly/cross-slice], kept for reference only --"
run_warm_hp_kb_anomaly $CPU 4096 "C1-A725 4MB(HP)[anomaly]" 5
run_warm_hp $CPU 5  "C1-A725 L3-hit(HP)"   5
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
# BUG-10 FIX: 起始点从 4096KB → 5120KB，4096KB 单独标注 anomaly
# BUG-11 FIX: C1-A725 9~12MB 区间 256KB 步长细粒度扫描
# ================================================================
echo ""
echo "============================================================"
echo "# Section 5: hugepage L3 boundary scan (4-core comparison)"
echo "#   BUG-10: 4096KB [anomaly/cross-slice] 单独测量，不参与边界判断"
echo "#   BUG-11: C1-A725 9~12MB 区间 256KB 步长细粒度扫描"
echo "#   C0-A725: 锐利边界 ~10MB (4.0→6.4ns)"
echo "#   C1-A725: 渐变边界 near≤9MB / far 9~11MB / SLC>11MB"
echo "#   X925:    无边界，distributed slice，latency 单调下降"
echo "#   force_rounds: ≤8192KB→38, >8192KB→5"
echo "============================================================"

NR_HP=$(cat /proc/sys/vm/nr_hugepages 2>/dev/null || echo 0)
if [ "$NR_HP" -lt 32 ]; then
    echo "  [WARN] nr_hugepages=$NR_HP < 32, hugepage alloc may fallback to 4K"
    echo "  [HINT] echo 64 | sudo tee /proc/sys/vm/nr_hugepages"
fi

# 粗粒度扫描点（所有四核共用，BUG-10: 从 5120KB 开始，跳过 4096KB）
BOUNDARY_COARSE_KB="5120 6144 7168 7680 8192 8704 9216 9728 10240 12288 14336 16384"

# C1-A725 专用：9~12MB 区间 256KB 步长（BUG-11 FIX）
# seq 9216 256 12288 生成: 9216 9472 9728 9984 10240 10496 10752 11008 11264 11520 11776 12032 12288
C1A725_FINE_KB=$(seq 9216 256 12288 | tr '\n' ' ')

echo ""
echo "  -- Section 5.0: 4MB [anomaly/cross-slice] 参考测量 (4 cores) --"
echo "  -- 仅作结构性异常记录，不参与 L3 boundary 判断 --"
run_warm_hp_kb_anomaly 0  4096 "C0-A725-HP 4096KB[anomaly]" 5
run_warm_hp_kb_anomaly 5  4096 "C0-X925-HP 4096KB[anomaly]" 5
run_warm_hp_kb_anomaly 10 4096 "C1-A725-HP 4096KB[anomaly]" 5
run_warm_hp_kb_anomaly 15 4096 "C1-X925-HP 4096KB[anomaly]" 5

echo ""
echo "  -- Section 5.1: C0-A725 cpu0 hugepage boundary (粗粒度, 5~16MB) --"
for size_kb in $BOUNDARY_COARSE_KB; do
    run_warm_hp_kb 0 $size_kb "C0-A725-HP ${size_kb}KB" 5
done

echo ""
echo "  -- Section 5.2: C0-X925 cpu5 hugepage boundary (粗粒度, 5~16MB) --"
for size_kb in $BOUNDARY_COARSE_KB; do
    run_warm_hp_kb 5 $size_kb "C0-X925-HP ${size_kb}KB" 5
done

echo ""
echo "  -- Section 5.3: C1-A725 cpu10 hugepage boundary --"
echo "  -- 粗粒度: 5~9MB --"
for size_kb in 5120 6144 7168 7680 8192; do
    run_warm_hp_kb 10 $size_kb "C1-A725-HP ${size_kb}KB" 5
done
echo "  -- 细粒度: 9~12MB 区间 256KB 步长 (BUG-11 FIX) --"
for size_kb in $C1A725_FINE_KB; do
    run_warm_hp_kb 10 $size_kb "C1-A725-HP ${size_kb}KB" 5
done
echo "  -- 粗粒度: 14~16MB --"
for size_kb in 14336 16384; do
    run_warm_hp_kb 10 $size_kb "C1-A725-HP ${size_kb}KB" 5
done

echo ""
echo "  -- Section 5.4: C1-X925 cpu15 hugepage boundary (粗粒度, 5~16MB) --"
for size_kb in $BOUNDARY_COARSE_KB; do
    run_warm_hp_kb 15 $size_kb "C1-X925-HP ${size_kb}KB" 5
done

# Section 6: L1 hit + A725/X925 L2 HP 补测
# 目标: 补齐 L1 latency，消除 A725/X925 L2 的 TLB 噪声
echo "# Section 6: L1 hit + L2 HP boundary"
echo ""
echo "  -- 6.1 A725 L1 区间 (4K page，TLB 全命中，无需 HP) --"
for size_kb in 4 8 16 32 48 64 96 128; do
    run_warm_kb 0  $size_kb "C0-A725 L1-scan ${size_kb}KB(4K)" 5
    run_warm_kb 10 $size_kb "C1-A725 L1-scan ${size_kb}KB(4K)" 5
done

echo ""
echo "  -- 6.2 X925 L1 区间 (4K page) --"
for size_kb in 4 8 16 32 48 64 96 128; do
    run_warm_kb 5  $size_kb "C0-X925 L1-scan ${size_kb}KB(4K)" 5
    run_warm_kb 15 $size_kb "C1-X925 L1-scan ${size_kb}KB(4K)" 5
done

echo ""
echo "  -- 6.3 A725 L2 HP (消除 TLB，ground truth) --"
for size_kb in 128 192 256 320 384 448 512 640; do
    run_warm_hp_kb 0  $size_kb "C0-A725 L2-HP ${size_kb}KB" 5
    run_warm_hp_kb 10 $size_kb "C1-A725 L2-HP ${size_kb}KB" 5
done

echo ""
echo "  -- 6.4 X925 L2 HP boundary --"
for size_kb in 512 768 1024 1536 2048; do
    run_warm_hp_kb 5  $size_kb "C0-X925 L2-HP ${size_kb}KB" 5
    run_warm_hp_kb 15 $size_kb "C1-X925 L2-HP ${size_kb}KB" 5
done

echo "# Section 7: C0-X925 L2-HP 256/384KB "
echo ""
# 追加到 Section 7 或单独执行
run_warm_hp_kb 5  256 "C0-X925 L2-HP 256KB" 5
run_warm_hp_kb 5  384 "C0-X925 L2-HP 384KB" 5
run_warm_hp_kb 15 256 "C1-X925 L2-HP 256KB" 5
run_warm_hp_kb 15 384 "C1-X925 L2-HP 384KB" 5

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
echo "  [anomaly]=cross-slice structural artifact, excluded from boundary analysis"
echo ""
printf "  %-56s %8s  %-22s %10s\n" "Label" "Size" "Mode" "Latency"
printf "  %-56s %8s  %-22s %10s\n" \
    "$(printf '%0.s-' {1..56})" "--------" "----------------------" "----------"
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
        anomaly = ($0 ~ /anomaly/) ? 1 : 0
    }
    /\[median\/[0-9]/ {
        match($0, /latency = ([0-9.]+)/, b)
        note = (anomaly == 1) ? " [anomaly]" : ""
        printf "  %-56s %8s  %-22s %8s ns%s\n", label, size, mode, b[1], note
    }
' "$OUTFILE"
