# Phase 2 Backends and Environment Transactions Design

## 目的

Phase 2 增加 live、只读的 host inspection，以及一个可恢复的环境 mutation 基础，但不执行测量。它将 Phase 1 中声明式的 capabilities 和 environment previews，转化为显式的 OS-backend contracts、可独立测试的 controllers、持久化 journals 和 recovery operations。

Phase 2 必须在没有 GB10 访问的情况下被完整验收。Mac 提供持续的 contract 和 fault-injection testing；Linux ARM64 fixtures 和 CI 验证 Linux 机制。第一次真实 GB10 使用仍然是 Phase 3 Gate 1。

## 范围与边界

Phase 2 包含：

- 可复用的 host-backend protocol 和 Linux ARM64 backend；
- 经过 contract-test 的 Darwin ARM64 只读/minimal boundary；
- 通过 `probe doctor` 进行 live host diagnostics；
- 受控的 CPU-frequency、global hugepage-pool 和 transparent-hugepage transactions；
- 持久化 journals、单 host mutation locking、restoration 和 recovery；
- `probe plan` 中增强的确定性 environment previews；
- 用于从已有 managed journal 恢复的 `probe restore`；
- Mac fake/fixture tests，以及 Linux ARM64 fixture 或 CI validation。

Phase 2 不执行 probes 或 cases，不暴露通用目的的 environment apply command，也不声明支持 Apple M4 测量。它不修改 CPU online state、NUMA-node hugepage pools、PMU permissions 或 system load。
CPU affinity 和 per-allocation page policy 属于 Phase 3 case-execution 关注点，而不是 global host mutations。

## 授权与安全契约

CLI 绝不调用 `sudo`，不提示输入密码，也不静默提升权限。只读操作不需要 mutation authorization。任何可能改变 host 的公共操作都同时要求：

1. 显式指定 `--allow-mutation` 选项；以及
2. 调用进程具备足够权限。

例如：

```bash
sudo ./probe restore --journal /var/lib/arm64-uarch-probe/journals/<id>.json \
  --allow-mutation
```

缺少授权或权限会在 mutation 前失败。`restore` 只接受 authoritative host-state journal directory 下受管理的有效 journal。Journals 存储规范化 controller identities 和 values，绝不存储任意文件系统路径、shell commands 或 executable content。Controllers 从自身经过验证的 identities 推导允许的 OS paths，因此 journal 不能变成任意 privileged write interface。

## 架构与所有权

```text
arm64_probe/
  platforms/
    resolver.py                 static platform facts and semantic CPU selection
  backends/
    base.py                     HostBackend and controller protocols
    linux_arm64/
      backend.py
      cpu_frequency.py
      hugepage.py
      transparent_hugepage.py
      inspector.py
    darwin_arm64/
      backend.py                read-only/minimal unsupported boundary
  environment/
    models.py                   observations, operations, and journal records
    coordinator.py              transaction lifecycle
    journal.py                  atomic persistence and recovery discovery
    locking.py                  single-host mutation lock
  diagnostics/
    doctor.py                   backend, capability, and journal diagnostics
```

当前 `PlatformAdapter` 重命名为 `PlatformResolver`。它继续基于经过审阅的 platform facts 解析 semantic CPU selections，并且没有 live-host responsibility。

依赖流向单向：

```text
CLI
  -> diagnostics / environment coordinator / planner
  -> backend protocols
  -> OS-specific mechanisms
```

Platform definitions 包含 topology facts、expected capabilities、recommended policies 和 scenario defaults。它们不包含 OS paths、commands、controller logic 或 runner logic。Experiments 和 planner 命名 capability 与 environment requirements，但不导入 backend。
Coordinator 不包含 Linux path、GB10 name 或 experiment behavior。

所有 host access 都通过可注入的 filesystem 和 command-execution boundaries。Production Linux 实现使用真实 host；测试使用 temporary fixtures 和 fakes。

## 声明式 Capabilities 与 Live Observations

Phase 1 platform capabilities 描述所选硬件 platform 预期支持什么。Phase 2 live observations 描述当前 host 实际暴露什么。二者不能互相替代。

`probe plan` 保持 deterministic 且 side-effect free。它使用经过审阅的配置来展示 declared requirements、expected host mutations 和 privilege needs。它绝不读取 live `/sys` 或 `/proc` state。

`probe doctor` 执行 live read-only inspection。Phase 3 `run` 会在启动 transaction 前立即重复所需 inspection，而不是信任早先的 doctor report。

每个 capability observation 都具有：

- 稳定的 capability ID；
- 一个状态：`available`、`unsupported`、`permission-denied`、`degraded` 或 `unavailable`；
- 规范化 observed values；
- 简明 raw evidence 或 evidence references；
- 当未完全 available 时给出 actionable hint；
- 一个 Boolean，指示该 observation 是否允许 formal measurement。

Linux backend 支持以下 Phase 2 controller capabilities：

- `linux.cpufreq`：CPU-frequency policy inspection and control；
- `linux.hugepage`：global hugepage-pool inspection and control；
- `linux.transparent-hugepage`：transparent-hugepage policy inspection and control。

Host inspector 报告 CPU online state、CPU/cluster/cache topology、PMU interfaces and permission state、required kernel interfaces 和 system-load preconditions，但不修改它们。

Darwin ARM64 backend 在 Python standard library 能提供的范围内报告基本真实 host facts。所有 v1.0 mutation controllers 和 measurement capabilities 都显式报告 `unsupported`；该 backend 不构成任何 M4 performance claim。

## Controller Contract

每个可独立测试的 mutation controller 实现：

```text
inspect() -> before state
validate_request(request)
apply(request) -> applied record
verify(request) -> effective state
restore(before)
verify_restored(before) -> after state
```

Controllers 必须在写入前拒绝 unknown values、missing interfaces 和 ambiguous state。它们记录 normalized state，以及足够但有界的 raw evidence，以便诊断失败。它们绝不单凭一次成功写入就推断成功；verification 要求新的 observation。

### CPU Frequency

CPU frequency 由 Linux `policy*` domains 管理，而不是把每个 CPU 当作独立控制对象。State 记录每个 policy identity、related CPUs、governor、minimum frequency 和 maximum frequency。Apply 和 restore 使用一种不会有意创建 invalid minimum/maximum interval 的顺序。Missing policy files、inconsistent related-CPU sets 或 unreadable values 都会被显式报告。

### Hugepages

Hugepage controller 只修改 configured hugepage size 对应的 global hugepage pool。NUMA-node pools 在 Phase 2 中只被 inspect 和 report，不被修改。Controller 在 apply 后和 restore 后验证 observed pool；allocation shortfalls 被视为 failures，而不是静默降级。

### Transparent Hugepages

Transparent hugepage policy 是独立 controller，因为其 interface、values 和 restoration semantics 不同于 explicit hugepage pool。它记录 selected policy 和 kernel-reported available choices。

## Plan Environment Preview

Phase 2 将 global host mutation requirements 与 case-local execution requirements 分离：

- host mutations 包括 CPU governor/frequency、hugepage-pool 和 transparent-hugepage policy；
- case-local requirements 包括 CPU affinity 和 allocation page policy。

只有冲突的 host mutations 会将 plan 拆分为 environment transaction phases。单纯的 page-policy difference 不需要改变 global host state，因此不会拆分 transaction phase。Public plan schemas 和 contract tests 会同步更新，以显式表达该区别。

每个 preview 报告 responsible capability、requested policy、是否预期需要 mutation，以及通常是否需要 elevated privileges。Preview 不声称 requested state 当前可用或已经 effective。

## Transaction Lifecycle

一个 environment transaction 拥有一个 durable journal，并按如下顺序执行：

```text
acquire mutation lock
  -> rediscover and reject unfinished journals
  -> inspect before
  -> create journal
  -> record requested operations
  -> apply controllers in deterministic order
  -> inspect and verify effective state
  -> mark prepared
  -> invoke caller-supplied work
  -> restore applied controllers in reverse order
  -> inspect and verify after state
  -> finalize journal
  -> release lock
```

Phase 2 将 lifecycle 暴露为内部稳定 API，并使用 caller-supplied work callback 对其进行测试。Phase 3 会将 case execution 作为该 callback 提供。

Lock 必须在 authoritative `before` inspection 和 journal creation 之前持有，以防两个并发进程都捕获过期 original state，或创建相互竞争的 active journals。Journal creation 和 requested operations 在第一次 host mutation 之前必须已经持久化。

Journal states 如下：

```text
created
applying
prepared
restoring
restored
restore-failed
```

Journal 在第一次 mutation 之前被原子持久化。每个 controller apply 成功后，其 applied state 都会立即持久化。Restoration 只触碰被记录为 applied 的 controllers，并按反向顺序处理。

Apply failure、verification failure、work-callback failure，以及已处理的常见 signals 都进入 restoration。早先失败后即使 restoration 成功，该 transaction 仍然是 failed transaction，并报告原始失败。Restoration verification failure 会将 journal 变为 `restore-failed`，返回严重 recovery error，并且绝不被早先错误隐藏。

Coordinator 在发现 active mutation lock 或 unfinished journal 时拒绝新的 mutation。Read-only inspection 从不需要 mutation lock。已 restored 的 journal 会作为本地 audit evidence 保留。

## Journal、Lock 与 Recovery Storage

Runtime transaction state 位于：

```text
/var/lib/arm64-uarch-probe/
  mutation.lock
  journals/<transaction-id>.json
```

该 Linux host-level directory 是权威路径，因此同一机器上的不同 clones 和 worktrees 共享一个 mutation lock，并发现相同的 unfinished journals。Repository-local lock 无法保护全局 frequency 和 hugepage state。

Read-only commands 只 inspect 该目录，不创建它。只有在显式授权的 mutation flow 中且权限足够时才创建该目录。Public CLI 不提供 state-root override，因为不同 roots 会绕过 host-wide serialization 和 recovery discovery。Tests 通过 internal APIs 注入 temporary state root。

在 Linux 上，state root 和 journals 可读用于 diagnostics，但只有 privileged owner 可写。Journals 不包含 secrets 或无界 command output。实现以 mode `0755` 创建 root 和 journal directory，以 mode `0644` 创建 journal 和 lock files，在 mutation 前拒绝 unsafe existing ownership 或 modes，并且绝不放宽 existing path 上的 permissions。

Phase 3 会将 finalized environment evidence 复制到对应的 structured run result 中。Host-state journals 保持为本地 audit 和 recovery evidence，绝不提交到 Git。

Journals 使用 versioned、schema-validated JSON。Atomic updates 在 journal directory 中写入 temporary file、flush、替换 target，并在 update 失败时保留最后一个有效 journal。Journal 记录：

- schema version、transaction ID、backend ID、platform ID 和 repository identity；
- lifecycle state 和 bounded timestamps；
- requested controller policies；
- `before`、applied、`effective` 和 `after` controller states；
- restoration status 和 structured failures。

Mutation lock 使用 Linux advisory file lock，并记录 diagnostic owner metadata。持有的 OS lock 是权威依据；仅凭 metadata 不能证明存在 live owner。如果进程崩溃，OS 会释放其 lock，但 unfinished journal 仍会阻止新的 mutation，直到显式 recovery 完成。

Repository identity 是规范化的 authoritative repository identity，而不是 checkout path 或 commit，因此同一仓库的另一个 clone 可以执行 recovery。

`probe restore` 首先拒绝 symlink escapes 和 authoritative host-state journal directory 外部的 paths，并且在此之前不执行写入。然后它获取 mutation lock，重新读取 journal，并在任何 restoration 之前执行权威的 schema、backend、repository-identity 和 supported-controller validation。它只恢复记录为 applied 的 controllers。已经 restored 的 journal 是成功的 no-op。Unfinished 或 `restore-failed` journal 仍可被 `doctor` 发现。

## CLI Contract

Phase 2 增加：

```text
probe doctor [--platform <id>] [-o table|json]
probe restore --journal <path> --allow-mutation [-o table|json]
```

它同时增强 `probe plan` 的 environment previews，但不会使 planning 依赖 host。

`doctor` 始终是只读的。它报告 selected backend and platform、observed capabilities and permissions、host-inspection results，以及 unfinished 或 failed recovery journals。它可能返回非零 inspection status，但绝不请求权限，也不修改 host。

Expected `unsupported` observations，包括 Darwin mutation boundary，不会使 `doctor` 本身失败。Exit code `10` 表示 requested diagnostic 无法可靠完成，而不仅仅是某个 capability 不可用。

`restore` 不接受 desired target state。它只能恢复 managed journal 中记录的 original state。若没有显式 mutation authorization、足够权限、有效 journal 和可用 mutation lock，它会拒绝运行。

Phase 2 有意不提供公共 `environment apply` 命令。Phase 3 的 `probe run --allow-mutation` 将是创建新 transaction 的常规入口。

## Error and Exit Semantics

Phase 1 exit codes 保持不变。Phase 2 固定以下 runtime codes：

| Code | Meaning |
| --- | --- |
| `10` | Backend or host inspection failure |
| `11` | Mutation authorization or permission failure |
| `12` | Environment apply or verification failure; restoration succeeded |
| `13` | Environment restoration or recovery failure |
| `14` | Active lock or unfinished journal prevents mutation |

Human-readable errors 输出到 `stderr`。JSON output 使用既有 stable error envelope，并携带 structured context 和 actionable hint。当发生多个 failures 时，restoration failure 具有最高 severity，而原始 failure 仍记录在 journal 中。

## 验证策略

### Continuous Mac Verification

Mac 测试所有 platform-independent behavior，并且不产生 GB10 measurement evidence：

- 通过 fake filesystem 和 command boundaries 测试 controller contracts；
- journal schema、atomic updates、recovery discovery 和 managed-path checks；
- lock acquisition、contention、release 和 stale diagnostic metadata；
- 每个 valid transaction-state transition 以及 invalid-transition rejection；
- deterministic apply order 和 reverse restoration；
- 在每个 inspect、apply、verify、work、restore 和 journal persistence step 注入 fault；
- subprocess 和 signal-driven automatic restoration；
- Darwin ARM64 真实 read-only/minimal backend contract；
- `doctor`、`restore`、增强版 `plan`、JSON schemas 和 exit codes；
- 证明 read-only commands 不创建 runtime state，也不修改 host。

### Linux ARM64 Fixture and CI Verification

Linux ARM64 verification 使用 temporary sysfs/procfs fixtures，并且在 isolated CI environment 安全允许时执行受控 integration checks。它覆盖 path and parsing variants、permission failures、frequency-policy domains、global and NUMA hugepage observations、transparent-hugepage policy、topology、PMU interfaces 和 restoration behavior。

Container 或 CI observations 仅作为 engineering evidence，绝不作为 hardware performance conclusions。

## 兼容性与验收

现有 C probes、legacy runners、historical data 和 transitional cache-information tools 保持不变。Phase 2 可以将这些工具用作 behavior references，但不移动或扩展它们。

Phase 2 被接受的条件如下：

- capability interfaces 不包含 experiment-specific 或 GB10-specific logic；
- Linux ARM64 inspection 和 approved controllers 满足其 contracts；
- GB10 configuration 只包含 facts 和 policies，不包含 backend 或 runner logic；
- Darwin ARM64 满足其明确的 read-only/minimal unsupported contract；
- transactions 持久化并暴露 before/requested/effective/after state，序列化 mutation，在 failures 和 signals 后恢复，并 recover unfinished journals；
- `doctor`、`restore` 和 plan previews 满足其 public contracts；
- 所有 Mac checks 和 Linux ARM64 fixture/CI checks 在无 GB10 访问情况下通过。

Phase 2 验收并 merge 后，Phase 3 开始 normalized probes 和 unified runner。在 Phase 3 开始时，项目必须提醒用户准备 GB10 access。项目不得宣布 **"GB10 Gate 1 is ready to run"**，直到 unified runner、transaction/recovery flow 和 minimal smoke workflow 已就绪并通过验证。