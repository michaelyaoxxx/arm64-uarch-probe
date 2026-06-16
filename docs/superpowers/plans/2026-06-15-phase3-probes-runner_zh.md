# Phase 3 Probes and Unified Runner — 实施计划

> **面向 agentic workers：** REQUIRED SUB-SKILL：使用
> `superpowers:subagent-driven-development`（推荐）或
> `superpowers:executing-plans`，逐 task 实施本计划。
> Steps 使用 checkbox（`- [ ]`）语法进行跟踪。
>
> **配套设计：** `docs/superpowers/specs/2026-06-15-phase3-probes-runner-design.md`。
> **架构契约：** `docs/superpowers/handoffs/2026-06-15-phase3-handoff.md`（AC1–AC9、已锁定架构、质量控制）。

**目标：** 实现统一测量 runner。具体而言，交付 `probe run`、`probe resume`、atomic `RunResult` persistence，以及 `make smoke` / `make phase3-check` wrappers；全部建立在现有 `EnvironmentCoordinator` 和已固定的 CPython 3.13.13 toolchain 之后 —— 不触碰任何 frozen 或 transitional path，不在任何位置添加 `if platform == "gb10"` 分支，并且不代替 architect 宣称 GB10 Gate 1 readiness。

**架构：** Phase 3 在 Phase 2 之上增量添加。`Runner` 消费现有 `Planner` 生成的 `Plan`，按 `EnvironmentPhase` 对 cases 分组，并对每个 phase 调用一次 `EnvironmentCoordinator.execute`。在每次 `execute` 调用内部，`work` closure 通过注入的 `CommandExecutor` 驱动逐 case 的 `ProbeAdapter` 调用。runner 自身绝不解析 probe output；解析由各 `ProbeAdapter` 完成。结果累积为 `RunResult` records（schema v2，包含 `case_definitions_signature`、`repository_commit`、`toolchain`、`prior_run_id`、`resume_kind`），并以原子方式落盘到 `results/runs/<run_id>.json`（被 git 忽略）。`probe resume` 读取 prior `RunResult`，严格校验四个 compatibility fields（无 auto-conversion），diff sample state，并只重跑 `error` cases。两个新的 `ExitCode` 值（`15`、`16`）补齐 exit-code ladder；Phase 2 中其余 `0`–`14` 矩阵保持不变。

**技术栈：** Python 3.13.13（uv-managed，固定于 `.python-version` / `pyproject.toml` / `uv.lock`）；standard library；现有 `arm64_probe` packages。C probes 继续通过 `make build` 构建，并通过 `subprocess.run(argv, shell=False, text=True, capture_output=True, timeout=60)` 执行，该执行由 `arm64_probe/backends/io.py:19` 中的 injected `CommandExecutor` protocol 驱动。Public schemas 使用 JSON Schema 2020-12。Make，Git。

## Delivery Boundaries

- 所有开发、characterization 和 acceptance runs 都在 Mac 或临时 Linux sysfs/procfs fixture trees 上进行。**不触碰 GB10 硬件。** GB10 Gate 1 readiness 只由用户宣布；本计划以 runbook 结束，而不是以公告结束。
- Phase 3 **不得**修改 `runner/run_pmu*.sh`、`data/`、`analysis/`、`baseline/` 或 `runner/cache_info_*.sh`。会记录一个 frozen legacy-wrapper adapter，但它**不会**注册到 `probe run` happy path；如果后续 task 需要它，应作为单独 scoped concern 处理。
- Phase 2 架构、toolchain pin、environment transaction model，以及 journal / lock / restoration contract **不重新决策**。本计划复用 `EnvironmentCoordinator.execute`、`JournalStore._atomic_write` 和现有 `ControllerRequest` ordering。不引入新的公共 mutation 入口点；`probe run` 是 Phase 3 唯一新增的此类入口点。
- Makefile 只扩展极薄的 `smoke` 和 `phase3-check` wrappers。不在 Makefile 中出现 scenario matrix、platform-name branch、probe output parser、mutation logic 或 result logic。
- `probe run` 中的公共 mutation 同时要求 `--allow-mutation` 和调用者权限。CLI 绝不调用 `sudo`，也不接受公共 `--state-root` override。
- Python toolchain 保持 `==3.13.13`。不 bump version，不引入新 dependency，不放宽 `requires-python`。
- `probe` shebang（`uv run --no-sync python`）保持不变。
- `probe analyze` 和 `probe report` **超出范围**（Phase 4）。

## Architecture Decision Anchors（来自 spec §12）

本计划中的 tasks 按 spec 现有设计实施。
brainstorming flow 捕获的 9 个架构决策在此锚定，供 implementer 使用：

| # | Decision | Implemented in |
|---|---|---|
| 1 | Transaction granularity：按 environment phase，而非按 case（handoff §2.1） | Task 17（`Runner` algorithm step 2） |
| 2 | Resume data source：prior `RunResult`（handoff §2.2） | Task 19（`ResumeService`） |
| 3 | `EvictSlcAdapter` 注册到 synthetic `evict-slc.setup`，不位于 `probe run` happy path | Task 15（Step 5） |
| 4 | Schema `1 → 2` upgrade：resume 时严格拒绝（exit `16`） | Task 16（`RunResultStore.validate_compatibility`）和 Task 19（`ResumeService` abort path） |
| 5 | Resume sample state machine：重新记录 `error`，carry `ok`，drop `skipped` | Task 19（Step 3） |
| 6 | Default case timeout：60 秒（通过 `--case-timeout` / `--no-case-timeout` 覆盖） | Task 17（Step 3，`Runner` argv builder）和 Task 18（parser） |
| 7 | Characterization fixture capture：hand-rolled byte-for-byte snapshots，记录于 code-handoff，无 `tests/support/capture.py` | Task 14（Step 3） |
| 8 | Mutation boundary：当 plan 有 `host` requirements 时要求 `--allow-mutation`（重新应用 Phase 2 contract） | Task 18（Step 4） |
| 9 | GB10 Gate 1 runbook commit：包含在 Phase 3 acceptance commit 中 | Task 20（Step 8） |

## File Map

### 新模块（增量添加到 `arm64_probe/` 下）

- `arm64_probe/execution/__init__.py`
- `arm64_probe/execution/adapters/__init__.py`
- `arm64_probe/execution/adapters/base.py` — `ProbeAdapter` Protocol + `ProbeOutcome` dataclass + `ProbeFailure` / `ProbeFailureMode` records
- `arm64_probe/execution/adapters/chase_pmu.py` — `ChasePmuAdapter`
- `arm64_probe/execution/adapters/evict_slc.py` — `EvictSlcAdapter`（注册到 synthetic setup scenario）
- `arm64_probe/execution/adapters/chase_migrate.py` — `ChaseMigrateAdapter`
- `arm64_probe/execution/adapters/legacy_wrapper.py` — documentation-only stub；不注册用于 execution
- `arm64_probe/execution/runner.py` — `Runner` 和 `RunRequest` / `ToolchainEvidence` records
- `arm64_probe/execution/result_store.py` — `RunResultStore` + `case_definitions_signature`
- `arm64_probe/execution/resume.py` — `ResumeService`

### 对现有模块的增量修改

- `arm64_probe/errors.py` — 将 `PROBE_EXECUTION = 15`、`RUN_RESULT = 16` 添加到 `ExitCode`；handoff contract test 断言二者存在。
- `arm64_probe/domain/models.py` — 给 `RunResult` 增加 `prior_run_id: str | None = None` 和 `resume_kind: str | None = None`（frozen dataclass；新增字段，默认 `None`；因为新字段 optional，不破坏现有 consumers）。
- `arm64_probe/serialization/model_json.py` — 扩展 `to_data()`，支持 `Sample`、`RunResult`、`ToolchainEvidence`；将 `RunResult` `schema_version` bump 到 `2`（见 Task 16）。
- `arm64_probe/cli/parser.py` — 添加 `run` 和 `resume` subcommands；扩展 `COMMANDS` 以包含它们。
- `arm64_probe/cli/main.py` — dispatch `run` 和 `resume`；与 `plan` 完全一致地解析 `Platform`。
- `arm64_probe/cli/render.py` — 添加 `render_run`、`render_resume`（table 和 JSON branches）。
- `Makefile` — 添加 `smoke` 和 `phase3-check` targets；扩展 `help` 文本和 `.PHONY` list。
- `schemas/sample.schema.json` — 添加 optional `toolchain` object。
- `schemas/run-result.schema.json` — 添加 optional `summary.case_definitions_signature`、`summary.repository_commit`、`summary.dirty_tree`、`summary.toolchain`、`summary.prior_run_id`、`summary.resume_kind`、`environment.toolchain`；记录 `schema_version` bump 到 `2`。
- `tests/support/fake_coordinator.py` — 新增。
- `tests/support/fake_adapter.py` — 新增。
- `tests/support/executor_recorder.py` — 新增。
- `tests/fixtures/probe_output/chase_pmu_v2.7.3/` — 新增（`chase_pmu` 的 captured stdout/stderr fixtures）。
- `tests/fixtures/probe_output/evict_slc_v1.2/` — 新增。
- `tests/fixtures/probe_output/chase_migrate_v1.0/` — 新增。

### Tests（增量添加）

- `tests/unit/test_characterization_probes.py`
- `tests/unit/test_chase_pmu_adapter.py`
- `tests/unit/test_evict_slc_adapter.py`
- `tests/unit/test_chase_migrate_adapter.py`
- `tests/unit/test_runner.py`
- `tests/unit/test_result_store.py`
- `tests/unit/test_resume.py`
- `tests/contract/test_cli_run.py`
- `tests/contract/test_cli_resume.py`
- `tests/contract/test_run_plan_equivalence.py`
- `tests/contract/test_exit_codes.py`
- `tests/contract/test_probe_adapters.py`
- `tests/integration/test_phase3_smoke_workflow.py`
- `tests/integration/test_phase3_resume_workflow.py`
- `tests/integration/test_phase3_signal_restore.py`
- `tests/integration/test_phase3_fixture_workflow.py`
- `tests/test_makefile_contract.py` — 扩展（现有文件）

### Frozen / transitional paths（不得修改）

`runner/`、`data/`、`analysis/`、`baseline/`、`runner/cache_info_*.sh`。若这些路径中的任何文件被意外 commit 修改，则 Phase 3 Completion Gate 失败。

### Code-handoff document（Task 14 添加，但不在本 plan 中 commit）

- `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md` — 捕获每个 fixture file 对应的精确 `subprocess.run` argv 和 capture flags；implementer 按该文档 hand-roll fixture bytes。

## Public Type Contract（对 Phase 2 的增量）

```python
# arm64_probe/errors.py
class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    CONFIG = 3
    CAPABILITY = 4
    PLANNING = 5
    HOST_INSPECTION = 10
    MUTATION_AUTHORIZATION = 11
    ENVIRONMENT_APPLY = 12
    ENVIRONMENT_RESTORE = 13
    ENVIRONMENT_BUSY = 14
    PROBE_EXECUTION = 15   # NEW
    RUN_RESULT = 16        # NEW


# arm64_probe/execution/adapters/base.py
@dataclass(frozen=True)
class ProbeFailure:
    stage: str         # "launch" | "timeout" | "exit" | "parse" | "signal"
    category: str
    message: str


@dataclass(frozen=True)
class ProbeFailureMode:
    stage: str
    category: str
    regex: str          # matched against the probe's stderr for diagnostics


@dataclass(frozen=True)
class ProbeOutcome:
    status: str                                    # "ok" | "error" | "skipped"
    metrics: tuple[tuple[str, JsonScalar], ...]
    evidence: tuple[str, ...]
    failure: ProbeFailure | None


class ProbeAdapter(Protocol):
    adapter_id: str
    scenario_id: str
    schema_version: int
    @property
    def supported_cpu_modes(self) -> tuple[str, ...]: ...
    def build_argv(self, request: RunRequest) -> tuple[str, ...]: ...
    def parse_output(
        self, *, stdout: str, stderr: str, exit_code: int, timed_out: bool
    ) -> ProbeOutcome: ...
    def known_failure_modes(self) -> tuple[ProbeFailureMode, ...]: ...


# arm64_probe/execution/runner.py
@dataclass(frozen=True)
class ToolchainEvidence:
    python_version: str
    uv_version: str
    cc: str
    host_os: str


# arm64_probe/domain/models.py  (additive; existing fields preserved)
@dataclass(frozen=True)
class RunResult:
    run_id: str
    plan: Plan
    samples: tuple[Sample, ...]
    summary: tuple[tuple[str, JsonScalar], ...]
    environment: tuple[tuple[str, JsonScalar], ...]
    schema_version: int = 2
    prior_run_id: str | None = None
    resume_kind: str | None = None
```

Apply order：`linux.cpufreq`、`linux.hugepage`、`linux.transparent-hugepage`（复用 Phase 2 `CONTROLLER_ORDER`，保持不变）。

Controller IDs（复用 Phase 2，保持不变）：
`linux.cpufreq`、`linux.hugepage`、`linux.transparent-hugepage`。Phase 3 不新增 controller。

## Public Behavior Contract

详细设计中的 §3 冻结以下形式。本计划中的 contract tests 会断言每一种。

```text
# Spec §3.2
probe run cache-latency/l1-latency
probe run cache-latency/l2-latency cache-latency/dram-latency
probe run migration-latency/cross-cluster
probe run cache-latency
probe run --profile smoke
probe run --case <stable-case-id>
probe run --platform gb10 --profile baseline --output-dir /tmp/runs
probe run --platform gb10 --profile smoke --allow-mutation
probe run --platform gb10 --profile smoke --case-timeout 30

# Spec §3.3
probe resume --run <run-result-path>
probe resume --run <run-result-path> --output-dir /tmp/runs
probe resume --run <run-result-path> --allow-mutation
```

Exit codes：`0` success；`2` usage；`3` config；`4` capability；`5` planning；`10` host inspection；`11` mutation authorization；`12` apply/work failure（restoration succeeded）；`13` restore failure；`14` active lock or unfinished journal；**15 probe execution**；**16 run result**。对于任何 failed case 的 invocation（status `15`），始终写入 partial `RunResult`；restore failure 具有优先级（`13`）。

## Phase 3 Acceptance Criteria（映射到 plan tasks）

这些 criteria 是 handoff 的 AC1–AC9，针对 implementer 重新陈述，并给出证明每项的 test path。每个 criterion 都必须由自动化证据关闭，而不是 narrative assertion。

| AC | Proven by | Covered in |
|---|---|---|
| AC1 Normalized probe contract | `tests/contract/test_probe_adapters.py`，`tests/unit/test_characterization_probes.py`，`tests/unit/test_chase_pmu_adapter.py`（及 sibling tests） | Task 14，Task 15 |
| AC2 Selection and composition | `tests/contract/test_run_plan_equivalence.py`，`tests/contract/test_cli_run.py`（selection + `--case`） | Task 18，Task 19 |
| AC3 Transactional execution | `tests/unit/test_runner.py`，`tests/integration/test_phase3_signal_restore.py` | Task 17 |
| AC4 Structured results and provenance | `tests/unit/test_result_store.py`，`tests/contract/test_public_schemas.py`（扩展），`tests/unit/test_characterization_probes.py` | Task 15，Task 16，Task 20 |
| AC5 Resume and exact rerun | `tests/unit/test_resume.py`，`tests/contract/test_cli_resume.py`，`tests/integration/test_phase3_resume_workflow.py` | Task 19 |
| AC6 Stable CLI and Makefile | `tests/contract/test_cli_run.py`，`tests/contract/test_cli_resume.py`，`tests/test_makefile_contract.py`（扩展） | Task 18，Task 19，Task 20 |
| AC7 Compatibility and boundaries | `tests/contract/test_phase2_acceptance.py`（扩展），`tests/contract/test_repository_policy.py`（扩展），`tests/contract/test_public_schemas.py`（扩展） | Task 20 |
| AC8 Minimal smoke workflow | `tests/integration/test_phase3_smoke_workflow.py`，`tests/integration/test_phase3_fixture_workflow.py`，`tests/test_makefile_contract.py`（扩展），live `make smoke` target | Task 20 |
| AC9 GB10 Gate 1 runbook | 本计划 “Phase 3 Completion Gate” §1.1 中的 runbook subsection | Task 20 |

## AC → Task → Test map

| AC | Task that closes it | Verifying test(s) |
|---|---|---|
| AC1 | Task 14（characterization），Task 15（adapters） | `test_characterization_probes.py`，`test_chase_pmu_adapter.py`，`test_evict_slc_adapter.py`，`test_chase_migrate_adapter.py`，`test_probe_adapters.py` |
| AC2 | Task 18（runner + `probe run`） | `test_run_plan_equivalence.py`，`test_cli_run.py`，`test_runner.py`（selection-by-profile 和 exact-case-id subsets） |
| AC3 | Task 17（runner / coordinator integration） | `test_runner.py`，`test_phase3_signal_restore.py` |
| AC4 | Task 16（result store + serialization） | `test_result_store.py`，`test_public_schemas.py`（扩展），`test_characterization_probes.py`（sample round-trip） |
| AC5 | Task 19（resume + `probe resume`） | `test_resume.py`，`test_cli_resume.py`，`test_phase3_resume_workflow.py` |
| AC6 | Task 20（Makefile wrappers + extended CLI） | `test_cli_run.py`，`test_cli_resume.py`，`test_makefile_contract.py`（扩展） |
| AC7 | Task 20（boundary tests） | `test_phase2_acceptance.py`（扩展），`test_repository_policy.py`（扩展），`test_public_schemas.py`（扩展） |
| AC8 | Task 20（smoke workflow） | `test_phase3_smoke_workflow.py`，`test_phase3_fixture_workflow.py`，`test_makefile_contract.py`（扩展） |
| AC9 | Task 20（runbook） | Phase 3 Completion Gate 中的 runbook subsection 由 architect review |

## Test Taxonomy

- **Unit**（`tests/unit/`）：argument normalization、output parsing、process outcomes、result assembly/storage、resume diffing、phase grouping、schema-version compatibility。
- **Contract**（`tests/contract/`）：CLI examples、schemas、exit codes、plan/run equivalence、capability-driven boundaries、frozen paths、uv/Makefile rules、exit-code ladder。
- **Integration**（`tests/integration/`）：fake process executor + fake backend + real coordinator；全量 failure/signal/timeout restoration；result persistence and resume。
- **Host validation**（在 Mac 上运行；未来 Linux ARM64）：build、fixture smoke、`probe doctor` round-trip。

所有行为变更使用 TDD。每个外部边界必须进行 fault-injection tests：process start、output parse、sample persistence、journal transition、work callback、restoration 和 resume persistence。

## Per-Task Gate

每个 focused commit 前执行：

```sh
uv run --no-sync python -m unittest <focused-modules> -v
make check
make legacy-check
git diff --check
git status --short
```

每个 commit 拥有一个内聚行为及其 tests。不要把 probe normalization、runner orchestration、resume 和 acceptance closure 合并到一个 commit 中。

## Phase Completion Gate

最终 architect review 前执行（对应 handoff §5 “Phase Completion Gate”）：

```sh
make phase3-check
make check
make legacy-check
make build
make smoke
./probe --help
./probe help run
./probe help resume
git diff --check
git status --short
git diff --name-status main...HEAD
```

implementation agents 必须提供一个 **AC1–AC9 evidence matrix**，其中包含 criterion、proving test/command、result 和 artifact path。任何 criterion 都不得仅通过 narrative assertion 关闭。

### 1. GB10 Gate 1 runbook（仅在 AC1–AC8 关闭后）

AC9 是一个 **runbook**，不是自动化测试。implementer 在
`docs/superpowers/handoffs/2026-06-15-phase3-gate1-runbook.md`
中生成 Markdown runbook（Task 20 中添加，**与 Task 20 Step 11 中的 acceptance evidence 一起 commit**），包含用户将在 GB10 上按以下顺序执行的精确步骤：

1. 记录 commit SHA，并确认 `git status` 干净。
2. 捕获 pinned toolchain evidence：
   `uv run --no-sync python -V`、`uv --version`、`cc --version`、
   `uname -srm`。
3. 运行 `make build`；记录生成的 binaries 和
   `file build/bin/chase_pmu` 等。
4. 运行 `make phase3-check`；记录最终 test count 和 status。
5. 运行 `./probe doctor -o json`；保存 artifact。
6. 运行 `./probe plan --platform gb10 --profile smoke -o
   json`；保存 artifact。
7. 运行
   `./probe run --platform gb10 --profile smoke --allow-mutation
   --output-dir results/gate1-runs`；记录生成的
   `RunResult` JSON path 和 journal path。
8. 再次运行 `./probe doctor -o json`；确认
   `journals` 为空，并且刚写入的 journal 的
   `restoration_status` 为 `succeeded`。
9. 不要仅为了 Gate 1 在 GB10 上添加 resume / rerun invocations；
   Mac / Linux ARM64 上的 AC5 fixture evidence 已经证明它们。

runbook 是 implementer 对 AC9 唯一需要交付的内容。Gate 1 execution 本身是用户职责；只有用户宣布 `GB10 Gate 1 is ready to run`。

---

## Batch 1：Characterization + Probe Adapters

### Task 14：Capture and Lock the Current Probe Output

**Files:**
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/warm-32KiB.stdout.txt`
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/warm-32KiB.stderr.txt`
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/cold-64MiB.stdout.txt`
- Create: `tests/fixtures/probe_output/chase_pmu_v2.7.3/cold-64MiB.stderr.txt`
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/quiet-default.stdout.txt`（empty）
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/quiet-default.stderr.txt`
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/verbose.stdout.txt`
- Create: `tests/fixtures/probe_output/evict_slc_v1.2/verbose.stderr.txt`
- Create: `tests/fixtures/probe_output/chase_migrate_v1.0/cross-cluster.stdout.txt`
- Create: `tests/fixtures/probe_output/chase_migrate_v1.0/cross-cluster.stderr.txt`
- Create: `tests/unit/test_characterization_probes.py`
- Create: `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md`（code-handoff only；不属于 spec/plan acceptance）

- [ ] **Step 1：编写失败的 characterization tests**

  在 `tests/unit/test_characterization_probes.py` 中，对每个 probe 和 capture variant，断言预期 fixture file 存在，并断言当前 C probe 的 textual output 与 recorded baseline 匹配。每个 test 必须读取 fixture 并断言 byte-for-byte equality；这是 handoff 要求的 behavior-pinning layer。示例：

  ```python
  def test_chase_pmu_warm_32kib_output_pinned(self):
      fixture = (FIXTURES / "chase_pmu_v2.7.3"
                 / "warm-32KiB.stdout.txt").read_text()
      self.assertIn("=== chase_pmu v2.7.3 ===", fixture)
      self.assertIn(">>> latency =", fixture)
      self.assertRegex(fixture, r"elapsed=\d+ ns")
  ```

  将与 live probe output 对比的 assertion 标记为
  `# TODO(phase-3): populate live fixtures via deferred
  capture script`。

- [ ] **Step 2：运行 focused tests 并确认失败**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_characterization_probes -v
  ```

  预期：FAIL（无 fixtures，无 module）。

- [ ] **Step 3：在 code-handoff 中记录 capture procedure**

  创建
  `docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md`，
  其中包含填充每个 fixture file 所需的精确
  `subprocess.run(argv, shell=False, text=True,
  capture_output=True, timeout=60)` 调用。`make build`
  后的工作目录是 `build/bin/`。handoff 不交付 in-tree capture script；理由见 spec §8.4。handoff document 仅为信息性文档，不属于 contract tests。

- [ ] **Step 4：为 offline CI hand-roll fixtures**

  Characterization tests 必须在 Mac 和 CI 上不运行 C probes 即可通过。通过从现有
  `runner/run_pmu*.sh` 调用输出中复制 representative output，或在用户授权时通过一次性
  `make build` + 手动 probe invocation，来 hand-roll fixtures。每个 fixture 都是 stdout 或 stderr 的 byte-for-byte snapshot；tests 只断言 structural anchors 的存在，例如 `=== chase_pmu v2.7.3 ===`、`>>>` markers、`lat=` substrings。

- [ ] **Step 5：运行 tests 并 commit**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_characterization_probes -v
  make check
  make legacy-check
  git diff --check
  git add tests/fixtures/probe_output tests/unit/test_characterization_probes.py
  git add docs/superpowers/handoffs/2026-06-15-phase3-fixture-capture.md
  git commit -m "Pin current probe textual output as characterization fixtures"
  ```

  预期：focused tests 和 Phase 1+2 suite（241 + N 个 characterization tests）通过。

### Task 15：Implement the Three Probe Adapters and Their Public Protocol

**Files:**
- Create: `arm64_probe/execution/__init__.py`
- Create: `arm64_probe/execution/adapters/__init__.py`
- Create: `arm64_probe/execution/adapters/base.py`
- Create: `arm64_probe/execution/adapters/chase_pmu.py`
- Create: `arm64_probe/execution/adapters/evict_slc.py`
- Create: `arm64_probe/execution/adapters/chase_migrate.py`
- Create: `arm64_probe/execution/adapters/legacy_wrapper.py`（doc-only stub）
- Create: `tests/unit/test_chase_pmu_adapter.py`
- Create: `tests/unit/test_evict_slc_adapter.py`
- Create: `tests/unit/test_chase_migrate_adapter.py`
- Create: `tests/contract/test_probe_adapters.py`
- Create: `tests/support/fake_adapter.py`

- [ ] **Step 1：编写失败的 adapter tests**

  对每个 adapter：

  - `build_argv` test：断言 representative request dataclasses 对应的精确 argv tuples。
  - `parse_output` test：喂入 captured fixture strings（Task 14），断言 `status == "ok"` 和精确 `metrics` tuple。
  - `parse_output` failure tests：empty stdout、nonzero exit、`timed_out=True`、malformed `>>>` line。
  - `supported_cpu_modes` test：断言返回的 tuple 与
    `configs/experiments/*.json` 中 scenario 的 `cpu_mode` 匹配。

- [ ] **Step 2：运行 focused tests 并确认失败**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_chase_pmu_adapter -v
  ```

  预期：FAIL（无 module）。

- [ ] **Step 3：实现 `ProbeAdapter` Protocol 和 base dataclasses**

  在 `arm64_probe/execution/adapters/base.py` 中：

  - `ProbeFailure` 和 `ProbeFailureMode`（frozen dataclasses）。
  - `ProbeOutcome`（frozen dataclass，包含 `status`、`metrics`、`evidence`、`failure`）。
  - `ProbeAdapter` Protocol，包含 public type contract 中的四个成员。
  - 一个将 `scenario_id` 映射到 `ProbeAdapter` 的 `AdapterRegistry`。在 `arm64_probe/execution/adapters/__init__.py` 中 module import 时填充。

- [ ] **Step 4：实现 `ChasePmuAdapter`**

  `arm64_probe/execution/adapters/chase_pmu.py`：

  - `ChasePmuArgs(size_kb: int, warm: int, force_rounds: int = 0,
    seed: int = 0, clflush: int = 0, hugepage: int = 0,
    cpu: int | None = None)`（frozen）。
  - `ChasePmuAdapter`，其 `scenario_id` 匹配 `cache-latency.*` scenarios。
  - `build_argv`：当 `cpu is not None` 时，以
    `("taskset", "-c", str(cpu))` 作为 prefix。否则，probe binary argv 精确等于 `chase_pmu` 期望的七个 positional 参数。
  - `parse_output`：从 stdout 中 regex 提取 `elapsed=`、`accesses=`、`latency =`。如果 `warm=0 && force_rounds=1`，解析 `src_latency` 和 `migrate_latency` fallback 到 cold-DRAM semantic。非零退出或缺失 `>>>` marker 时，返回 `status="error"`，并设置
    `failure=ProbeFailure("exit", ...)` 或 `ProbeFailure("parse", ...)`。

- [ ] **Step 5：实现 `EvictSlcAdapter`**

  `arm64_probe/execution/adapters/evict_slc.py`：

  - 注册到 synthetic `evict-slc.setup` scenario。runner 不会从
    `probe run --profile smoke` dispatch 到它；它是为了完整性和未来 direct invocation 而存在。`ChasePmuAdapter` cold-DRAM path **不**自行调用 `evict_slc`；integration plan（Task 17）在需要时安排顺序。
  - `EvictSlcArgs(evict_mb: int = 64, seed: int = 42,
    seq: bool = False, random: bool = True, touch_init:
    bool = True, verbose: bool = False)`。
  - `build_argv`：默认发出 long-form flags；
    positional `[evict_mb] [seed]` 用于 backward-compat。
  - `parse_output`：在 `--quiet`（默认）下 stdout 为空；adapter 从 stderr 中 regex 提取 `approx_bw`、`evict_ms`、`touch_ms`。在 `--verbose` 下，adapter 提取同样信息以及 runtime header。

- [ ] **Step 6：实现 `ChaseMigrateAdapter`**

  `arm64_probe/execution/adapters/chase_migrate.py`：

  - `ChaseMigrateArgs(src_cpu: int, dst_cpu: int,
    size_kb: int, warm_src: int = 5, measure_rounds: int =
    1, measure_src: bool = True, seed: int = 42,
    hugepage: bool = True, strict_hugepage: bool = True,
    sleep_us: int = 0, label: str | None = None)`。
  - `scenario_id` 匹配 `migration-latency.*`。adapter 的
    `build_argv` 与现有 C probe 的 `getopt_long` 调用一致。runner 通过 `Plan` 的 `Case` selection 传入正确的 `cpu_mode`（`pair-same-core`、`pair-same-cluster`、`pair-cross-cluster`），但 argv 本身是 platform-agnostic。
  - `parse_output`：提取三个 `>>>` markers（`src_latency`、`migrate_latency`、`migrate_penalty`）。当 `cpu_before != src_cpu` 或 `cpu_after != dst_cpu` 时，返回
    `status="error", failure=ProbeFailure("parse",
    "affinity_lost")`。

- [ ] **Step 7：实现 doc-only `legacy_wrapper.py`**

  `arm64_probe/execution/adapters/legacy_wrapper.py` 是一个单一的
  `@dataclass(frozen=True) class LegacyWrapperAdapter`，其
  `parse_output` 抛出
  `NotImplementedError("legacy wrapper is documentation only
  for Phase 3")`。class docstring 说明：未来 task 可以将其注册到 synthetic
  `legacy.run-pmu-v2.7.7` scenario，用于调用
  `runner/run_pmu_v2.7.7.sh` 来保持行为；Phase 3 happy path 不注册它。

- [ ] **Step 8：运行 tests 并 commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.unit.test_chase_pmu_adapter \
    tests.unit.test_evict_slc_adapter \
    tests.unit.test_chase_migrate_adapter \
    tests.contract.test_probe_adapters -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/execution tests/unit/test_chase_pmu_adapter.py \
    tests/unit/test_evict_slc_adapter.py \
    tests/unit/test_chase_migrate_adapter.py \
    tests/contract/test_probe_adapters.py \
    tests/support/fake_adapter.py
  git commit -m "Add normalized probe adapters behind ProbeAdapter protocol"
  ```

  预期：所有 focused tests 通过；AC1 关闭。

## Batch 2：Result Persistence and Runner

### Task 16：Add the Atomic `RunResultStore` and Bump `RunResult` Schema to v2

**Files:**
- Modify: `arm64_probe/errors.py`（添加 `PROBE_EXECUTION = 15`、`RUN_RESULT = 16`）
- Modify: `arm64_probe/domain/models.py`（扩展 `RunResult`，添加 `prior_run_id`、`resume_kind`；默认均为 `None`；设置 `schema_version` 默认值为 `2`）
- Modify: `arm64_probe/serialization/model_json.py`（为新字段和 `ToolchainEvidence` 扩展 `to_data`）
- Modify: `schemas/sample.schema.json`（添加 `toolchain` object）
- Modify: `schemas/run-result.schema.json`（添加 `summary.*` 和 `environment.toolchain`）
- Create: `arm64_probe/execution/result_store.py`
- Create: `tests/unit/test_result_store.py`
- Create: `tests/support/fake_coordinator.py`

- [ ] **Step 1：编写失败的 `ExitCode` 和 schema contract tests**

  在 `tests/contract/test_exit_codes.py` 中：

  ```python
  from arm64_probe.errors import ExitCode

  class ExitCodeContractTests(unittest.TestCase):
      def test_phase_3_codes_exist(self):
          self.assertEqual(ExitCode.PROBE_EXECUTION, 15)
          self.assertEqual(ExitCode.RUN_RESULT, 16)
  ```

  在 `tests/contract/test_public_schemas.py` 中扩展新 keys，断言
  `run-result.schema.json` 要求
  `summary.case_definitions_signature`、
  `summary.repository_commit`、`summary.dirty_tree`、
  `summary.toolchain`、`summary.prior_run_id`、
  `summary.resume_kind`、`environment.toolchain`。

- [ ] **Step 2：运行 focused tests 并确认失败**

  ```sh
  uv run --no-sync python -m unittest tests.contract.test_exit_codes -v
  uv run --no-sync python -m unittest tests.contract.test_public_schemas -v
  ```

  预期：FAIL（无新 codes，无新 schema fields）。

- [ ] **Step 3：添加 `ExitCode` members 并扩展 dataclass**

  在 `arm64_probe/errors.py` 中：

  ```python
  class ExitCode(IntEnum):
      ...
      ENVIRONMENT_BUSY = 14
      PROBE_EXECUTION = 15   # probe launch, timeout, signal, nonzero exit, malformed output
      RUN_RESULT = 16        # run-result read, validation, compatibility, or persistence failure
  ```

  在 `arm64_probe/domain/models.py` 中扩展 `RunResult`（保持现有 field order，以便 tests 中任何 positional construction 仍可工作）：

  ```python
  @dataclass(frozen=True)
  class RunResult:
      run_id: str
      plan: Plan
      samples: tuple[Sample, ...]
      summary: tuple[tuple[str, JsonScalar], ...]
      environment: tuple[tuple[str, JsonScalar], ...]
      schema_version: int = 2
      prior_run_id: str | None = None
      resume_kind: str | None = None
  ```

  如果尚未存在，则添加 `from __future__ import annotations` import。

- [ ] **Step 4：为新字段扩展 `to_data`**

  在 `arm64_probe/serialization/model_json.py` 中，`RunResult` branch 必须发出 `schema_version`、`prior_run_id` 和 `resume_kind`（后两者未设置时为 `None`）。添加 `to_data_toolchain_evidence` branch 和 `to_data_sample_toolchain` branch。

- [ ] **Step 5：扩展 public schemas**

  `schemas/sample.schema.json`：添加 optional `toolchain` object（可复用 sub-schema；保持 `additionalProperties: false`）。新字段是 **optional**；现有 required-key set 不变。

  `schemas/run-result.schema.json`：添加 optional
  `summary.case_definitions_signature`、
  `summary.repository_commit`、`summary.dirty_tree`、
  `summary.toolchain`、`summary.prior_run_id`、
  `summary.resume_kind`、`environment.toolchain`。全部 optional。保持 `additionalProperties: false`。

  `RunResult` 的 `schema_version` field 现在是 public contract 的一部分；将 contract test 中的 schema docstring 更新为 `2`。

- [ ] **Step 6：编写失败的 `RunResultStore` tests**

  在 `tests/unit/test_result_store.py` 中：

  - `test_write_local_creates_atomic_file` —— 断言 temp + replace pattern。
  - `test_read_rejects_outside_root` —— symlink parent test。
  - `test_read_rejects_oversize` —— `MAX_RESULT_BYTES = 1 MiB`。
  - `test_validate_compatibility_rejects_schema_version_mismatch`
    —— `schema_version=1` prior + current `RunResult` 抛出 `ProbeError(16)`。
  - `test_validate_compatibility_rejects_case_definitions_signature_mismatch`。
  - `test_validate_compatibility_rejects_repository_id_mismatch`。
  - `test_validate_compatibility_rejects_platform_id_mismatch`。

- [ ] **Step 7：实现 `RunResultStore`**

  在 `arm64_probe/execution/result_store.py` 中：

  - 复用 `JournalStore._atomic_write` pattern（`arm64_probe/environment/journal.py:338`）：写入
    `.<run_id>.<uuid>.tmp`、`fsync`、`os.replace`、parent `fsync`、owner/mode check。
  - `validate_compatibility` 检查
    `schema_version`、`platform_id`、`repository_id`、
    `repository_commit` 和 `case_definitions_signature`（基于 `Plan` 计算）。
  - `MAX_RESULT_BYTES = 1024 * 1024`。
  - `read` 校验 `schema_version == 2`。

- [ ] **Step 8：运行 tests 并 commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.contract.test_exit_codes \
    tests.contract.test_public_schemas \
    tests.unit.test_result_store -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/errors.py arm64_probe/domain/models.py \
    arm64_probe/serialization/model_json.py \
    schemas/sample.schema.json schemas/run-result.schema.json \
    arm64_probe/execution/result_store.py \
    tests/unit/test_result_store.py \
    tests/contract/test_exit_codes.py
  git commit -m "Add RunResult schema v2 and atomic RunResultStore"
  ```

  预期：AC4 部分关闭（storage + schema）。runner 在 Task 17 中填充新字段。

### Task 17：Implement the `Runner` and the Fake Coordinator

**Files:**
- Create: `arm64_probe/execution/runner.py`
- Create: `tests/support/fake_coordinator.py`（或在单独文件冗余时扩展 `tests/support/fake_controllers.py` —— 计划为清晰起见指定新文件）
- Create: `tests/support/executor_recorder.py`
- Create: `tests/unit/test_runner.py`
- Modify: `tests/support/fake_controllers.py`（如 runner 需要 frozen observer callback，则扩展 `FakeController.events`）

- [ ] **Step 1：编写失败的 runner tests**

  在 `tests/unit/test_runner.py` 中：

  - `test_run_with_no_controllers_runs_work_immediately` —— 当 resolved `Plan` 没有 cases 时，runner 返回 empty `RunResult`，并且不调用 `EnvironmentCoordinator.execute`。对应 Phase 2 的 “no requests” branch。
  - `test_run_groups_cases_by_environment_phase` —— 一个具有两个 phases 的 `Plan` 产生两次
    `EnvironmentCoordinator.execute` 调用；断言每个调用的 `requests` tuple。
  - `test_run_propagates_environment_apply_exit_code_12`
    —— 当 coordinator 抛出 `ENVIRONMENT_APPLY` 时，runner 原样重新抛出相同 code；partial `RunResult` 写入且 `complete=False`。
  - `test_run_propagates_environment_restore_exit_code_13`。
  - `test_run_returns_propagates_environment_busy_14`。
  - `test_run_writes_partial_result_on_case_failure_15`
    —— runner 将 per-case adapter exceptions 包装为
    `ProbeError(PROBE_EXECUTION)`；partial `RunResult` 将 failed case 标为 `status: "error"`。
  - `test_run_uses_default_60s_case_timeout` —— 未给出 `--case-timeout` 时，runner 将 `timeout=60` 传给 injected `CommandExecutor`。
  - `test_run_persists_run_result_atomically` —— `RunResultStore.write_local` 每次 `probe run` 只调用一次；磁盘文件与 `to_data(result)` 匹配。
  - `test_run_records_repository_commit_dirty_tree_toolchain`
    —— 断言 `summary` map 包含 `repository_commit`、`dirty_tree` 和 `toolchain` keys，且类型符合预期。
  - `test_run_uses_injected_command_executor_not_subprocess`
    —— runner **不**直接调用 `subprocess`；它通过 injected `CommandExecutor` 路由。

- [ ] **Step 2：运行 focused tests 并确认失败**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_runner -v
  ```

  预期：FAIL（无 module）。

- [ ] **Step 3：实现 `Runner` 和 `ToolchainEvidence`**

  在 `arm64_probe/execution/runner.py` 中：

  - `ToolchainEvidence` frozen dataclass，字段为
    `python_version: str`、`uv_version: str`、`cc: str`、`host_os: str`。在 runner instantiation 时通过
    `subprocess.run(("uv", "--version"),
    capture_output=True, text=True, check=False,
    shell=False)` 等构造；任何 failure 均 fallback 到 `"unknown"`。
  - `RunRequest`（frozen），封装 `case`、`platform_id`、
    `backend`、`allow_mutation`。不对外使用；runner 内部构建。
  - `Runner.__init__(self, adapter_registry,
    store, *, executor: CommandExecutor | None = None,
    case_timeout_seconds: int = 60)`。`case_timeout_seconds` 是 runner 传给 `executor.run(argv, timeout=...)` 的默认值。可在构造时 override（CLI flags 转换为 constructor args）。
  - `Runner.run(plan, platform_id, backend,
    allow_mutation, output_dir, run_id=None,
    toolchain_evidence=None, started_at=None)`
    遵循 design §4.2 和 §5 的算法。
  - 传给 `EnvironmentCoordinator.execute` 的 runner work callback 遍历 phase 中的 cases，根据每个 `case.scenario_id` 查找 `ProbeAdapter`，构建 argv，调用
    `self._executor.run(argv, timeout=self._case_timeout)`，并把 `(stdout, stderr, exit_code, timed_out)` 传给 adapter 的 `parse_output`。生成的 `Sample` objects append 到 closure-captured list。发生 `subprocess.TimeoutExpired` 时设置 `timed_out` flag；runner 捕获它并按 spec §5.4 合成 `ProbeFailure`。
  - 除非 adapter 抛出异常，否则 runner 自身不抛出 `ProbeError(15)`；per-case failure path 是 `status: "error"`，不是 coordinator abort。
  - `RunResult` 在 coordinator 返回后写入；对于 partial runs，runner 仍以 `complete=False` 调用 `write_local`。

- [ ] **Step 4：实现 `tests/support/fake_coordinator.py`**

  一个 recording fake，返回 configurable `EnvironmentJournal`，并可选抛出 `ProbeError`。角色类似
  `tests/support/fake_controllers.py:FakeController`。

- [ ] **Step 5：实现 `tests/support/executor_recorder.py`**

  实现 `arm64_probe/backends/io.py:19` 中的现有 `CommandExecutor` Protocol。维护一个 `argv → CompletedProcess` mappings 队列。Tests push responses；runner consume。recorder 暴露其收到的 `argv`，包括 `timeout` 参数，以便 `test_run_uses_default_60s_case_timeout` 断言。

- [ ] **Step 6：运行 tests 并 commit**

  ```sh
  uv run --no-sync python -m unittest tests.unit.test_runner -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/execution/runner.py tests/unit/test_runner.py \
    tests/support/fake_coordinator.py \
    tests/support/executor_recorder.py
  git commit -m "Add Runner that groups cases by environment phase"
  ```

  预期：focused tests 通过；AC3 关闭（runner 侧）；AC4 关闭（summary fields）。

### Task 18：Wire the `probe run` CLI Surface

**Files:**
- Modify: `arm64_probe/cli/parser.py`（添加 `run` subcommand；扩展 `COMMANDS`）
- Modify: `arm64_probe/cli/main.py`（dispatch `run`）
- Modify: `arm64_probe/cli/render.py`（添加 `render_run`，包含 table 和 JSON branches）
- Create: `tests/contract/test_cli_run.py`
- Create: `tests/contract/test_run_plan_equivalence.py`

- [ ] **Step 1：编写失败的 CLI tests**

  在 `tests/contract/test_cli_run.py` 中，覆盖 spec §3.2 的每个 example 以及 failure paths：

  - `probe run cache-latency/l1-latency` —— exit 0；JSON output 包含一个 `RunResult`，其中有一个或多个 `Sample` records，且其 `case_id` 匹配 scenario。
  - `probe run --profile smoke` —— exit 0；JSON output 的 `RunResult.plan.cases` 匹配 smoke profile 的 selections。
  - `probe run --case <stable-case-id>` —— exit 0；result 中正好一个 case。
  - `probe run --case-timeout 30` —— runner 以 `case_timeout_seconds=30` 构造；`executor.run` 以 `timeout=30` 被调用。通过 `ExecutorRecorder` 断言。
  - `probe run` 无 target 且无 `--profile` —— exit 2（usage）。
  - `probe run --case bogus` —— exit 2（usage）。
  - `probe run --platform gb10 --profile smoke` 缺少 `--allow-mutation` 且 profile 需要 mutation —— exit 11。
  - `probe run` 无 `--output-dir` —— exit 0，并写入 `results/runs/`（被 git 忽略；test 将 workdir override 到 tempdir）。
  - `probe run -o json` —— JSON output 是 `to_data(result)`。
  - `probe run -o table` —— table output 包含 `CASE`、`STATUS`、`SAMPLES`、`METRIC` columns。

  在 `tests/contract/test_run_plan_equivalence.py` 中：

  - `test_run_and_plan_emit_same_case_set` —— 对 smoke profile 中的每种 selection，`probe plan` 和 `probe run`（table output）发出的 case IDs 相等。
  - `test_run_and_plan_emit_same_parameter_values` —— `samples`、`working-set`、`page-policy` 匹配。

- [ ] **Step 2：运行 focused tests 并确认失败**

  ```sh
  uv run --no-sync python -m unittest \
    tests.contract.test_cli_run \
    tests.contract.test_run_plan_equivalence -v
  ```

  预期：FAIL（无 subcommand，无 renderer）。

- [ ] **Step 3：将 `run` subcommand 添加到 parser**

  在 `arm64_probe/cli/parser.py` 中：

  - 将 `COMMANDS` 扩展为 `("list", "show", "plan", "doctor",
    "restore", "run", "resume")`。
  - 添加 `run_parser`，包含 spec §3.2 中的 args，
    包括新的 `--case-timeout <seconds>` 和
    `--no-case-timeout` flags。`--no-case-timeout` 是将值存为 `0` 的 argparse action；runner 将 `0` 映射为 “no timeout”（`executor.run(argv, timeout=None)`）。
  - 通过 argparse `default` 拒绝重复 `--platform`，并记录事实上的 single-occurrence 行为。

- [ ] **Step 4：在 `main.py` 中添加 dispatch**

  在 `arm64_probe/cli/main.py` 中：

  - 与 `plan` 完全一致地解析 platform（`_resolve_platform`）。
  - 构建 `Planner` 并调用
    `Planner(catalog).plan(_plan_request(args))`。
  - 以 default registry 和 `RunResultStore(root=output_dir_default)` 构造 `Runner`。`output_dir` 默认是 `results/runs/`。生产路径下 runner 注入 `LocalCommandExecutor`；tests 注入 `ExecutorRecorder`。
  - 从 parsed arguments 传递 `case_timeout_seconds`：
    `--case-timeout N` → `N`，
    `--no-case-timeout` → `0`（映射为 `None`），
    默认 `60`。
  - 调用 `runner.run(...)`。捕获 `ProbeError` 并路由到现有 structured-error path。
  - 打印 `render_run(result, args.output)`。

- [ ] **Step 5：实现 `render_run`**

  在 `arm64_probe/cli/render.py` 中：

  - JSON branch：`dump_json(to_data(result))`。
  - Table branch：case ID、status、samples（count）、
    primary metric（例如 `latency_ns` 或
    `migrate_penalty_ns`）。精确 column set 由 `test_cli_run.py` 捕获；本 task 不进行临时 schema 设计。

- [ ] **Step 6：运行 tests 并 commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.contract.test_cli_run \
    tests.contract.test_run_plan_equivalence -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/cli/parser.py arm64_probe/cli/main.py \
    arm64_probe/cli/render.py \
    tests/contract/test_cli_run.py \
    tests/contract/test_run_plan_equivalence.py
  git commit -m "Add probe run CLI with plan equivalence"
  ```

  预期：focused tests 通过；AC2 关闭；AC6 部分关闭（CLI 侧）。

### Task 19：Implement `probe resume` and the Resume Service

**Files:**
- Create: `arm64_probe/execution/resume.py`
- Create: `tests/unit/test_resume.py`
- Create: `tests/contract/test_cli_resume.py`
- Create: `tests/integration/test_phase3_resume_workflow.py`

- [ ] **Step 1：编写失败的 resume tests**

  在 `tests/unit/test_resume.py` 中：

  - `test_resume_runs_only_error_cases` —— prior `RunResult` 中有两个 `status: "ok"` cases 和一个
    `status: "error"` case；resume 产生新的 `RunResult`，其中有 **两个** samples（一个 carry 的 `ok`，一个 fresh re-run）；carry 的 case 保留其原始 `Sample.run_id`；re-run case 使用新的 `Sample.run_id`。
  - `test_resume_drops_skipped_cases` —— prior
    `RunResult` 中有一个 `status: "skipped"` case；resume 产生新的 `RunResult`，其中 **零** samples（skipped case 既不 carry，也不 re-execute）。`summary["skipped_cases"]` 记录被 dropped 的 case IDs。
  - `test_resume_is_idempotent_on_fully_successful_prior`
    —— repeated resume 返回 `0`，并写入新的 `RunResult`，其中 `resume_kind: "no-op"`。
  - `test_resume_rejects_schema_version_mismatch` —— exit
    16；abort 发生在任何 case re-execute **之前**（通过统计 `executor.run` 调用次数断言）。
  - `test_resume_rejects_case_definitions_signature_mismatch`
    —— exit 16。
  - `test_resume_rejects_platform_id_mismatch` —— exit 16。
  - `test_resume_rejects_repository_id_mismatch` —— exit 16。

  在 `tests/contract/test_cli_resume.py` 中：

  - `probe resume --run <path>` —— exit 0；新
    `RunResult` JSON 包含 `prior_run_id` 和
    `resume_kind: "missing"` 或 `"failed"`。
  - `probe resume --run <path>` 指向不存在路径 —— exit 16。
  - `probe resume --run <path>` 指向 malformed JSON file
    —— exit 16。
  - `probe resume --run <path>` 指向具有错误
    `repository_id` 的 JSON file —— exit 16。
  - 当 underlying plan 会 mutate host 时，`probe resume` 要求 `--allow-mutation`；缺失 → 11。

  在 `tests/integration/test_phase3_resume_workflow.py` 中：

  - End-to-end：`FakeBackend` + `FakeController` +
    `FakeAdapter` + `ExecutorRecorder`。第一次 run 产生一个含 one failed case 的 `RunResult`；第二次 run（`probe resume`）只重新执行该 case；两次 runs 都落到同一个 `output_dir` 下。

- [ ] **Step 2：运行 focused tests 并确认失败**

  ```sh
  uv run --no-sync python -m unittest \
    tests.unit.test_resume \
    tests.contract.test_cli_resume \
    tests.integration.test_phase3_resume_workflow -v
  ```

  预期：FAIL（无 module）。

- [ ] **Step 3：实现 `ResumeService`**

  在 `arm64_probe/execution/resume.py` 中：

  - `ResumeService(store: RunResultStore, runner: Runner)`。
  - `resume(prior_path: Path, *, plan: Plan, platform_id:
    str, backend: HostBackend, allow_mutation: bool,
    output_dir: Path, case_timeout_seconds: int = 60) -> RunResult`。
  - `validate_compatibility(prior, plan)` 调用
    `RunResultStore.validate_compatibility`；任何
    `ProbeError(16)` 原样传播。**这发生在任何 re-execution 之前**；见 test
    `test_resume_rejects_schema_version_mismatch`。
  - 按 spec §5.5 执行 sample diff logic：`status: "ok"` 的 cases carry over；`status: "error"` 的 cases re-executed；`status: "skipped"` 的 cases dropped（并记录到 `summary["skipped_cases"]`）。
  - 新 `RunResult` 记录
    `summary["prior_run_id"] = prior.run_id` 和
    `summary["resume_kind"]` ∈
    `{"missing", "failed", "no-op"}`。

- [ ] **Step 4：将 `resume` subcommand 添加到 parser**

  在 `arm64_probe/cli/parser.py` 中：

  - 扩展 `COMMANDS`。
  - 添加 `resume_parser`，包含 required `--run <path>`、
    `--output-dir`、`--case-timeout`（或
    `--no-case-timeout`）、`--allow-mutation`、
    `-o/--output`。

- [ ] **Step 5：在 `main.py` 中添加 dispatch**

  在 `arm64_probe/cli/main.py` 中：

  - 通过 `RunResultStore.read(prior_path)` 读取 prior `RunResult`。
  - 从 prior `RunResult.plan` 重建 `Plan`（除非用户传入新的 `--select` / `--profile`，否则不进行 fresh `Planner` invocation —— handoff 固定 resume 行为为“重跑 prior `RunResult` 中引用的 cases”）。
  - 调用 `ResumeService.resume(...)`。
  - 打印 `render_resume(result, args.output)`。

- [ ] **Step 6：实现 `render_resume`**

  与 `render_run` 镜像。Table view 增加 `RESUME` column，显示每个 case 的 `missing` / `failed` / `no-op`。JSON output 为 `to_data(result)`。

- [ ] **Step 7：运行 tests 并 commit**

  ```sh
  uv run --no-sync python -m unittest \
    tests.unit.test_resume \
    tests.contract.test_cli_resume \
    tests.integration.test_phase3_resume_workflow -v
  make check
  make legacy-check
  git diff --check
  git add arm64_probe/execution/resume.py \
    arm64_probe/cli/parser.py arm64_probe/cli/main.py \
    arm64_probe/cli/render.py \
    tests/unit/test_resume.py \
    tests/contract/test_cli_resume.py \
    tests/integration/test_phase3_resume_workflow.py
  git commit -m "Add probe resume and ResumeService"
  ```

  预期：focused tests 通过；AC5 关闭。

## Batch 3：Acceptance, Smoke, and Runbook

### Task 20：Phase 3 Acceptance, Smoke Workflow, Documentation, and Gate 1 Runbook

**Files:**
- Modify: `Makefile`（添加 `smoke` 和 `phase3-check`；更新 `help`；添加到 `.PHONY`）
- Create: `tests/contract/test_phase3_acceptance.py`
- Create: `tests/integration/test_phase3_smoke_workflow.py`
- Create: `tests/integration/test_phase3_signal_restore.py`
- Create: `tests/integration/test_phase3_fixture_workflow.py`
- Create: `docs/superpowers/handoffs/2026-06-15-phase3-gate1-runbook.md`（AC9 deliverable；**不是** frozen file —— 用户在 Gate 1 时审阅）
- Modify: `tests/test_makefile_contract.py`（扩展 `phase3-check` 和 `smoke` wrappers）
- Modify: `tests/contract/test_phase2_acceptance.py`（扩展 platform-name branch check，覆盖 `arm64_probe/execution/`）
- Modify: `tests/contract/test_repository_policy.py`（扩展 frozen-path integrity，断言新 file paths 不在 frozen list）
- Modify: `tests/contract/test_public_schemas.py`（已在 Task 16 扩展；此处 verify）
- Modify: `AGENTS.md`（Phase 3 section）
- Modify: `CLAUDE.md`（Phase 3 architecture section）
- Modify: `docs/design/cli-contract.md`（添加 `probe run` 和 `probe resume`）
- Modify: `docs/design/repository-contract.md`（添加 `make phase3-check` 和 `make smoke`）
- Modify: `docs/superpowers/handoffs/2026-06-15-phase2-closure-and-phase3-readiness.md`（将 “Phase 3 plan written and accepted” gate 替换为新状态）

- [ ] **Step 1：编写失败的 acceptance tests**

  在 `tests/contract/test_phase3_acceptance.py` 中：

  - `test_no_platform_name_branch_in_execution_modules` ——
    扩展现有 Phase 2 contract，禁止
    `arm64_probe/execution/` 中出现
    `gb10` / `m4` / `taskset` / `sudo ` / `/sys/` /
    `/proc/` literals。
  - `test_runner_runner_cli_resume_schemas_have_contract_tests`
    —— `to_data(RunResult)` path 所需的每个 public schema 都在
    `SCHEMA_REQUIRED` 中。
  - `test_probe_run_does_not_bypass_coordinator` —— focused test，import `arm64_probe.cli.main` 并断言 `run` dispatch 通过 `Runner.run` 路由，而不是 hand-rolled subprocess wrapper。
  - `test_resume_rejects_cross_version_results` —— 四个 compat fields 分别被覆盖。
  - `test_smoke_workflow_runs_without_host_mutation` —— fake-backend 路径通过 `make smoke` 产生 schema-valid `RunResult` 并写入 tempdir。
  - `test_frozen_paths_remain_unchanged` —— 现有
    `git diff main..HEAD` filter 覆盖
    `runner/`、`data/`、`analysis/`、`baseline/`，且仍通过。

- [ ] **Step 2：编写失败的 Makefile contract tests**

  在 `tests/test_makefile_contract.py` 中扩展：

  - `test_phase3_wrappers_are_thin` —— `make smoke` 和
    `make phase3-check` 存在；recipes 由 uv 管理；不包含 parsing、不包含 platform branch、不包含 mutation logic。
  - `test_phase3_help_advertises_targets` —— `make help` 提及 `phase3-check` 和 `smoke`。

- [ ] **Step 3：运行 focused tests 并确认失败**

  ```sh
  uv run --no-sync python -m unittest tests.contract.test_phase3_acceptance -v
  uv run --no-sync python -m unittest tests.test_makefile_contract -v
  ```

  预期：FAIL（acceptance tests missing；Makefile targets missing）。

- [ ] **Step 4：添加 Makefile targets 并更新 help**

  在 `Makefile` 中：

  ```makefile
  phase3-check:
      $(UV_RUN) python -m unittest discover -s tests -p 'test_*.py' -v
      $(UV_RUN) python scripts/legacy_manifest.py verify
      $(UV_RUN) python -m unittest tests.contract.test_exit_codes -v
      $(UV_RUN) python -m unittest tests.contract.test_run_plan_equivalence -v
      $(UV_RUN) python -m unittest tests.contract.test_cli_run -v
      $(UV_RUN) python -m unittest tests.contract.test_cli_resume -v

  smoke:
      @mkdir -p $(BUILD_DIR)/smoke-runs
      $(UV_RUN) python ./probe plan --platform gb10 --profile smoke -o json > $(BUILD_DIR)/smoke-plan.json
      $(UV_RUN) python ./probe run --platform gb10 --profile smoke --allow-mutation \
          --output-dir $(BUILD_DIR)/smoke-runs
  ```

  更新 `.PHONY` 和 `help`。

- [ ] **Step 5：实现 smoke workflow integration tests**

  在 `tests/integration/test_phase3_smoke_workflow.py` 中：

  - 使用 fake `Backend` + `FakeController` + `FakeAdapter` + `ExecutorRecorder` 驱动 runner。
  - 断言 schema-valid `RunResult` 落在 tempdir 下。

  在 `tests/integration/test_phase3_signal_restore.py` 中：

  - runner 的 `work` callback 中途收到 SIGTERM；
    `EnvironmentCoordinator` 恢复 host，并写入 partial `RunResult`。

  在 `tests/integration/test_phase3_fixture_workflow.py` 中：

  - 等价于 Phase 2 fixture workflow，但针对 `probe run`，使用
    `FakeBackend` + `FakeController` + `FakeAdapter`。

- [ ] **Step 6：扩展现有 acceptance tests**

  在 `tests/contract/test_phase2_acceptance.py` 中，将
  `arm64_probe/execution/` 添加到 platform-name branch check。

  在 `tests/contract/test_repository_policy.py` 中，将
  `runner/`、`data/`、`analysis/`、`baseline/` 加入 v1.0-owned paths 下 forbidden new entries（defense in depth；`make legacy-check` 已通过 `legacy/manifest.json` 保护 frozen paths）。

- [ ] **Step 7：更新文档**

  在 `AGENTS.md`：添加 Phase 3 section，列出
  `probe run`、`probe resume`、`make smoke`、
  `make phase3-check`、`Sample` 和 `RunResult`
  schema-version bump，以及 AC1–AC9 evidence matrix pointer（`tests/contract/test_phase3_acceptance.py`）。

  在 `CLAUDE.md`：添加 Phase 3 architecture section，覆盖
  `Runner`、`ProbeAdapter`、`RunResultStore`、
  `ResumeService` 和 `Makefile` targets。

  在 `docs/design/cli-contract.md`：将 `probe run` 和
  `probe resume` 添加到 Phase 2 surface block（**不要**添加 `probe analyze` 或 `probe report`；它们属于 Phase 4）。

  在 `docs/design/repository-contract.md`：添加
  `make phase3-check` 和 `make smoke`。

  在 `docs/superpowers/handoffs/2026-06-15-phase2-closure-and-phase3-readiness.md`：
  更新 §1.3 table —— 将 Gate 2（Phase 3 plan written and accepted）标记为 done；将 Gate 3（`probe run` / `probe resume` CLI + domain model）、Gate 4（probe normalization）、Gate 5（unified runner + transactional integration）和 Gate 6（Mac + Linux ARM64 fixture smoke workflow）通过引用新 commits 标记为 done；Gate 7（GB10 hardware）和 Gate 8（`GB10 Gate 1 is ready to run`）仍标记为 pending。

- [ ] **Step 8：编写 Gate 1 runbook**

  创建
  `docs/superpowers/handoffs/2026-06-15-phase3-gate1-runbook.md`，
  包含 Phase Completion Gate §1（runbook subsection）中的精确步骤列表。明确标记为 **user-executed** runbook；implementer **不**执行它。runbook 作为 deliverable 加入 AC9 evidence matrix，而不是作为 automated evidence。

- [ ] **Step 9：运行完整验证**

  ```sh
  make phase3-check
  make check
  make legacy-check
  make build
  make smoke
  ./probe --help
  ./probe help run
  ./probe help resume
  git diff --check
  git status --short
  git diff --name-status main...HEAD
  ```

  预期：所有 tests 通过；smoke workflow 在 `build/smoke-runs/` 下写入 `RunResult`；`run` 和 `resume` 的 help 存在；diff 中不出现 frozen 或 transitional paths。

- [ ] **Step 10：审查完整 Phase 3 diff**

  ```sh
  git diff --stat main...HEAD
  git diff --name-status main...HEAD
  git status --short
  ```

  确认：

  - 无 frozen 或 transitional files 被修改；
  - `Makefile` 或 shebangs 中无 `python3` literal；
  - `arm64_probe/` 中无 platform-name branch；
  - 无新的公共 `environment-apply` command；
  - 文档与实现行为一致。

- [ ] **Step 11：commit Phase 3 acceptance evidence**

  ```sh
  git add Makefile AGENTS.md CLAUDE.md \
    arm64_probe \
    docs/design \
    docs/superpowers/handoffs \
    tests
  git commit -m "Complete Phase 3 probes and unified runner"
  ```

  预期：acceptance commit 后 branch 干净；runbook 包含在该 commit 中（用户在 Gate 1 时审阅，而非之前）。

## Phase 3 Completion Gate

在请求 architect review 前：

1. 从 clean tree 运行 `make phase3-check`、`make check`、`make legacy-check` 和 `make build`。
2. 运行 `make smoke`，确认 schema-valid `RunResult` 落在 `build/smoke-runs/` 下。
3. 确认 `tests/contract/test_phase3_acceptance.py` 中的每个 AC1–AC9 evidence entry，以及本计划中的 per-task proof matrix 均已满足。
4. 确认 `probe run` 和 `probe resume` 已进行 contract-tested（AC2、AC5、AC6），并且 test count 相比 Phase 2 baseline 的 241 至少增加 25。
5. 确认 `results/runs/` 被 git 忽略；确认本阶段**未**触碰 `results/baselines/<version>/`。
6. 确认 environment layer 的 production `STATE_ROOT` 仍然是 `/var/lib/arm64-uarch-probe`，且未被 override。
7. 确认 Phase 3 不包含 GB10 measurement evidence，也不作任何 M4 measurement claim。
8. 确认 AC9 runbook 存在且可由用户执行。
9. Review 并将 Phase 3 implementation branch merge 到 `main`（由用户执行；保留历史，使用 `--no-ff`），然后用户才宣布 `GB10 Gate 1 is ready to run`。

implementer **不**宣布 `GB10 Gate 1 is ready to run`。用户在真实 GB10 硬件上运行 AC9 runbook 后再宣布。

在 Gate 1 阶段，如果用户遇到 failure，implementer 的职责是先在 Mac 或 Linux ARM64 上修复并重新验证。不要将 Gate 1 扩展为广泛 exploratory measurement；handoff 明确禁止这样做。

用户 merge Phase 3 branch 后，implementer 将工作移交给用户（以及 Phase 4 handoff architect，如果用户后续创建该 handoff）。Phase 3 branch 是下一个 handoff artifact；handoff chain 现在是 `phase1 → phase2 → phase3`。