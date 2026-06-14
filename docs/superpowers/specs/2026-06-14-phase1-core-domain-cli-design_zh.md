# Phase 1 核心领域模型与 CLI 设计

> 本文与
> [`2026-06-14-phase1-core-domain-cli-design.md`](2026-06-14-phase1-core-domain-cli-design.md)
> 同步；英文规格是设计约束的权威来源，中文稿用于审阅与协作。

## 目的

Phase 1 建立 v1.0 的平台无关词汇体系，以及只读控制面。它必须使 experiments 可发现、可组合，并且能够在不探测硬件、不修改主机、不运行测量的前提下，进行确定性的 planning。

本规范细化了 v1.0 设计中的 Phase 1 细节。特别是，canonical scenario IDs 使用 dot-qualified names，并且下面的 Phase 1 package 边界将取代早先仅作为示意的 `core/` layout。

## 范围与边界

Phase 1 包含：

- immutable domain models 和 stable identifiers；
- JSON configuration 和 public validation contracts；
- GB10 和 Apple M4 platform fixtures；
- target 和 profile registries；
- `probe --help`、`list`、`show` 以及只读 `plan`；
- stable planning errors、exit codes 和 contract tests。

Phase 1 不执行 probes、不修改环境、不聚合真实结果、不生成图表，也不修改 frozen 和 transitional paths。Apple M4 仅用于验证工程契约；v1.0 不声明支持 M4 测量。

## 架构与所有权

```text
arm64_probe/
  cli/                 argument parsing and rendering
  domain/              immutable models, IDs, and common validation
  planning/            selection, parameter resolution, gates, case generation
  registry/            target, profile, and platform definition loading
  platforms/           adapter protocol plus GB10 and M4 adapters
  serialization/       JSON encoding, decoding, and schema validation
configs/
  experiments/         experiment and scenario definitions
  profiles/            reproducible parameter baselines
  platforms/           topology, capabilities, and semantic CPU groups
schemas/               public JSON schemas
```

`domain` 不依赖任何 CLI、OS、platform 或 C probe 实现。
`planning` 是 pure 且 side-effect free 的。Platform adapters 解析 semantic selectors 并报告 capabilities；它们不包含 experiment orchestration。
Targets 声明含义、参数和 capability requirements，但不包含 CPU IDs 或 commands。所有 CLI 操作调用相同的 registry 和 planner APIs。

添加一个 platform 通常只应需要一个 platform definition；仅在必要时增加一个小型 adapter，以及 conformance fixtures。它不得要求修改 generic planning、已有 targets 或 result contracts。

## Domain Model 和 Stable IDs

Immutable models 包括：

- `Capability`：命名的平台特性，例如 `linux.hugepage`。
- `Platform`：topology、semantic CPU groups、capabilities 和 defaults。
- `Experiment`：benchmark 家族。
- `Scenario`：可独立选择的测试项。
- `Profile`：已提交的、命名的参数与选择基线。
- `Case`：未来执行中最小的完全展开单元。
- `Plan`：有序 cases、environment preview 和 gate decisions。
- `Sample` 与 `RunResult`：现在定义、后续产生的结果契约。

Public IDs 使用小写 kebab-case。Canonical scenarios 如下：

```text
cache-latency.l1-latency
cache-latency.l2-latency
cache-latency.l3-latency
cache-latency.slc-latency
cache-latency.dram-latency
migration-latency.same-core
migration-latency.same-cluster
migration-latency.cross-cluster
```

Case ID 将 scenario 与规范化后的 semantic dimensions 组合，例如：

```text
cache-latency.l2-latency@gb10.x925.c0.warm.default-page
```

IDs 绝不依赖输入顺序、显示标签、实现文件名或尚未解析的 defaults。解析后的 platform CPU IDs 属于 `Case` record，而不属于 target definitions。每个 sample 同时引用 run ID 和 case ID。

初始 registry 包含上面列出的两个 experiments 和八个 scenarios，外加 `smoke` 与 `baseline` profiles。精确可复现性来自记录的 Git commit 和 resolved plan；即使 profile ID 保持稳定，对已提交 profile 内容的更改仍然是可审阅的。

## 统一只读 CLI

Phase 1 暴露：

```text
probe --help
probe help plan
probe list [targets|profiles|platforms|capabilities]
probe show <id>
probe plan [options]
```

`targets` 包含 experiments 和 scenarios。`show` 接受任何全局无歧义的 registry ID，并在存在歧义时报告 qualified alternatives。

`probe plan` 与未来的 `probe run` 共享同一个 selection interface：

```bash
probe plan --select cache-latency
probe plan --select cache-latency.l2-latency \
  --select migration-latency.cross-cluster
```

重复的 `--select` 选项形成一个去重后的 union。选择一个 experiment 会展开其所有 scenarios。语义选择器，例如 `--cluster c0` 和 `--core-group x925`，是常规接口。高级 `--cpu`、`--src-cpu` 和 `--dst-cpu` 选项支持诊断和精确复现；它们覆盖 semantic selection，并且 plan 会记录该 override。

常用长选项如下：

```text
--platform --profile --select --cluster --core-group --cpu
--samples --working-set --page-policy --skip-unavailable --output
```

`--output` 接受 `table` 或 `json`；`--page-policy` 初始接受 `default` 或 `hugepage`。每个命令只记录适用于该命令的选项。

Phase 1 只提供传统且无歧义的短选项：`-h/--help` 和 `-o/--output`，同时为 Phase 3 预留 `-v/--verbose` 与 `-q/--quiet`。`--platform`、`--profile`、`--select` 和 `--samples` 等参数有意不提供短别名。文档和脚本使用长选项。

## 确定性 Planning

Planning 遵循如下序列：

```text
CLI input
  -> load and validate registries
  -> select platform
  -> expand selections
  -> merge parameters
  -> resolve semantic CPUs
  -> validate applicability and capabilities
  -> generate and sort cases
  -> render plan
```

参数优先级如下：

```text
platform defaults < profile < explicit CLI overrides
```

每个 resolved value 都记录其 value 和 source。Unknown fields、invalid enumerations、selector conflicts，以及与所选 targets 无关的 parameters 都会失败，而不是被忽略。Cases 按 normalized scenario、platform、CPU 和 parameter dimensions 排序。相同输入和已提交配置必须产生 byte-equivalent JSON plans。Plans 排除 timestamps、random run IDs 以及其他 volatile execution metadata。

`plan` 预览所需的环境变更，但绝不应用这些变更。Phase 3 将实现已批准的 transaction lifecycle：inspect、save、apply、execute、restore 和 verify restoration。Profiles 可以声明 CPU-frequency、governor、hugepage 和 page-policy requirements。冲突的环境 requirements 会创建显式 transaction phases，而不是静默覆盖。

## Capability Gates 和 Errors

每个 planned case 都具有 `ready`、`unsupported` 或 `blocked` 状态，并带有稳定 reason。当 `plan` 能够确定性地报告不可用 cases 时，`plan` 成功；`--skip-unavailable` 标记未来 execution 将跳过哪些不可用 cases。默认情况下，未来的 `run` 命令在任何已选择 case 不可用时会拒绝测量。该选项绝不会隐藏 invalid input 或 configuration。

Stable public exit codes 如下：

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `2` | CLI usage error |
| `3` | Configuration or schema error |
| `4` | Platform identification or capability error |
| `5` | Planning error |
| `10+` | Reserved for Phase 3 runtime failures |

CLI 实现拥有唯一的 exit-code definition。Implementation plan 会将 public table 放在 `docs/design/cli-contract.md`；contract tests 会将其与代码定义冻结一致。Automation 可以消费这些 codes，但不得重新定义它们。Human-readable errors 输出到 `stderr`。JSON output 使用稳定的 error schema，并包含 category、context、affected target 和 actionable hint。

## Result Contracts

Phase 1 定义但不填充未来 run layout：

```text
results/<run-id>/
  manifest.json
  plan.json
  samples.jsonl
  summary.json
  environment.json
  logs/
```

JSON 和 JSONL 是权威格式。Figures、tables 和 Markdown 是派生 artifacts。Original samples 是 immutable 的；filtering 或 anomaly decisions 只影响记录下来的 derived statistics。Run IDs 和 manifests 捕获 time、Git commit、platform、toolchain、fully resolved parameters 和 environment decisions。

Public schemas 覆盖 registry definitions、platform fixtures、cases、plans、manifests、environment records、samples、run results 和 errors。除非 schema 显式定义 extension field，否则 unknown fields 会被拒绝。

## 验证策略

Mac 运行 Phase 1 unit、schema、CLI 和 contract tests。GB10 与 M4 fixtures 必须满足相同 platform contract，同时报告不同 capabilities。Tests 覆盖：

- 每个 model 的 valid、invalid 和 serialization-round-trip 行为；
- canonical IDs、deterministic case IDs、sorting 和 deduplication；
- selection expansion、parameter precedence、overrides 和 applicability；
- `list`、`show`、`plan`、table output、JSON output、help 和 exit codes；
- capability failures 和 `--skip-unavailable`；
- 每个 Phase 1 CLI 操作的 no-side-effect guarantees。

Phase 1 或 Phase 2 不需要 GB10 访问。第一次真实 GB10 使用是在 Phase 3 Gate 1：此时 unified runner、environment transaction and recovery flow，以及 minimal smoke workflow 已就绪。Gate 1 验证 clean checkout、one-time toolchain acceptance、environment restoration、minimal L1 latency、minimal cross-cluster migration 和 structured result artifacts。

在 Phase 3 开始时，项目必须提前发出通知，以准备 GB10 access。一旦 Gate 1 workflow 和 checklist 就绪，在请求硬件使用前，必须明确发出 “GB10 Gate 1 is ready to run” 通知。

## 兼容性与验收

现有 C probes、legacy runners、historical `data/` 以及 transitional cache-information tools 保持不变。它们是行为参考和未来兼容性输入，而不是新控制层的扩展点。Phase 3 将在 execution adapters 后封装 probe 行为，并且只有在等价行为通过 GB10 verification 后，才可以退役 legacy runner。

当所有 models 和 schemas 均已实现、两个 fixtures 通过 shared contracts、只读 CLI 满足其文档化行为、plans 是 deterministic 且 side-effect free、所有 Mac checks 通过，并且没有 frozen 或 transitional path changes 时，Phase 1 即被接受。
