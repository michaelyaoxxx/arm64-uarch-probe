# Phase 3 Probes and Unified Runner — 详细设计

> **状态：** design（在 superpowers brainstorming flow 下于 2026-06-15 重新撰写）。权威输入：
> - `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md`（AC1–AC9、已锁定的架构决策、质量控制）
> - `docs/superpowers/specs/2026-06-12-arm64-uarch-probe-v1.0-design.md`（§7.4 individual and combined execution，§7.5 operations）
> - `docs/superpowers/specs/2026-06-14-phase2-backends-environment-design.md`（本阶段复用的现有 transaction model）
>
> **配套文档：** `docs/superpowers/plans/2026-06-15-phase3-probes-runner.md`（将 AC1–AC9 映射到 Task 14–Task 20 的可执行计划）。
>
> **实现状态：** **无**。本 spec 用于审批；代码将按照 plan 后续实现。凡是需要示例来验证设计的地方（例如 fixture-runner round-trips），本设计会说明“deferred to a code-handoff document”，而不是在 spec 中编写代码。

## 1. 目标

交付统一测量 runner。具体包括：

1. 一个 `ProbeAdapter` protocol，包含三个 concrete adapters（`ChasePmuAdapter`、`EvictSlcAdapter`、`ChaseMigrateAdapter`），用于封装现有 C probes，并在每次调用时产生一个 `Sample`。
2. 一个 `Runner`，驱动 planner 生成的 `Plan`，针对每个 environment phase 调用一次 `EnvironmentCoordinator.execute`，并将 `Sample` records 累积为一个 `RunResult`。
3. 一个 `RunResultStore`，用于在 `results/runs/` 下以原子方式持久化 schema-valid 的 `RunResult`（该目录被 git 忽略），并支持可选 promotion 到 `results/baselines/<version>/`。
4. 两个新的公共命令 —— `probe run` 和 `probe resume` —— 通过现有 `arm64_probe.cli` surface 接入，并遵循与 Phase 2 相同的 exit-code contract。
5. 两个新的 `ExitCode` 常量（`15`、`16`），并通过 §3 中的 schema 和 CLI examples 进行 contract-tested。
6. 一个 `make smoke` target 和一个 `make phase3-check` target，二者均由 uv 管理，并通过 contract-tested。
7. Characterization tests，用于在任何 normalization 修改之前锁定当前 `chase_pmu` / `evict_slc` / `chase_migrate` 文本输出，从而证明 normalization 是行为保持的。

`probe analyze`、`probe report` 以及完整 v1.0 baseline measurements 明确不在本阶段范围内（属于 Phase 4）。handoff 已固定 `probe run` 和 `probe resume` 是 Phase 3 唯一新增项；本 spec 和 plan 不引入 `probe analyze` 或 `probe report`。

## 2. 已锁定的架构决策（来自 handoff）

以下内容引用自 architect handoff，不开放重新决策。对于 handoff 未明确但实现必须承诺的细节，本 spec 会显式说明并引用约束。

### 2.1 Transaction boundary

> 每个 environment phase 一个 transaction，而不是每个 case 一个 transaction。共享相同 host requirements 的 cases 在同一个 transaction 下运行；在进入下一个 phase 前执行 restoration。

结果：runner 根据 `phase.host_requirements` 对 cases 分组，并针对每个 group 调用一次 `EnvironmentCoordinator.execute(backend, platform_id, requests, work, allow_mutation)`。每次 `execute` 调用内部的 `work` callback 会遍历该 phase 中的 cases，为每个 case 调用对应的 `ProbeAdapter`，并组装 `Sample` records。共享同一 phase 的 cases 共享一次 host-mutation cycle。

### 2.2 Resume source

> `probe resume` 读取先前的结构化 `RunResult`。Environment journals 仅用于 environment recovery。

结果：`probe resume --run <path>` 打开先前的 `RunResult`，计算未产生 `status: "ok"` `Sample` 的 cases 集合，并只重跑这些 cases。不会查询先前 run 的 journal；如果先前 host 被遗留在 mutated state，则由 `probe doctor` / `probe restore` 处理。这是刻意的职责分离：journals 描述 *host* state；results 描述 *measurement* state。

### 2.3 Execution boundary

> 平台无关 runner 调用可注入的 probe/process adapters。它不包含 GB10/M4 分支、sysfs paths 或 experiment-specific parsing。

结果：runner 和 adapters 只从 `arm64_probe.platforms`、`arm64_probe.domain` 以及 standard library 导入。它们绝不读取 `/sys/`、`/proc/`、`runner/`，也不读取 `configs/platforms/` 下的任何配置。Probe output parsing 位于各自 adapter 中，绝不位于 runner 中。Adapter selection 基于 `scenario.id` 和 adapter registry，而不是 `platform_id`。

### 2.4 Legacy boundary

> 冻结的 `runner/run_pmu*.sh`、`data/`、`analysis/`、`baseline/` 和 `runner/cache_info_*` 保持不变。新的 adapters 可以保留其行为，但不得将 frozen runners 作为新的公共控制面调用。

结果：未来的 “legacy wrapper” adapter 可以调用 `runner/run_pmu_v2.7.7.sh` 以保留行为，但该 adapter 不位于 `probe run` happy path 上。Phase 3 只交付三个 direct C-probe adapters；legacy-wrapper adapter 是本阶段 non-goal。

### 2.5 Mutation boundary

> `probe run` 是唯一新的公共 mutation 入口点，并且必须使用既有 coordinator、lock、journal、restoration 和 `--allow-mutation` contract。不自动调用 `sudo`。

结果：CLI 不调用 `sudo`。公共 mutation 同时要求 `--allow-mutation` 和调用者权限。runner 与 `EnvironmentCoordinator` 共同执行 Phase 2 的 `11`/`12`/`13`/`14` 矩阵；`probe run` 在 probe-execution failure 时新增 `15`，在 `RunResult` persistence failure 时新增 `16`（见 §3）。

### 2.6 Result boundary

> 本地 runs 写入被忽略的 `results/runs/`。Promotion 到 `results/baselines/<version>/` 是一个单独的、经过审阅的动作。

结果：`RunResultStore.write_local(result)` 写入 `results/runs/<run_id>.json`（被 git 忽略）。Phase 3 没有任何 CLI 写入 `results/baselines/`。Promotion 留给用户通过 filesystem copy 完成，或通过 `probe promote` 完成；后者是 Phase 4 命令。

## 3. 公共契约新增项

### 3.1 新的 `ExitCode` 值（由 handoff 冻结）

| Code | Name | Meaning |
|---|---|---|
| `15` | `PROBE_EXECUTION` | probe 启动失败、timeout、signal、非零退出、malformed/partial/empty machine-readable output，或任何其他不属于 transaction failure 的 per-case failure |
| `16` | `RUN_RESULT` | `RunResult` 读取、校验、schema-compatibility 或 atomic-persistence failure |

这两个值添加到 `arm64_probe/errors.py`，与 Phase 2 enum 并列；runner 按名称引用它们，并由 `tests/contract/test_exit_codes.py` 断言（新的 contract test，见 §6）。

### 3.2 新的 `probe run` CLI surface

```text
probe run [--platform <id>] [--profile <id>] [--select <id> ...]
          [--cluster <id>] [--core-group <id>]
          [--cpu <int>] [--src-cpu <int>] [--dst-cpu <int>]
          [--samples <int>] [--working-set <size>]
          [--page-policy default|hugepage]
          [--case <stable-case-id>]
          [--case-timeout <seconds>] [--no-case-timeout]
          [--output-dir <path>]
          [--allow-mutation]
          [-o table|json]
          [<target> ...]
```

规则：

- Selection 和 override semantics 与 `probe plan` **完全相同**。runner 通过现有 `Planner` 计算相同的 `Plan`，然后执行它。`tests/contract/test_run_plan_equivalence.py` contract 断言：相同选择下，`probe plan ...` 与 `probe run ...`（使用 `--output table`）产生相同的 case IDs 和 parameters。
- 至少需要一个 target 或 `--profile`；否则 argparse 抛出 `usage error (2)`。
- `--case <stable-case-id>` 通过 stable ID 精确选择一个 case；runner 验证该 ID 是否是 resolved `Plan` 中某个 case 的 substring match。不匹配 → `usage error (2)`。
- 当 plan 包含任何 `host`-scoped environment requirement（即任何 controller request）时，必须指定 `--allow-mutation`。缺失 → 在 host writes 前返回 `11`。这是 Phase 2 contract 的重新应用；参见 `tests/contract/test_run_authorization.py`。
- `--output-dir` 默认是 `results/runs/`（被 git 忽略）。store 在目录不存在时以 mode `0o755` 和 ownership `os.geteuid()` 创建。
- **Case timeout：** 默认每个 case `60` 秒（理由见 §5.4）。`--case-timeout <seconds>` 覆盖；`--no-case-timeout` 完全禁用 timeout。timeout 会产生一个 `status: "error"` 的 `Sample` 和一个 `ProbeFailure(stage="timeout")`，runner 记录该 per-case failure，但不中止周围 phase；该 phase 中的下一个 case 会继续执行。timeout 的 exit code 是 `15`（probe execution）——见 §5.4。
- 短选项仅限 `-h`/`--help` 和 `-o`/`--output`（Phase 1 contract）。`--allow-mutation`、`--case`、`--case-timeout`、`--output-dir`、`--cpu` 等均必须使用长形式。
- 只有当每个 case 都产生 `status: "ok"` samples，并且 `RunResult` 成功写入时，exit code 才是 `0`。否则为 `15`（case failure）或 `16`（persistence failure），其中 environment restore priority `13` 高于 `15`/`16`。

### 3.3 新的 `probe resume` CLI surface

```text
probe resume --run <path-to-run-result-json>
             [--output-dir <path>]
             [--case-timeout <seconds>] [--no-case-timeout]
             [--allow-mutation]
             [-o table|json]
```

规则：

- `--run` 必填，并且必须指向一个 schema-valid 的 `RunResult` JSON 文件。
- CLI 校验兼容性（见 AC5 和 §5.6）：相同 `schema_version`、相同 `platform_id`、相同 `repository_id`、相同 `repository_commit`、相同 `case_definitions_signature`（见 §4.5）。任何不匹配 → `RUN_RESULT` exit `16`，并带 structured error。
- runner 计算 prior `RunResult` 的 `samples` 与当前 `Plan` 中 case IDs 集合之间的差异。当前 `Plan` 由 prior `Plan` 加上 CLI 上任何新的 `selections` 重建。已经是 `status: "ok"` 的 cases 会被 carry over；失败 cases 会被重新执行；标记为 `status: "skipped"` 的 cases **不会重新执行，也不会被 carry over**（理由见 §5.5）。新的 `RunResult` 在其 `summary` map 中记录 `prior_run_id` 和 `resume_kind`（`"missing"`、`"failed"` 或 `"no-op"`）。先前的 `RunResult` 不被修改。
- 对一个完全成功的 `RunResult` 反复执行 `probe resume` 是成功的 no-op，返回 `0`，并写入一个新的 `RunResult`，其中 `resume_kind: "no-op"`。
- **`schema_version` mismatch（例如 `1` vs `2`）：** compatibility check 返回 `ProbeError(16)`，并在重新执行任何 case 之前中止 resume。Phase 3 没有 auto-conversion path；用户应从头重新执行原始 `probe run`，或等待未来的 `probe convert` 命令（Phase 4 deliverable）。理由见 §5.6。

### 3.4 从早期阶段继承的不变量

- `probe --help` 和 `probe help <topic>` 将 `run` 与 `resume` 和既有命令一同枚举。handoff 要求对 `probe help run` 和 `probe help resume` 进行 contract-tested。
- `--output table|json` 对 `run` 和 `resume` 均有效。JSON output 发出一个 `to_data(RunResult)` object（见 §4.4）。
- `probe run` 和 `probe resume` 不接受 `python3` / state-root override；它们不能绕过 `EnvironmentCoordinator`、`MutationLock`、`JournalStore` 或 `EnvironmentRecovery`。
- `arm64_probe/` 中不得出现 `if platform == "gb10"` / `if platform == "m4"` 分支。Phase 2 acceptance test 扩展覆盖 `arm64_probe/execution/`、`arm64_probe/runner/` 和 `arm64_probe/backends/adapters/`。
- 新模块中的每个 Python invocation 都通过 Makefile 中的 `uv run --no-sync python` 执行；`probe` shebang 保持 Phase 2 toolchain pin 不变。

## 4. Module layout（增量添加，不删除）

新模块（全部位于 `arm64_probe/` 下）：

```text
arm64_probe/
  execution/
    __init__.py
    adapters/
      __init__.py
      base.py            # ProbeAdapter Protocol + ProbeOutcome dataclass
      chase_pmu.py       # ChasePmuAdapter
      evict_slc.py       # EvictSlcAdapter
      chase_migrate.py   # ChaseMigrateAdapter
      legacy_wrapper.py  # Stub; documents the non-goal for Phase 3
    runner.py           # Runner (plan -> samples -> RunResult)
    result_store.py     # RunResultStore (atomic write, read, validate)
    resume.py           # ResumeService (diff prior -> plan -> runner)
  diagnostics/
    doctor.py           # existing; unchanged
```

所有新模块遵循 Phase 2 conventions：

- frozen `@dataclass(frozen=True)` records；
- `JsonScalar` mappings（sorted-unique keys）；
- 基于 `tuple` 的 public models；
- `unittest` tests 位于 `tests/unit/`，contract tests 位于 `tests/contract/`，integration tests 位于 `tests/integration/`；
- 无 platform-name branches，无 `python3` literals，无 `subprocess.run(shell=True)`。

### 4.1 `ProbeAdapter` protocol

```python
# arm64_probe/execution/adapters/base.py
class ProbeFailure(Protocol):
    @property
    def stage(self) -> str: ...          # "ok" | "error" | "skipped"
    @property
    def metrics(self) -> tuple[tuple[str, JsonScalar], ...]: ...
    @property
    def evidence(self) -> tuple[str, ...]: ...
    @property
    def failure(self) -> ProbeFailure | None: ...


class ProbeAdapter(Protocol):
    adapter_id: str                          # "chase_pmu.v2.7.3"
    scenario_id: str                         # "cache-latency.l1-latency"
    schema_version: int                      # 1
    @property
    def supported_cpu_modes(self) -> tuple[str, ...]: ...

    def build_argv(self, request: RunRequest) -> tuple[str, ...]: ...
    def parse_output(
        self, *, stdout: str, stderr: str, exit_code: int, timed_out: bool
    ) -> ProbeOutcome: ...
    def known_failure_modes(self) -> tuple[ProbeFailureMode, ...]: ...
```

每个 concrete adapter 都是一个 `@dataclass(frozen=True)`，通过 typed dataclass 接收 argv-builder 参数，例如 `ChasePmuArgs(size_kb, warm, force_rounds, seed, clflush, hugepage, cpu)`，并由 `build_argv` 方法渲染为 `tuple[str, ...]`。`parse_output` 方法是 `(stdout, stderr, exit_code, timed_out)` 的 pure function，并返回 `ProbeOutcome`。这可以脱离 `subprocess` 进行独立测试。

Adapter selection 基于 `scenario.id`：

- `cache-latency.l1-latency` / `.l2-latency` / `.l3-latency` / `.slc-latency` → `ChasePmuAdapter`
- `cache-latency.dram-latency` → `ChasePmuAdapter`（cold DRAM 使用同一个 probe，参数为 `warm=0`、`force_rounds=1`，并使用现有 probe 已经发出的 `[COLD]` marker）
- `migration-latency.*` → `ChaseMigrateAdapter`
- `evict_slc` **不是 scenario**；它是 `ChasePmuAdapter` 为 cold DRAM case 使用的 setup tool。`EvictSlcAdapter` 位于 `adapters/evict_slc.py` 中是为了完整性，并注册到一个 synthetic `evict-slc.setup` scenario，以便未来 scenarios 调用；Phase 3 中它没有 `probe run` 暴露面。

`Runner` 从一个 frozen `ADAPTER_REGISTRY: dict[str, ProbeAdapter]` 中根据 `scenario_id` 解析 adapter。该 registry 在 module import 时填充。registry 内部没有 platform-name lookup。

### 4.2 `Runner`（plan -> samples -> RunResult）

```python
# arm64_probe/execution/runner.py
@dataclass(frozen=True)
class RunRequest:
    case: Case
    platform_id: str
    backend: HostBackend
    allow_mutation: bool


class Runner:
    def __init__(self, adapter_registry: AdapterRegistry, store: RunResultStore): ...

    def run(
        self,
        plan: Plan,
        *,
        platform_id: str,
        backend: HostBackend,
        allow_mutation: bool,
        output_dir: Path,
        run_id: str | None = None,
        toolchain_evidence: ToolchainEvidence | None = None,
        started_at: datetime | None = None,
    ) -> RunResult: ...
```

算法（依赖顺序，不是 commit 顺序）：

1. 校验 `platform_id` 与 `Plan.platform_id` 一致；如果用户传入 `--platform auto`，通过 `arm64_probe/cli/main.py` 中现有 `_resolve_platform` helper 解析。
2. 按 `phase.host_requirements` 对 `plan.cases` 分组（一个 `EnvironmentPhase` → 一次 `execute` 调用）。`arm64_probe.planning.planner.Planner` 上已有的 `_environment_phases` static method 会产生这些 groupings；runner 复用它（不新增 planner 代码）。
3. 对每个 phase，调用 `EnvironmentCoordinator.execute(backend, platform_id, requests, work, allow_mutation)`，其中 `work()` 遍历该 phase 中的 cases，调用 `adapter.build_argv`，然后调用 `subprocess.run(adapter.build_argv, ..., timeout=case_timeout, text=True, capture_output=True)`，随后调用 `adapter.parse_output`，并累积 `Sample` records。subprocess 是唯一调用 probe 的位置；runner 本身绝不解析 probe output。
4. 每个 phase 结束后，如果该 phase 失败且 `EnvironmentCoordinator` 抛出异常，则 runner：
   - 持久化 partial `RunResult`（包含截至并包括该 phase 已收集的 samples），并设置 `result.complete = False`；
   - 重新抛出原始 `ProbeError`，或在底层 failure 是 per-case execution issue 时包装为新的 `ProbeError`，其 `code: 15`，且绝不掩盖 `12` / `13` / `14`。
5. 全部成功时，runner：
   - 构建 `RunResult`，包含 `samples: tuple[Sample, ...]`、`summary`（case counts、status histogram、toolchain evidence、repo commit、dirty-tree status）和 `environment`（controller list + final observed state）；
   - 通过 `RunResultStore.write_local` 持久化 `RunResult`；
   - 返回 `RunResult`。

runner 本身不以 `shell=True` 导入或调用 `subprocess`；它使用 `subprocess.run(argv, ..., shell=False)`，与 `arm64_probe/backends/io.py:19` 中现有 `CommandExecutor` protocol 已强制的方式一致。复用 `CommandExecutor` protocol；runner 构造函数接受注入的 `CommandExecutor`，以便测试传入 recording fake，例如 `tests/support/executor_recorder.py`（新增，见 §6）。

### 4.3 `RunResultStore`

```python
# arm64_probe/execution/result_store.py
class RunResultStore:
    def __init__(self, root: Path, *, schema_version: int = 1): ...
    def write_local(self, result: RunResult) -> Path: ...
    def read(self, path: Path) -> RunResult: ...
    def validate_compatibility(
        self, prior: RunResult, current_plan: Plan
    ) -> None: ...   # raises ProbeError(16) on mismatch
```

规则（AC4）：

- 磁盘文件为 `<run_id>.json`，写入 `root` 下。`write_local` 使用与 `JournalStore._atomic_write` 相同的 atomic-replace pattern（参见 `arm64_probe/environment/journal.py:338`）：写入 `.<run_id>.<uuid>.tmp`、`fsync`、`os.replace`、parent `fsync`。中断的写入绝不替换最后一个有效 result。
- `read` 使用与 `JournalStore.read` 相同的 `O_NOFOLLOW` + owner-check + size-cap pattern。store 拒绝 `root/` 外部路径、symlinks，以及 parent directory 不安全的文件。
- `validate_compatibility`（由 `probe resume` 使用）：要求相同 `schema_version`、相同 `platform_id`、相同 `repository_id`、相同 `repository_commit`（从 `summary["repository_commit"]` 提取），以及相同 `case_definitions_signature`（对排序后的 `Case.id` 集合 + scenario parameter schemas 计算稳定 hash）。不匹配 → `ProbeError(code: 16)`。
- `to_data(result)` 和 `from_data(payload)`（位于 `arm64_probe/serialization/model_json.py`）处理 `schemas/` 中的 `Sample` 和 `RunResult` schemas。

### 4.4 Public dataclass changes

- `RunResult`（现位于 `arm64_probe/domain/models.py:142`）新增一个 optional field：`prior_run_id: str | None = None`，以及 `resume_kind: str | None = None`。非 resume 路径下二者默认均为 `None`。dataclass 保持 frozen。
- `Sample` 不变。
- 新增 `ToolchainEvidence` dataclass，记录 `python_version`（例如 `"3.13.13"`）、`uv_version`（例如 `"0.11.18"`）、`cc`（例如 `"cc"`）以及发现的 `host_os`（例如 `"Darwin"`）。runner 将其记录到 `RunResult.summary` 中。

### 4.5 Case definitions signature

```python
# arm64_probe/execution/result_store.py
def case_definitions_signature(plan: Plan) -> str:
    """Stable hash of the resolved cases that determines
    cross-version compatibility for `probe resume`."""
```

实现方式：对如下内容计算 SHA-256：

```text
"\\n".join(f"{c.id}\\t{c.scenario_id}\\t{...sorted(c.parameters...)}" for c in sorted(plan.cases, key=lambda c: c.id))
```

存储在 `RunResult.summary["case_definitions_signature"]` 中。
`probe resume` 将它与自身重建出的 plan 的 signature 进行比较；不匹配 → `16`。

## 5. Result lifecycle（文字版 sequence diagram）

一个 case、一个 phase 的成功 `probe run`：

1. CLI 解析参数；通过现有 `Planner` 解析 `Plan`。AC2 中与 `probe plan` 的等价性由 `test_run_plan_equivalence` 断言。
2. Runner 将 plan 分组为 `EnvironmentPhase`s；对于每个 phase，调用 `EnvironmentCoordinator.execute`，参数包括：
   - `requests` = 该 phase 的 `host_requirements` 对应的 `ControllerRequest`s；
   - `work` = 一个 closure，遍历该 phase 中的 cases，通过其 `ProbeAdapter` 运行每个 case，并将 `Sample`s append 到 closure 捕获的 per-run list 中。
3. `EnvironmentCoordinator` 生成 finalized journal（`state: "restored"`，`restoration_status: "succeeded"`），并且 runner 的 `work` callback 返回。runner 将 journal 的 `effective` 和 `after` states 转换为 `RunResult.environment` entries。
4. Runner 组装 `RunResult`；调用 `RunResultStore.write_local(result)`；返回 result。
5. CLI 打印 table view（case ID、status、samples、metrics）或 JSON view（`to_data(result)`）。

单个 case 失败（probe 返回非零退出）：

1. `work` callback 捕获 adapter 抛出的 `ProbeError(code: 15)`；将该 case 的 samples 标记为 `status: "error"`；继续执行 phase 中的下一个 case（因此单个 case failure 不会中止该 phase）。
2. phase 结束后，runner 仍然执行 restoration。partial `RunResult` 写入时设置 `complete: False`。
3. CLI 打印 partial `RunResult` 并以 `15` 退出。

### 5.4 Per-case timeout（理由：默认 60s）

默认 case timeout 是 **60 秒**。理由：

- GB10 smoke profile 下的 `chase_pmu` warm pass（L1-Latency at 32 KiB，7 samples）预期每个 sample 远低于 1 秒；4 KiB cold DRAM variant 更慢，但仍低于 10 秒。
- `chase_migrate` warm + measure 对 GB10 migration matrix 预期低于 5 秒。
- `evict_slc --quiet` 使用 64 MiB 和 `posix_memalign` working set，受 memory bandwidth 约束；在 GB10 上低于 2 秒。
- 60s 是三个 probes 中最坏预期 wall time 的 **6×**；这是用于覆盖意外 page-table walks、NUMA cold paths 和 contention 的安全裕量。
- 30s 替代方案是最坏预期的 3×；相较于 30s 的误超时，60s 成本更低。120s 替代方案浪费时间，并会掩盖真实 hang。

当 timeout 触发时，`subprocess.run(..., timeout=N)` 抛出 `subprocess.TimeoutExpired`。adapter 的 `parse_output(timed_out=True, exit_code=-1, stdout="", stderr="")` 返回 `status: "error"`，以及 failure：

```text
ProbeFailure(stage="timeout", category="case_timeout", message=f"exceeded {N}s")
```

runner 将其映射为 `ProbeError(code: 15)`；该 case 以 `status: "error"` 记录到 `RunResult` 中，并且周围 phase 继续执行。timeout 的 exit code 是 `15`（probe execution）。

### 5.5 Resume sample state machine（理由：仅重新记录必要项）

`probe resume` 的 `ResumeService` 产生一个新的 `RunResult`。
从 prior `RunResult.samples` 到新 `RunResult.samples` 的映射如下：

| Prior case status | Action in new `RunResult` |
|---|---|
| `ok` | Carry over prior `Sample`（保留其原始 `run_id`、`sample_index`、`metrics`、`evidence`） |
| `error` | 重新执行 case；记录新的 `Sample`（使用新 run 的 `run_id` 和新的 `sample_index`） |
| `skipped` | **不重新执行；不 carry over。** 新 `RunResult` 不包含该 case 的 sample。 |

理由：

- carry over `ok` 可保留用户先前结果；重新执行 `ok` case 会浪费，并且如果 probe 存在噪声，可能引入非确定性。
- 重新执行 `error` 是 `probe resume` 的核心目的。
- `skipped` **不重新执行且不 carry over**，因为 `skipped` sample 不是测量结果；它是“该 case 未运行”的记录。carry over 它会误导未来读者，使其认为该 case 在新 run 中被测量。`ResumeService` 记录 `summary["skipped_cases"]`，以便用户看到哪些 cases 被有意不重新执行。

新 `RunResult` 记录：

```text
summary["prior_run_id"] = prior.run_id
```

以及：

```text
summary["resume_kind"] ∈ {"missing", "failed", "no-op"}
```

其中 `"missing"` 覆盖 case 存在于新 `Plan` 但不存在于 prior `RunResult` 的情况；`"failed"` 覆盖 case 在 prior `RunResult` 中存在且 `status: "error"` 的情况。

### 5.6 Resume 上的 schema-version compatibility（理由：严格拒绝）

当 `probe resume` 读取 prior `RunResult` 且 prior 的 `schema_version` 与当前 `RunResult` schema version（Phase 3 中为 `2`）不匹配时，resume 以 `ProbeError(code: 16)` 中止，并给出如下结构化消息：

```text
probe resume: prior RunResult schema_version=1 is not
compatible with the current schema_version=2. Re-run the
original `probe run` from scratch, or wait for a future
`probe convert` command (out of scope for Phase 3).
```

理由：

- Phase 3 schema 新增 `summary.case_definitions_signature`、`summary.repository_commit`、`summary.dirty_tree`、`summary.toolchain`、`summary.prior_run_id`、`summary.resume_kind` 和 `environment.toolchain`。
- `schema_version=1` 的 prior `RunResult` **不包含**这些字段。尤其是 `case_definitions_signature`，它是防止在 Plan 被静默修改后仍然 resume 的主要防线；没有它，对已变化代码库的 resume 会静默成功，并产生一个 sample cases 与记录不一致的 `RunResult`。
- “accept but warn” 路径会使 `case_definitions_signature` 为 `None`，从而静默削弱防线。严格拒绝的成本是用户重新运行一次；静默接受的成本是产生一个与记录 cases 不对应的测量。
- “convert” 路径是 Phase 4 deliverable，需要一个 `probe convert <path>` 命令。Phase 3 明确排除它（按 handoff）。

`probe resume` flow：

1. CLI 读取 prior `RunResult`；调用 `RunResultStore.validate_compatibility`。
2. Runner 将 prior `samples` 与重建的 plan 做 diff；carry over `status: "ok"` cases；重跑其余 cases。
3. 新 `RunResult` 记录 `prior_run_id` 和 `resume_kind`。只有当每个剩余 case 现在都是 `status: "ok"` 时，`complete: True`。

## 6. Test taxonomy（增量添加；Phase 2 pyramid 保持不变）

### 6.1 Unit tests（新增于 `tests/unit/`）

- `test_chase_pmu_adapter.py` —— argv builder，基于 captured fixture strings 的 `parse_output`（直接传入 adapter，不 spawn），missing/nonzero output 上的 `parse_output`，以及 `timed_out=True` 下的 `parse_output`。
- `test_evict_slc_adapter.py` —— argv builder，默认 `--quiet`（无 stdout），`--verbose` parsing。
- `test_chase_migrate_adapter.py` —— argv builder，跨三个 `>>>` markers（`src_latency`、`migrate_latency`、`migrate_penalty`）的 stdout parsing，affinity 和 hugepage-failure handling。
- `test_runner.py` —— 将 `Plan` 分组到 phases，调用 fake `EnvironmentCoordinator`（或通过 `tests/support/fake_coordinator.py` 的 recording fake —— 新增），组装 `RunResult`，原样传播 exit codes 12/13/14。
- `test_result_store.py` —— atomic write、parent fsync、symlink rejection、size cap、`validate_compatibility` table。
- `test_resume.py` —— diff logic、repeated-resume idempotency、compat rejection（四个 compat fields 分别覆盖）。
- `test_characterization_probes.py` —— **必须最先添加**（见 plan Task 14）。捕获当前 `chase_pmu`、`evict_slc`、`chase_migrate` 文本输出为 fixtures，并断言 adapters 的 `parse_output` 复现预期 `metrics`。这是 handoff 要求的 behavior-pinning layer。

### 6.2 Contract tests（新增于 `tests/contract/`）

- `test_cli_run.py` —— §3.2 中每个 example（positional target list、`--profile`、`--case`、缺失 `--allow-mutation`、table output、JSON output、exit code 11/15/16）。
- `test_cli_resume.py` —— happy path、prior `RunResult` read error（`16`）、compat rejection（`16`）、no-op（resume_kind: `"no-op"`）、repeated resume idempotency。
- `test_run_plan_equivalence.py` —— 相同 selection 下，`probe plan` 与 `probe run --output table` 产生相同 case IDs 和 parameter values。
- `test_exit_codes.py` —— 断言 `arm64_probe.errors` 中存在 `PROBE_EXECUTION (15)` 和 `RUN_RESULT (16)`，且 contract test table 与其一致。
- `test_probe_adapters.py` —— 每个 concrete adapter 都满足 public contract（`build_argv`、`parse_output`、`schema_version`、`supported_cpu_modes`）。`legacy_wrapper.py` 只注册用于文档说明，不用于 execution。
- 对现有测试的更新：`test_public_schemas.py` 将 `sample.schema.json` 和 `run-result.schema.json` 加入 required-keys table；`test_phase2_acceptance.py` 扩展为禁止新 `arm64_probe/execution/` 和 `arm64_probe/execution/adapters/` packages 中出现 platform-name branches。

### 6.3 Integration tests（新增于 `tests/integration/`）

- `test_phase3_smoke_workflow.py` —— 使用 fake `Backend` + recording fake `CommandExecutor` + recording fake `EnvironmentCoordinator` 启动 runner；运行 reduced smoke profile；断言 schema-valid `RunResult` 落在临时 `results/runs/` 下。
- `test_phase3_resume_workflow.py` —— 运行 fixture workflow，从 prior `RunResult` 中删除一个 per-case sample，调用 `probe resume`，断言新 `RunResult` 对 carry-over cases 保持相同 run IDs，并为 re-run case 生成新 samples。
- `test_phase3_signal_restore.py` —— runner 的 `work` callback 中途收到 SIGTERM；`EnvironmentCoordinator` 恢复 host，并写入 partial `RunResult`。
- `test_phase3_fixture_workflow.py` —— 等价于 Phase 2 fixture workflow，但针对 `probe run`，使用 `FakeBackend` + `FakeController` + `FakeAdapter`（后者新增 —— 见 §6.4）。

### 6.4 新增测试基础设施

- `tests/support/fake_coordinator.py` —— 记录 `EnvironmentCoordinator.execute` 调用并返回一个 recorded `EnvironmentJournal`。角色类似 `fake_controllers.FakeController`。
- `tests/support/fake_adapter.py` —— 实现 `ProbeAdapter`，带可配置 `parse_output` stub 和 argv recorder。其在 probe 层中的角色类似 `fake_controllers.FakeController`。
- `tests/support/executor_recorder.py` —— 实现 `arm64_probe/backends/io.py:19` 中的 `CommandExecutor`，包含一组 recorded `argv` 和 scripted `CompletedProcess` responses。用于驱动 runner 而不 spawn 真实 probes。
- `tests/fixtures/probe_output/` —— 当前 C probes 的 captured stdout/stderr fixtures，由 `test_characterization_probes.py` 和 per-adapter unit tests 使用。

### 6.5 Makefile contract tests（新增于 `tests/`）

- `tests/test_makefile_contract.py` 扩展：
  - `test_phase3_wrappers_are_thin` —— 断言存在 `make smoke` 和 `make phase3-check`；`smoke` 调用 `uv run --no-sync python`（或现有 wrappers 使用的相同 `$(UV_RUN) python` pattern），`phase3-check` 调用 `unittest discover` + `legacy_manifest.py verify` + 额外 Phase-3-specific contract invocation。
  - `test_phase3_targets_have_no_parsing_or_mutation_logic` —— `smoke` 和 `phase3-check` recipes 不包含 platform 相关 `if/else`、不包含 `/sys/`、不包含 `python3` literal、不包含 probe output parser。

## 7. Makefile targets（增量添加；Phase 2 targets 保持不变）

```makefile
phase3-check:
	$(UV_RUN) python -m unittest discover -s tests -p 'test_*.py' -v
	$(UV_RUN) python scripts/legacy_manifest.py verify
	$(UV_RUN) python -m unittest tests.contract.test_exit_codes -v
	$(UV_RUN) python -m unittest tests.contract.test_run_plan_equivalence -v
	$(UV_RUN) python -m unittest tests.contract.test_cli_run -v
	$(UV_RUN) python -m unittest tests.contract.test_cli_resume -v

smoke:
	$(UV_RUN) python ./probe plan --platform gb10 --profile smoke -o json > $(BUILD_DIR)/smoke-plan.json
	$(UV_RUN) python ./probe run --platform gb10 --profile smoke --allow-mutation \
	    --output-dir $(BUILD_DIR)/smoke-runs
```

`phase3-check` 复用现有 `unittest discover` 和 `legacy-check` bodies；它增加三个 Phase-3-specific contract invocations，以便 per-AC evidence 明确可见。
`smoke` 在 dry-run fixture mode 中调用实际 CLI（见 §8.1）。

`smoke` **不会**修改 host。dry-run recipe 中出现 `--allow-mutation` flag 只是为了覆盖 authorization code path；当 runner 被传入一个不暴露 controllers 的 fake `Backend` 时，它绝不会用非空 `requests` 调用 `EnvironmentCoordinator.execute`，因此 mutation lock 不会被触碰。AC8 由 dry-run 形式满足。

## 8. Open questions（推迟到 implementation plan）

这些不是 spec 的 blocker。implementation plan 会解决它们，或显式记录决策。

1. **Probe stdin / output capture。** 现有 C probes 写 stdout；`evict_slc --quiet` 只写 stderr。`CommandExecutor` protocol 捕获二者。adapters 通过注入的 `CommandExecutor` 使用 `subprocess.run(..., capture_output=True)`。无需新决策。
2. **CPU pinning。** `chase_migrate` 通过 argv 接受 `--src-cpu` 和 `--dst-cpu`；`chase_pmu` 需要外部 `taskset -c`。`chase_pmu` 的 runner argv builder 仅在用户传入 `--cpu` 时发出 `taskset -c <cpu>`；传给 `subprocess.run` 的 argv 是 `("taskset", "-c", str(cpu), probe_binary, *args)`。runner 不把 `taskset` 作为库导入；它通过 `CommandExecutor.run(argv)` 执行。
3. **Resume of multi-phase runs。** prior `RunResult` 可能跨多个 environment phases。`probe resume` 必须按 plan 中出现的顺序重新执行每个产生非 `"ok"` sample 的 case，并重新打开 prior phase groups，使 journal transaction sequence 匹配。runner 通过遍历 `plan.environment_phases` 并只重跑尚未 `status: "ok"` 的 cases 实现。
4. **Characterization fixture capture method。** Phase 3 交付的 characterization fixtures 是位于 `tests/fixtures/probe_output/` 下的 **hand-rolled byte-for-byte snapshots**。capture procedure 记录在 code-handoff document `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md` 中（Task 14 添加），而不是写在 `tests/support/capture.py` script 中。理由是 in-tree capture script 需要 spawn C probes，超出 Phase 3 范围。handoff document 会针对每个 fixture file 列出未来开发机上填充该 fixture 所需的精确 `subprocess.run` argv 和 capture flags。

## 9. 本设计明确不做的事情

- 不引入 `probe analyze` 或 `probe report`。它们属于 Phase 4（按 handoff §1）。
- 不引入 “v1.0 baseline” 命令。baseline promotion 是 filesystem copy，或 Phase 4 的 `probe promote`。
- 不声明 GB10 Gate 1 readiness。announcement gate 由用户拥有；本 spec 定义 runbook（见 plan §Phase Completion Gate）。
- 不修改 `runner/run_pmu*.sh`、`data/`、`analysis/`、`baseline/` 或 `runner/cache_info_*.sh`。
- 不放宽 `requires-python = "==3.13.13"` toolchain pin。
- 不引入任何新的 `subprocess` shell command 或 `sudo` invocation。
- **不**添加用于 `schema_version=1 → 2` upgrade 的 `probe convert` 命令。那是 Phase 4 deliverable。Phase 3 对 incompatible schemas 严格拒绝。

## 10. Schema additions（增量添加）

`schemas/sample.schema.json` 和 `schemas/run-result.schema.json` 已经存在（见 Phase 2）。它们会用以下 optional fields 扩展（增量添加；无 breaking change）：

- `sample.schema.json`：
  - `toolchain`（object）：`python_version`、`uv_version`。
- `run-result.schema.json`：
  - `summary.case_definitions_signature`（string，64 hex）。
  - `summary.repository_commit`（string，40 hex）。
  - `summary.dirty_tree`（boolean）。
  - `summary.toolchain`（object，同上）。
  - `summary.prior_run_id`（string，optional）。
  - `summary.resume_kind`（取值之一：`null`、`"missing"`、`"failed"`、`"no-op"`）。
  - `environment.toolchain`（object）。

这些新增项由 AC4 要求（“results record … repository commit, dirty-tree status, toolchain/compiler evidence”）。schemas 是 versioned；`schema_version` 已存在于 `RunResult` 中，并因这些新增项 bump 到 `2`。
handoff 中关于 `probe resume` 的 compatibility rule（上文 §3.3）明确先检查 `schema_version`，因此 `1 → 2` bump 受 gate 控制；理由见 §5.6。

## 11. Cross-references

| Section | Reads |
|---|---|
| §2 | `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §2（locked architecture） |
| §3 | `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §3（required public behavior），`docs/superpowers/specs/2026-06-12-arm64-uarch-probe-v1.0-design.md` §7.4–§7.5 |
| §4 | `arm64_probe/domain/models.py`，`arm64_probe/environment/coordinator.py`，`arm64_probe/backends/base.py`，`arm64_probe/backends/io.py` |
| §5 | 同 §4，外加 `arm64_probe/environment/journal.py:338`（atomic-write pattern） |
| §5.4 | `src/chase_pmu/chase_pmu_v2.7.3.c`（warm pass timing），`src/chase_migrate/chase_migrate_v1.0.c`（warm + measure timing），`src/evict_slc/evict_slc_v1.2.c`（默认 `--quiet` runtime） |
| §5.5 | prior `RunResult` sample status enum（`"ok" | "error" | "skipped"`） |
| §5.6 | `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md` §AC5 中的 schema-version compatibility rule |
| §6 | `tests/support/host_fixture.py`，`tests/support/fake_controllers.py`，`tests/contract/test_phase2_acceptance.py`（AC source of truth） |
| §7 | `Makefile`（现有 `UV`、`UV_RUN`、`phase1-check`、`phase2-check` definitions） |
| §10 | `schemas/sample.schema.json`，`schemas/run-result.schema.json` |

配套的 `plans/2026-06-15-phase3-probes-runner.md` 将本设计转换为 Task 14–Task 20，每个 task 都包含 file map、test map、commit boundary 和 verification command，并将每个 task 映射回 handoff 固定的 AC1–AC9 criteria。

## 12. Architecture Decision Rationale（汇总）

本节汇总 brainstorming flow 捕获的 9 个架构决策的显式 rationale，使读者无需重读对话即可审计本设计。

| # | Decision | Rationale | Locked by |
|---|---|---|---|
| 1 | Transaction granularity：按 environment phase，而不是按 case | Handoff §2.1；降低 lock overhead，并将 `host` mutations 原子化分组 | handoff |
| 2 | Resume data source：prior structured `RunResult`，不是 journal | Handoff §2.2；journals 描述 host state，results 描述 measurement state | handoff |
| 3 | ProbeAdapter boundary：`EvictSlcAdapter` 注册到 synthetic `evict-slc.setup`，不位于 `probe run` happy path | Cold-DRAM case 直接使用 `ChasePmuAdapter`；`evict_slc` 是未来 setup tool，不是 Phase 3 surface | design（低风险，兼容 handoff） |
| 4 | Schema `1 → 2` upgrade on resume：**严格拒绝**（exit `16`） | `case_definitions_signature` 是防止 silent case-set drift 的主要防线；auto-conversion 会削弱它。拒绝的成本：重跑一次。 | brainstorming（高杠杆） |
| 5 | Resume sample state machine：只重新记录必要项（不 carry error → ok；不 carry `skipped`；carry `ok`） | carry `ok` 保留用户结果；重新记录 `error` 是 resume 的目的；`skipped` 是“未运行”——carry 它会误导 | brainstorming（高杠杆） |
| 6 | Default case timeout：`60` 秒（通过 `--case-timeout` / `--no-case-timeout` 覆盖） | 三个 probes 最坏预期 wall time 的 6×；比 30s 误超时更低成本；120s 浪费 | brainstorming（高杠杆） |
| 7 | Characterization fixture capture：hand-rolled byte-for-byte snapshots，记录在 code-handoff 中（无 `tests/support/capture.py`） | in-tree capture script 需要 spawn C probes；hand-rolled fixtures 可由任何开发机复现 | brainstorming（高杠杆） |
| 8 | Mutation-vs-non-mutation boundary：由 Phase 2 contract 强制（缺失 `--allow-mutation` → host writes 前返回 `11`） | 当 plan 包含任何 `host` requirement 时要求 `--allow-mutation`；不是新决策 | handoff |
| 9 | GB10 Gate 1 runbook commit：包含在 Phase 3 acceptance commit 中；用户在 Gate 1 时审阅 runbook | runbook 是 deliverable，不是代码；与 acceptance evidence 捆绑保持 handoff chain 完整 | design（低风险） |

前两个由 architect 锁定；后七个由 implementer 在 brainstorming flow 下断言。