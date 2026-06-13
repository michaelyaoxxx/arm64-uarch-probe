# arm64-uarch-probe v1.0 基线设计

## 1. 目的

`arm64-uarch-probe` v1.0 将把现有的 GB10 微架构实验，工程化为一个可复现、可扩展、可持续演进的研究基线。

当贡献者能够完成以下事项时，v1.0 发布即视为完成：

1. 在 GB10 系统上克隆权威 GitHub 仓库。
2. 检查计划中的环境变更和实验用例。
3. 构建并运行单个、组合或完整的实验 profile。
4. 在成功或失败后恢复被修改的系统设置。
5. 通过 GitHub 传递结构化结果。
6. 分析结果，并重新生成已发布的图表和报告。

GB10 是 v1.0 唯一官方支持的测量平台。该架构必须允许后续 ARM64 平台，包括 Apple M4 系统，在无需重写 runner、结果协议或报告的前提下，复用平台无关组件。

## 2. 范围

### 2.1 v1.0 包含内容

- Cache 拓扑采集与建模。
- Pointer-chase L1、L2、L3、SLC 和 DRAM 延迟实验。
- Warm path 与 cold path、4K page 与 hugepage 策略，以及 SLC eviction。
- 同核、同 cluster、跨 cluster 迁移延迟。
- 对单个或组合测试场景进行统一规划与执行。
- 事务化的环境准备与恢复。
- 结构化结果、历史结果导入、分析、图表与文档。
- 与 Chips and Cheese 的对比分析，区分一致项、差异项以及尚未覆盖的实验。
- 面向 X925 和 A725 微架构 deep dive 的设计 roadmap，包括 ROB 容量、
  decode 与 dispatch width、执行端口与功能单元结构、load/store 行为、
  分支预测以及 cache/TLB 行为。

### 2.2 v1.0 不包含内容

- 新的 benchmark 家族，例如带宽、负载下延迟、CPU/GPU contention，以及完整的 core-to-core 矩阵。
- 对 macOS 或 Apple M4 的官方性能分析支持。
- 复现 Chips and Cheese 文章中的每一个实验。

被排除的实验属于 v1.x roadmap，不得阻塞 v1.0 发布。

## 3. 仓库与协作契约

`michaelyaoxxx/arm64-uarch-probe` 是唯一权威仓库。现有 Git 历史必须保留。Mac 与 GB10 系统仅通过 GitHub branches、pull requests、commits 和 tags 进行协作。

- Mac 是主要的开发、离线测试、分析、图表生成和文档环境。
- GB10 是权威硬件测量环境。
- 每次硬件运行都记录精确的 Git commit 或 tag。
- 任一机器都不得在 `main` 上直接维护独立变更。
- Release-candidate 运行使用不可变 tag，例如 `v1.0.0-rc1`。
- 仅在最终基线和文档合并后创建 `v1.0.0`。

日常运行输出被 Git 忽略。仓库只提交审阅已发布结论所需的证据：

- `results/baselines/v1.0/`：结构化基线数据、manifests、选定的原始日志以及异常证据。
- `docs/assets/v1.0/`：生成的发布图表。
- `docs/results/v1.0.md`：结论、限制以及可追溯性。

现有版本化 runners 和 `data/` 作为历史证据保留。

## 4. 可扩展架构

核心架构如下：

```text
experiment definition
  -> capability interface
  -> OS backend
  -> hardware platform description
  -> probe
  -> structured result
```

### 4.1 平台无关核心

核心层负责稳定的领域模型和编排：

- `Platform`：被选中的硬件描述与 backend。
- `Capability`：可测量或可控制的平台特性。
- `Experiment`：benchmark 家族。
- `Scenario`：可独立选择的测试项。
- `Case`：一个完全展开的测量点，具有稳定 ID。
- `Profile`：由 scenarios 和 selectors 组成的命名组合。
- `Sample` 与 `RunResult`：平台中立的结果记录。

Experiments 声明 required 和 optional capabilities，而不是检查平台名称。Experiment 代码中不允许出现类似 `if platform == "gb10"` 的平台特定分支。

Capability 声明示例：

```python
required = {"monotonic_timer", "cpu_binding"}
optional = {"explicit_hugepage", "cache_flush", "pmu"}
```

当 capability 不可用时，planner 必须拒绝、显式跳过或记录降级行为。它绝不能静默模拟支持。

### 4.2 OS Backends

OS backends 实现多个硬件平台共享的机制。

- `linux_arm64`：affinity、`/sys`、`/proc`、Linux hugepages、PMU access，以及 Linux 环境控制。
- `darwin_arm64`：未来用于 macOS 支持的 affinity、topology 和 memory-policy capabilities 的 backend。

添加另一个 Linux ARM64 系统时，通常应只需要新增 platform description，而不是新增 backend。添加 Apple M4 时，需要一个可复用的 Darwin backend 以及一个 Apple M4 platform description。

### 4.3 硬件平台描述

硬件 platform description 包含事实和策略，而不是 runner 逻辑：

- Core groups、clusters、cache domains，以及默认代表性 CPU。
- 支持的 capabilities 与已知限制。
- 推荐的环境策略。
- 默认 scenario matrices 和平台特定 validation constraints。

GB10 是完整的 v1.0 platform description。Apple M4 可以以 fixtures 的形式用于 contract testing，但不是 v1.0 支持的测量目标。

### 4.4 Probes

C probes 执行一个明确的测量动作。它们校验参数，并同时输出可读诊断信息与稳定的机器可读记录。它们不展开实验矩阵、不计算多次运行统计，也不管理系统环境设置。

现有 `chase_pmu`、`evict_slc` 和 `chase_migrate` 的行为将被保留，并在该契约下进行规范化。

## 5. 目标仓库组织

实现计划将细化精确的 package 名称，但所有权边界应遵循如下结构：

```text
src/                         C 单次测量 probes
arm64_probe/
  core/                      domain models, planner, results, schemas
  backends/
    linux_arm64/
    darwin_arm64/            未来实现
  platforms/
    gb10/
    apple_m4/                未来 description 与 fixtures
  experiments/               capability-driven experiment definitions
  reports/                   平台无关的分析输入
configs/
  platforms/
  experiments/
  profiles/
legacy/runner/               冻结的历史 runner scripts
tests/
  unit/
  contract/
  fixtures/
  integration/
results/
  runs/                      被忽略的临时 runs
  baselines/v1.0/            已提交的 release evidence
analysis/                    分析与图表生成
docs/
  design/
  methodology/
  references/
  results/
  roadmap/
  assets/
```

在实际可行的情况下，文件移动应使用 `git mv`，以保留历史。现有 `data/` 目录保持不变，作为历史证据。

## 6. 实验组合模型

Experiments 由三个层级组成：

```text
Experiment -> Scenario -> Case
```

示例：

```text
cache-latency
  l1-latency
  l2-latency
  l3-latency
  slc-latency
  dram-latency

migration-latency
  same-core
  same-cluster
  cross-cluster
```

每个 scenario 独立声明：

- Capability requirements。
- Environment policy。
- Core 和 cluster selection rules。
- Working-set parameter space。
- Warm、cold、page 和 eviction policies。
- Required setup steps。
- Result fields 和 acceptance rules。

用户可以选择一个 scenario，组合多个 scenarios，选择一个 experiment，或者运行一个命名 profile。被选中的 scenarios 会合并为一个 execution plan，并移除重复 cases。

Environment-policy 冲突会将 plan 拆分为显式 transaction phases。它们不得被静默覆盖。

每个 case 都有稳定的语义 ID，例如：

```text
gb10/cache-latency/l2/C0-X925/2048KB/hugepage/warm
```

Stable IDs 支持 resume、失败 case 重跑、结果对比和基线可追溯性。

## 7. 统一控制面

稳定接口将是一个基于 Python standard library 的控制层。Scenarios 必须是一等可选择目标，使用户无需调用实验专用脚本，即可发现、检查、规划、运行、组合、恢复和比较 scenarios。

### 7.1 稳定目标模型

控制面接受四类目标：

- `experiment`：一个实验包含的全部 scenarios，例如 `cache-latency`。
- `scenario`：一个可独立运行的测试项，例如 `l1-latency`、`dram-latency`
  或 `cross-cluster`。
- `profile`：已提交的 experiments、scenarios 和 selectors 命名组合，例如
  `v1.0-smoke` 或 `v1.0-baseline`。
- `case`：一个稳定的展开后 case ID，主要用于诊断、比较或精确重跑。

Scenario 的规范名称使用限定形式 `experiment/scenario`，例如
`cache-latency/l2-latency` 和 `migration-latency/cross-cluster`。未限定的
短名称仅在能够无歧义解析时作为便利别名。已提交 profiles、结果记录和文档使用规范限定名称。

v1.0 scenario catalog 包含：

```text
cache-latency/l1-latency
cache-latency/l2-latency
cache-latency/l3-latency
cache-latency/slc-latency
cache-latency/dram-latency

migration-latency/same-core
migration-latency/same-cluster
migration-latency/cross-cluster
```

### 7.2 快速 Usage 与 Help

控制面必须在无需平台探测、特权访问、有效实验配置或环境变更的情况下，快速提供常规 usage 信息：

```text
probe --help
probe help
probe run --help
probe plan --help
probe analyze --help
```

顶层 help 总结工作流、操作、目标类型和常见示例。子命令 help 说明该操作接受的目标、selectors、输入、输出、退出行为和相关示例。

无参数调用 `probe` 时，输出简洁 usage 摘要，并指向 `probe --help`、
`probe list scenarios` 和 smoke-profile 工作流。无效命令或选项输出简短、
可执行的错误信息和相关 help 命令，默认不得转储长篇 help。

Help 输出必须：

- Checkout 后可立即在 Mac 和 GB10 上使用。
- 无需读取 GB10 专用 `/sys` 或 `/proc` 状态即可完成。
- 永不请求特权、创建 run 目录或修改环境。
- 使用由自动化文档测试持续校验的示例。

`--help` 回答如何使用接口；`list` 和 `show` 回答有哪些 experiments、
scenarios、profiles 和 selectors。

### 7.3 发现与规划

用户必须能够在运行测试前发现可用接口：

```text
probe list experiments
probe list scenarios
probe show cache-latency/l2-latency
probe show --profile v1.0-baseline
```

`show` 描述 capability requirements、environment policy、默认 selectors、
参数空间、预计时长和结果字段。

`plan` 接受与 `run` 相同的目标和 selectors。它在不修改机器的情况下，
展开精确 cases、环境事务阶段、跳过的 cases、特权需求和预计工作量：

```text
probe plan cache-latency/l1-latency
probe plan cache-latency/l2-latency cache-latency/dram-latency
probe plan migration-latency/cross-cluster
probe plan --profile v1.0-baseline
```

### 7.4 独立与组合执行

同一调用模型支持单个 scenario、任意 scenario 组合、完整 experiment 或已提交 profile：

```text
probe run cache-latency/l1-latency
probe run cache-latency/l2-latency cache-latency/dram-latency
probe run migration-latency/cross-cluster
probe run cache-latency
probe run --profile v1.0-baseline
```

Selectors 缩小所选目标范围，但不修改其定义。必需的通用 selector 维度包括
platform、cluster、core group、working-set range、page policy、sample count
和 case ID。Scenarios 可增加符合其测量语义的类型化 selectors。

接口必须支持等价于以下行为的调用：

```text
probe plan cache-latency/l2-latency --core-group X925
probe run cache-latency/l2-latency --cluster C1 --page-policy hugepage
probe run cache-latency/dram-latency --working-set 32MB,64MB,128MB
probe run migration-latency/cross-cluster --samples 3
probe run --case gb10/cache-latency/l2/C0-X925/2048KB/hugepage/warm
```

这些示例建立所需选择行为；精确选项拼写将在实现级接口设计中最终确定。

多个目标展开为一个 execution plan。重复 case ID 被移除。冲突的环境策略生成
独立且可见的 transaction phases。不支持的 cases 在 planning 阶段报告，不得静默省略。

### 7.5 操作

概念操作如下：

```text
probe list         discover experiments, scenarios, profiles, and prior runs
probe show         inspect one target or profile
probe help         show quick usage and operation-specific help
probe doctor       inspect dependencies, capabilities, and recovery journals
probe plan         expand selected targets and show environment changes
probe run          execute selected targets inside environment transactions
probe resume       continue incomplete cases from a prior run
probe analyze      calculate statistics and compare selected runs or baselines
probe report       generate figures and Markdown reports
probe restore      recover an interrupted environment transaction
```

规则：

- Help 操作快速、只读，并且独立于平台探测。
- `plan` 是只读的，并且可在执行前审阅。
- `plan` 和 `run` 接受相同的目标与 selector 模型。
- 正式 runs 引用已提交的 profile；CLI overrides 会被记录。
- Profiles 组合目标和 selectors，不调用专用脚本。
- `resume` 和精确重跑使用已有 run 中的稳定 case ID。
- 不支持的 capabilities 在 planning 阶段被识别。
- `run` 写入结构化结果，但不生成图表。
- 分析和报告可在 Mac 上离线运行。
- Makefile targets 封装常见开发任务，但不包含实验编排逻辑。

上述目标类型、scenario catalog、组合行为和操作语义是 v1.0 接口要求。
精确可执行文件名、选项拼写、配置文件编码和 selector 语法将在实现级分析后最终确定，并在编码前评审。

GB10 runtime 仅依赖已编译 probes、Bash/system utilities，以及 Python standard library。开发、测试、分析和绘图使用仓库管理的 Python 环境，并使用受控的第三方依赖。

## 8. 事务化环境管理

环境 setup 是一等事务：

```text
detect capabilities
  -> inspect current state
  -> save original state
  -> apply requested policy
  -> verify effective state
  -> run cases
  -> restore original state
  -> verify restoration
```

Policies 可包括：

- CPU governor、minimum and maximum frequencies，以及 online CPUs。
- Hugepage pool、transparent-hugepage policy，以及 page policy。
- CPU 和 NUMA affinity。
- PMU permissions 以及所需 kernel interfaces。
- System-load 和 GPU-activity preconditions。

结果必须区分 requested settings 与 observed effective state。例如，设置 frequency limits 并不能证明运行期间维持了固定频率。

Environment transactions 必须：

- 在修改前获取 process lock。
- 在变更设置前保存 durable recovery journal。
- 记录 `before`、`requested`、`effective` 和 `after` states。
- 在正常完成、命令失败和常见 signals 下恢复设置。
- 校验恢复结果，并将不完整恢复视为严重错误。
- 在下一次 invocation 时检测未完成 journals，并提供显式 recovery。
- 当 required settings 无法被 inspect、apply 或可靠 restore 时，拒绝执行正式 baseline。

默认模式只检查并描述所需变更。特权变更需要显式授权。一旦开始 mutation，恢复必须自动执行。

## 9. 结果协议与报告

每次 run 创建：

```text
results/runs/<run-id>/
  manifest.json
  environment.json
  cases.jsonl
  raw/
  errors.jsonl
```

`manifest.json` 记录 Git commit、platform、backend、profile、selectors、expanded-plan summary、tool versions 和 timestamps。

每个 case record 包含：

- Stable case ID、experiment 和 scenario。
- Platform、backend、CPU、core group、cluster 和 topology facts。
- Working set、page policy、warm/cold policy 和 eviction method。
- Requested parameters 和 observed capabilities。
- Individual samples、median、dispersion 和 anomaly flags。
- Probe version、exit status 和 raw log references。

Analysis 只读取结构化协议。历史文本日志通过经过测试的 compatibility adapters 导入；新报告不得直接解析 human log format。

已发布结论必须区分：

- Platform facts。
- Direct measurements。
- Derived results。
- Hypotheses 或 architectural inference。
- External references。

## 10. 文档交付物

- `README.md`：定位、quick start、结果概览和导航。
- `docs/design/`：架构、environment transactions、schemas 和 extension guide。
- `docs/methodology/`：pointer chasing、eviction、migration、statistics，以及 code-to-method reasoning。
- `docs/results/`：GB10 v1.0 baselines、figures、confidence、anomalies 和 limitations。
- `docs/references/`：对 Chips and Cheese 的 [GB10 memory-subsystem article](https://chipsandcheese.com/p/inside-nvidia-gb10s-memory-subsystem) 的分析，包括 agreements、differences、methodological differences 和 missing experiments。
- `docs/roadmap/`：X925/A725 微架构 deep dive，覆盖 ROB 容量、decode 与
  dispatch width、执行资源、load/store 行为、分支预测、cache/TLB 行为，
  以及 bandwidth、load contention、CPU/GPU interference 和 complete
  core-to-core studies。

Figure-generation code、structured baseline inputs 和 generated publication figures 都会被提交，以便 GitHub 读者能够直接审阅报告。

## 11. 验证策略

### 11.1 持续 Mac 验证

Apple M4 Pro Mac 验证工程行为，而不是 GB10 性能：

- Configuration expansion 和 stable case IDs。
- Statistics、anomaly handling 和 resume behavior。
- Result schemas 和 historical-log import。
- Report generation。
- 使用 GB10 和 M4 fixtures 的 backend contract tests。
- Probe parameter validation、pointer-chain logic 和 safe portable subsets。
- Makefile、configuration 和 documentation examples。

实现必须将 generic ARM64 code 与 Linux-specific features 分离。仅凭 `__aarch64__` 不得暗示支持 Linux 的 `MAP_HUGETLB`、`MAP_POPULATE`、`dc civac` 或 Linux affinity APIs。

### 11.2 Linux ARM64 验证

Native ARM64 Linux containers 或 CI 验证：

- Linux probe builds。
- Linux backend behavior 和 failure paths。
- Runner、Makefile、`taskset`、sysfs/procfs fixtures，以及 signal recovery。

Container measurements 绝不作为硬件性能结论。

### 11.3 GB10 验证门禁

**Gate 1：一次性 clean-environment toolchain acceptance**

- 从 clean checkout 开始。
- 验证 bootstrap、build、doctor、plan、scenario composition、environment transactions、recovery、smoke execution 和 GitHub result handoff。
- 仅在 bootstrap/build/environment machinery 发生变化、OS 或 kernel 变化、使用不同 GB10，或证据不完整时重复执行。

**Gate 2：methodology and result validation**

- 复用已验收的环境。
- 运行代表性的 C0/C1、A725/X925、warm/cold、4K/hugepage、eviction 和 migration cases。
- 验证 structured results、resume、statistics、figures，以及与历史数据的 comparisons。

**Gate 3：v1.0 release candidate**

- Checkout 一个固定 RC tag。
- 运行 `doctor` 和一个 minimal regression smoke。
- 执行完整 v1.0 profile。
- 冻结 release evidence、figures、conclusions 和 known limitations。

## 12. 交付阶段

### Phase 0：Repository Contract and History Freeze

- 将协作指向已重命名的权威仓库。
- 冻结 legacy runners 和 historical data。
- 建立 dependency、build、Git-ignore 和 platform-responsibility contracts。

### Phase 1：Core Domain Model

- 定义 platform、capability、experiment、scenario、case、profile、stable IDs 和 result schemas。
- 添加 fixtures、historical imports，以及 Mac unit/contract tests。

### Phase 2：Backends and Environment Transactions

- 实现 core interfaces、Linux ARM64 backend、GB10 platform description、environment journaling、restoration 和 recovery。
- 为未来 Darwin ARM64 backend 保留契约。

### Phase 3：Probes and Unified Runner

- 规范化三个 C probes 和 machine-readable output。
- 实现独立与组合 scenarios、profiles、planning、execution 和 resume。
- 对齐 Makefile，并运行 GB10 Gate 1。

### Phase 4：Analysis, Figures, and Methodology

- 导入 historical evidence，并生成 release-candidate baseline。
- 完成 figures、methodology、reference comparison 和 roadmap。
- 运行 GB10 Gate 2。

### Phase 5：Release Closure

- 完成 README、extension guide 和 known limitations。
- 从 RC tag 运行 GB10 Gate 3。
- 冻结 v1.0 evidence，并发布 `v1.0.0`。

每个阶段在进入下一阶段前，都需要完成 design review、code review 和 independent acceptance。

## 13. v1.0 验收标准

当满足以下条件时，v1.0 即可发布：

- Mac 和 Linux automated verification 通过。
- GB10 Gate 1 evidence 完整，后续 gates 通过其 regression smoke。
- 完整 GB10 v1.0 profile 在无未解释 failures 的情况下完成。
- Environment restoration 被验证并记录。
- Individual and combined scenarios、profiles、resume 和 failed-case reruns 均可通过稳定控制面工作。
- 一个全新的 GB10 checkout 可以按照 README 指令完成 smoke run。
- 已发布 figures 和 conclusions 可追溯到 structured cases、raw evidence 和 Git commit。
- Chips and Cheese comparisons 清晰地区分 agreement、difference、methodological mismatch 和 uncovered work。
- 仓库包含经过审阅的 roadmap，用于更深入的 X925/A725 和 v1.x 实验。
