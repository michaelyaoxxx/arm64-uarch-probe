# Phase 2B：延迟基准测试 · 子阶段拆分 & 基线评估

## Project Status

`arm64-uarch-probe` is being prepared as a reproducible and extensible v1.0
GB10 microarchitecture research baseline. GB10 is the authoritative measurement
platform; Mac and Linux ARM64 environments validate engineering behavior.

Current versioned `runner/run_pmu*.sh` scripts and tracked `data/` files are
frozen legacy evidence. The stable v1.0 runner will be introduced in later
phases.

Start with:

```sh
make help
make show-targets
make build
make check
```

See `docs/design/repository-contract.md` for collaboration, result-retention,
and hardware-handoff rules.

> 基于 v2.7.7 实测数据，2026-06-11

---

## 一、当前数据基线评估

### ✅ 可直接作为基线（7项，HIGH confidence）

| 指标                      | 基线值                    | 测量条件                      |
| ------------------------- | ------------------------- | ----------------------------- |
| L2 hit latency (X925)     | **3.03ns / 11.8c**        | HP, warm, 7×median            |
| L3 hit latency (X925)     | **4.2~4.7ns / 16~18c**    | HP, warm, distributed slice   |
| L3 hit latency (A725)     | **3.7~3.9ns / 10~11c**    | HP, warm, near-slice          |
| L3→SLC boundary (C0-A725) | **~9~9.5MB**              | 512KB步长扫描，边界锐利       |
| L3→SLC boundary (C1-A725) | **near≤9MB / far 9~11MB** | 256KB细粒度，三段式确认       |
| TLB overhead (X925)       | **+1.2~1.6ns / +4.5~6c**  | HP vs 4K 直接差值             |
| TLB overhead (A725)       | **+4.5~4.8ns / +12~13c**  | HP vs 4K 直接差值，多size一致 |

### ⚠️ 需补充验证（5项，MEDIUM/LOW confidence）

| 指标                  | 当前值             | 问题                                             | 补充方案                        |
| --------------------- | ------------------ | ------------------------------------------------ | ------------------------------- |
| L2 hit latency (A725) | ~9~11c（推算）     | L2 scan 用 4K page，含 TLB 噪声                  | **2B-1**：A725 小 size HP 补测  |
| SLC hit latency       | 7.0~7.5ns / 20~21c | SLC 容量未精确确认，warm 路径可能混入 L3 residue | **2B-3**：SLC 专项 + evict 验证 |
| DRAM latency (X925)   | ~100~111ns         | cold 路径用 4K page，含 TLB                      | **2B-4**：HP cold 补测          |
| DRAM latency (A725)   | ~128~135ns         | 同上                                             | **2B-4**：HP cold 补测          |
| SLC 容量精确值        | ~12~16MB（推断）   | 拐点推断，非直接测量                             | **2B-3**：SLC sweep 专项        |

### ❌ 完全空白（2项）

| 指标                  | 说明                 | 对应子阶段 |
| --------------------- | -------------------- | ---------- |
| L1 hit latency        | 需 <64KB working set | **2B-1**   |
| Cross-cluster latency | C0↔C1 via CMN mesh   | **2B-5**   |

---

## 二、子阶段拆分

### 2B-1：L1 hit + A725 L2 HP 补测（优先级：HIGH）

**目标**：补齐 L1 latency，消除 A725 L2 的 TLB 噪声

**测量点**：

```
A725 hugepage:  4KB, 8KB, 16KB, 32KB, 48KB, 64KB  → L1 hit
                96KB, 128KB, 192KB, 256KB           → L1→L2 boundary
                320KB, 384KB, 448KB, 512KB           → L2 hit (HP, no TLB)
X925 hugepage:  4KB, 8KB, 16KB, 32KB, 48KB, 64KB  → L1 hit（X925 L1=64KB）
```

**工具改动**：

- `chase_pmu` 当前最小 chain size 是否支持 4KB？需确认 `n_lines = size/64` 在 4KB 时 = 64 lines，pointer-chasing 链长度够用
- hugepage 最小粒度是 2MB，4KB~1MB 的 HP 测量需用 `mmap(MAP_HUGETLB)` + 手动限制 chain 范围，或改用 4K page + 已知 TLB 开销修正

**推荐方案**：直接用 4K page 测 L1（L1 hit 时 TLB 已在 L1 TLB 命中，penalty 极小），用 HP 测 L2（消除 L2 TLB 噪声）

**预期结果**：

- L1 hit：~1~2ns / 4~8 cycles（A725/X925 相近）
- A725 L2 HP：~3.5~4.5ns / 10~13c（去除 TLB 后）

---

### 2B-2：X925 L3 Distributed Slice 精细扫描（优先级：MEDIUM）

**目标**：量化 X925 L3 slice 分布特性，确认延迟单调下降的规律性

**当前问题**：

- C0-X925 在 5~8MB 区间延迟 4.61~4.65ns，8~16MB 下降到 4.12ns，但 Section 5.2 的数据在 8~10MB 出现小幅抬升（5.01~5.12ns），与 Section 1 的 warm 数据不完全一致
- 需要确认是 slice 数量（8MB L3 有几个 slice）还是测量噪声

**测量点**：C0-X925 HP warm，1MB 步长，1~8MB 全覆盖（fr=38）

**预期结论**：确认 slice 数量（推测 4 或 8 个 slice），为 Phase 4 SLC Hash 逆向提供前置数据

---

### 2B-3：SLC 容量精确探测（优先级：HIGH）

**目标**：精确确定 SLC 有效容量，将 SLC hit latency 置信度从 MEDIUM 提升到 HIGH

**当前问题**：

- C0-A725 HP warm：12MB=7.49ns，16MB=16.12ns → 拐点在 12~16MB 之间
- C1-A725 HP warm：12MB=6.97ns，16MB=11.29ns → 拐点在 16MB 附近
- 两个 Cluster 看到的 SLC 容量不同，可能是 SLC slice 分布不均或 GPU 占用

**测量方案**：

```
A725 HP warm，256KB 步长，12~20MB 全扫描：
  C0-A725: 12MB, 12.5MB, 13MB, 13.5MB, 14MB, 15MB, 16MB, 18MB, 20MB
  C1-A725: 14MB, 15MB, 16MB, 17MB, 18MB, 19MB, 20MB, 22MB, 24MB
```

**关键控制**：

- 必须用 `evict_slc` 做双重 evict，确保 SLC 完全 cold
- 对比 warm（SLC hit）vs cold（SLC miss/DRAM）两条曲线的交叉点
- 同时在 GPU idle 和 GPU 轻载两种状态下测，量化 GPU SLC 占用

**预期产出**：SLC 有效容量（精确到 ±1MB），SLC hit latency 锁定（±0.5ns）

---

### 2B-4：DRAM 延迟精确测量（优先级：MEDIUM）

**目标**：用 HP cold 消除 4K TLB 噪声，得到纯 DRAM 访问延迟

**当前问题**：所有 cold 测量均使用 4K page，A725 的 TLB penalty +13c 在 DRAM 路径下依然叠加

**测量方案**：

```
HP cold（需要 evict_slc 确保 SLC miss）：
  C0-X925: 32MB, 64MB, 128MB HP cold
  C0-A725: 32MB, 64MB, 128MB HP cold
  C1-X925: 32MB, 64MB, 128MB HP cold
  C1-A725: 32MB, 64MB, 128MB HP cold
```

**技术挑战**：

- HP cold 需要在 hugepage 分配后立即 evict，`evict_slc` 当前是否支持 HP 模式需确认
- 128MB HP 分配需要系统有足够的 hugepage pool（`/proc/sys/vm/nr_hugepages`）
- 单次 cold 测量（meas_rounds=1）的噪声较大，建议 5~7 次取 median

**预期结果**：

- X925 DRAM：~85~100ns（去除 TLB 后，接近 LPDDR5x 理论值）
- A725 DRAM：~100~115ns（去除 TLB 后，与 X925 差距缩小）

---

### 2B-5：Cross-Cluster 延迟测量（优先级：MEDIUM）

**目标**：量化 C0↔C1 跨 Cluster 访问延迟（CMN-700 mesh hop 开销）

**这是当前唯一完全空白的关键指标**

**测量原理**：

- 线程 A 绑定 cpu0（C0-A725），分配并 warm 一块内存（working set ≤ C0 L3 = 8MB）
- 线程 B 绑定 cpu10（C1-A725），对同一块内存做 pointer-chasing
- 此时内存在 C0 L3 中是 hot，C1 访问时需经过 CMN mesh 从 C0 L3 snoop

**实现方案**（两种）：

**方案 A：双线程协作**

```c
// Thread A (cpu0): warm 4MB buffer, then sleep
// Thread B (cpu10): pointer-chase 同一 buffer
// 测量 Thread B 的延迟 = cross-cluster L3 hit latency
```

**方案 B：单线程迁移**

```c
// 1. taskset -c 0: warm 4MB buffer (进入 C0 L3)
// 2. taskset -c 10: 立即 pointer-chase（迁移后 C0 L3 仍 hot）
// 3. 对比 taskset -c 0 的 baseline
```

方案 B 更简单，但有 migration overhead 和 OS 调度噪声，方案 A 更精确。

**预期结果**：

- Cross-cluster L3 hit：~20~40ns（CMN-700 mesh，2 hop）
- 对比 intra-cluster L3：3.7~4.7ns
- 差值 = CMN mesh 传输开销，直接量化互联代价

**工具改动**：`chase_pmu` 需增加 `--remote-warm-cpu` 参数，支持在指定 CPU 上 warm 后切换到另一 CPU 测量

---

## 三、执行优先级与依赖关系

```
2B-1 (L1 + A725 L2 HP)     ← 独立，1~2小时，补齐基础数据
     │
     └──→ 完成后 L1/L2 全层级基线锁定

2B-3 (SLC 容量精确探测)     ← 独立，2~3小时，需 evict_slc 配合
     │
     └──→ 完成后 SLC hit latency 升级为 BASELINE

2B-4 (DRAM HP cold)         ← 依赖 2B-3（需确认 evict_slc HP 支持）
     │
     └──→ 完成后 DRAM latency 升级为 BASELINE

2B-2 (X925 slice 精细扫描)  ← 独立，1小时，可选
     │
     └──→ 为 Phase 4 SLC Hash 逆向提供前置数据

2B-5 (Cross-cluster)        ← 需要工具改动（最复杂）
     │
     └──→ 完成后 Phase 2B 全部指标覆盖
```

**推荐执行顺序**：`2B-1 → 2B-3 → 2B-4 → 2B-2 → 2B-5`

---

## 四、Phase 2B 完成标准

| 子阶段   | 完成标准                                 | 预计工时           |
| -------- | ---------------------------------------- | ------------------ |
| 2B-1     | L1 hit latency ±0.2ns，A725 L2 HP ±0.3ns | 1~2h               |
| 2B-2     | X925 L3 slice 数量确认，延迟曲线斜率量化 | 1h                 |
| 2B-3     | SLC 容量 ±1MB，SLC hit latency ±0.5ns    | 2~3h               |
| 2B-4     | DRAM latency HP cold，4 核各 ±5ns        | 1~2h               |
| 2B-5     | Cross-cluster latency，±5ns              | 2~4h（含工具开发） |
| **总计** | **Phase 2B 全部 14 项指标 BASELINE**     | **~8~12h**         |
