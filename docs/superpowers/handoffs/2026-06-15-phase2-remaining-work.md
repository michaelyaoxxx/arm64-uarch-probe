# Phase 2 Remaining Work Handoff

> 面向接手 Task 11 及 Phase 2 剩余任务的 agent。请使用
> `superpowers:executing-plans` 或 `superpowers:subagent-driven-development`，
> 严格按现有计划逐项执行、测试并提交。

## 任务与起点

目标是在不使用 GB10、不执行测量 probe 的前提下，完成可恢复的环境事务、
受管 journal 恢复命令，以及 Phase 2 验收闭环。

- 仓库：`michaelyaoxxx/arm64-uarch-probe`，v1.0 唯一权威仓库
- 工作目录：`/Users/michaelyao/gb10-cpu-arch-probe`
- 工作分支：`codex/phase2-backends-environment-design`
- 代码起点：`5054df4 Add host-wide environment mutation lock`
- 起点状态：代码树在生成本交接文档前干净；本交接文档是预期的未提交变更
- 最近验证：2026-06-15 在 Mac ARM64 上运行 `make check`，192 个 Python
  测试和全部 shell syntax checks 通过

开始前执行：

```sh
git status --short
git branch --show-current
git log --oneline -12
make check
```

保留本交接文档，不要改写或 squash 已有提交。未经用户明确要求，不要 merge
`main`、push 或创建 PR。

## 给接手 Agent 的启动指令

```text
阅读 AGENTS.md 和 docs/superpowers/handoffs/2026-06-15-phase2-remaining-work.md，
再阅读其中列出的设计规格与实现计划。从当前分支和 HEAD 开始，按 TDD 完成
Task 11、Task 12、Task 13；每个任务完成验证后单独提交。不要使用 GB10，
不要 merge、push 或创建 PR。遇到规格冲突、不可恢复的安全边界问题或需要改变
公开接口时停止实现并向用户报告；其他可从仓库发现的问题自行分析并继续推进。
```

## 权威资料

按以下顺序阅读：

1. `AGENTS.md`
2. `docs/superpowers/specs/2026-06-14-phase2-backends-environment-design.md`
3. `docs/superpowers/plans/2026-06-14-phase2-backends-environment.md`

实现计划是任务步骤、文件范围、测试命令和提交消息的唯一权威来源。本交接文档
只负责标明当前进度与执行重点；发生差异时以设计规格和实现计划为准。

## 已完成范围

Task 1 至 Task 10 已完成并分别提交，包括静态 resolver、环境契约与 plan
预览、可注入 host I/O、Linux/Darwin 只读后端、`probe doctor`、CPU
频率/hugepage/THP controller、持久 journal 和 host-wide mutation lock。

重点复用现有边界：

- `arm64_probe/backends/base.py`：`HostBackend` 与 controller 协议
- `arm64_probe/environment/models.py`：不可变事务模型
- `arm64_probe/environment/constants.py`：固定状态根、仓库身份、controller 顺序
- `arm64_probe/environment/journal.py`：严格解析、原子持久化、未完成事务发现
- `arm64_probe/environment/locking.py`：跨 checkout 的 host-wide lock
- `tests/support/host_fixture.py`：Linux fixture 基础设施

## 剩余任务顺序

### Task 11：事务协调、失败恢复与信号

严格执行计划中的 **Task 11**。创建：

- `arm64_probe/environment/signals.py`
- `arm64_probe/environment/coordinator.py`
- `tests/support/fake_controllers.py`
- `tests/unit/test_environment_coordinator.py`
- `tests/integration/test_environment_signal_restore.py`

先用 TDD 固化完整成功事件序列，再对 inspect、journal persistence、apply、
verify、work、restore 和 restore verification 做穷举故障注入。必须保证：

- apply 按 `CONTROLLER_ORDER`，restore 逆序；
- `active_controller` 即使 apply 中断也优先恢复；
- 缺少授权、权限或 host capability 时，在 journal/host write 前失败；
- `SIGINT`/`SIGTERM` 仅在主线程事务范围内转换，并始终恢复原 handler；
- coordinator 不包含 Linux 路径、平台名或 experiment import。

完成后运行计划指定的 focused tests、`make check`、`git diff --check`，提交：

```sh
git commit -m "Add recoverable environment transaction coordinator"
```

### Task 12：受管恢复与 `probe restore`

Task 11 提交且验证通过后，严格执行计划中的 **Task 12**。恢复入口只能重放
受管 journal，不能成为任意环境设置接口。重点验证跨 checkout 同仓库恢复、
lock 后重新读取、symlink/path swap 防护、journal 等锁期间变化、backend/
repository/controller 不匹配，以及已经恢复 journal 的幂等成功。

公开 CLI 仅允许：

```sh
probe restore --journal <path> --allow-mutation
probe restore --journal <path> --allow-mutation -o json
probe help restore
```

不得增加 target settings、`--state-root`、自动 `sudo` 或交互提示。完成后执行
计划指定的 focused tests、`make check`、`git diff --check`，提交：

```sh
git commit -m "Add explicit environment recovery command"
```

### Task 13：Phase 2 验收与闭环

最后严格执行计划中的 **Task 13**。增加 Phase 2 acceptance/fixture workflow，
添加薄 `phase2-check` 与 `doctor` Makefile wrapper，并同步 CLI、repository、
package README 和 `AGENTS.md`。文档只能描述已实现能力，不能声称 `probe run`
已经实现。

完整验证必须包括：

```sh
make phase2-check
make check
make build
./probe --help
./probe doctor -o json
./probe plan --platform gb10 --profile baseline -o json
git diff --check
git status --short
```

随后审查 `main...HEAD` 的完整 diff，并提交：

```sh
git commit -m "Complete Phase 2 backend and environment contracts"
```

## 不可突破的边界

- Phase 2 只在 Mac 和临时 Linux fixture 上开发验收；不得访问或修改真实 Mac
  或 GB10 环境，不得执行 C probes/cases。
- 不得修改 CPU online state、NUMA hugepage pools、PMU permissions、system
  load、冻结 legacy runners、历史 `data/` 或 transitional paths。
- 公开 mutation 必须同时具备 `--allow-mutation` 和调用者权限；CLI 不调用
  `sudo`。
- 生产状态根固定为 `/var/lib/arm64-uarch-probe`；仅内部测试可注入临时根。
- 不得增加公开 environment-apply 命令或公开 state-root override。
- planner、controller、coordinator 必须保持 capability-driven，不能按 GB10、
  M4 或其他平台名分支。
- 每项任务遵循：先失败测试，再最小实现，再 focused/full verification，再单独
  提交。不要把三个任务攒成一个提交。

## 错误码与风险优先级

保持已固化的运行时错误码：host inspection `10`、authorization/permission
`11`、apply/work failure with successful restore `12`、restore failure `13`、
active lock/unfinished journal `14`。恢复失败严重度最高，同时必须保留原始失败。

事务和 recovery 是本阶段最高风险区域。任何绕过 managed path、authoritative
re-read、lock、原子 journal 或 reverse restore 的简化都不可接受。

## 完成定义与 GB10 时点

Phase 2 只有在 Task 11、12、13 分别提交，完成计划中的 Completion Gate，且
工作树干净后才可请求 review/merge。Phase 2 不需要 GB10，也不能产生 GB10
测量证据或声称 M4 测量基线。

Phase 2 merge 后进入 Phase 3 时，应提前提醒用户准备 GB10。只有 unified
runner、transaction/recovery flow 和 minimal smoke workflow 均准备完成后，
才可以明确通知：

```text
GB10 Gate 1 is ready to run
```
