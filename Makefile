# ============================================================
# GB10 MicroArch Makefile
# ============================================================
# 增量编译机制：
#   tools/ 下各子目录的 .c 文件自动发现，无需手动注册
#   新增工具只需在 tools/<subdir>/ 下放 .c 文件，make build 自动识别
#   每个 .c 对应一个同名 binary（去掉版本后缀），输出到 tools/bin/
# ============================================================

CC      := gcc
CFLAGS  := -O2 -Wall -g

ROOT    := .
TOOLS   := $(ROOT)/tools
BIN     := $(TOOLS)/bin
RUNNER  := $(ROOT)/runner
DATA    := $(ROOT)/data
RUN_SCRIPT ?= $(RUNNER)/run_pmu_v2.7.7.sh

# ============================================================
# 自动发现所有 tools/ 子目录下的 .c 源文件
# 目录结构：
#   tools/chase_pmu/chase_pmu_v2.7.3.c  → bin/chase_pmu
#   tools/evict/evict_slc_v2.7.3.c      → bin/evict_slc
#   tools/chase_pmu/chase_migrate_v0.c  → bin/chase_migrate
#
# 命名规则：取文件名，去掉 _v<版本号>.c 后缀
#   chase_pmu_v2.7.3.c  → chase_pmu
#   evict_slc_v2.7.3.c  → evict_slc
#   chase_migrate_v0.c  → chase_migrate
# ============================================================

# 递归查找所有 .c 文件
ALL_SRCS := $(shell find $(TOOLS) -name '*.c' -not -path '$(BIN)/*')

# 从文件名提取 binary 名：去掉路径、去掉 _v<任意版本>.c 后缀
# 例：tools/chase_pmu/chase_pmu_v2.7.3.c → chase_pmu
src_to_bin = $(BIN)/$(shell echo $(notdir $(1)) | sed 's/_v[0-9][^.]*\.c$$//' | sed 's/\.c$$//')

ALL_BINS := $(foreach src,$(ALL_SRCS),$(call src_to_bin,$(src)))

# 去重（同名 binary 只保留一个，避免 chase_pmu/ 下多个 .c 冲突）
ALL_BINS := $(sort $(ALL_BINS))

# ============================================================
# Default target
# ============================================================
.PHONY: all build prep run cross-cluster clean distclean help \
        test-l3 test-slc test-dram test-hugepage test-evict test-migrate

all: build

# ============================================================
# Build：自动推导所有 binary
# ============================================================
build: prep $(ALL_BINS)
	@echo ""
	@echo "[OK] Build complete. Binaries:"
	@ls -1 $(BIN)/

prep:
	@mkdir -p $(BIN)
	@mkdir -p $(DATA)

# 通用模式规则：从 ALL_SRCS 中反查对应 .c，编译成 binary
# 每个 binary 依赖其对应的 .c（通过 secondary expansion 实现）
.SECONDEXPANSION:
$(BIN)/%: $$(filter %/$$*_v%.c $$(filter %/$$*.c, $(ALL_SRCS)), $(ALL_SRCS))
	@# 反查：找到 binary 名对应的源文件
	$(eval _SRC := $(firstword $(filter $(TOOLS)/%/$*%.c, $(ALL_SRCS))))
	@if [ -z "$(_SRC)" ]; then \
	    echo "[ERROR] No source found for target: $@"; exit 1; \
	fi
	@echo "[BUILD] $* <- $(_SRC)"
	$(CC) $(CFLAGS) -o $@ $(_SRC)

# ============================================================
# Run targets
# ============================================================
run: build
	@echo "[RUN] Script: $(RUN_SCRIPT) to do Full PMU validation..."
	chmod +x $(RUN_SCRIPT) && cd $(RUNNER) && bash $(notdir $(RUN_SCRIPT))

cross-cluster: build
	@echo "[RUN] Cross-cluster migration scaffold..."
	cd $(RUNNER) && chmod +x run_cross_cluster_latency.sh && ./run_cross_cluster_latency.sh

# ============================================================
# Quick tests
# ============================================================
test-l3: build
	@echo "[TEST] L3 latency (cpu5, 4MB warm)"
	taskset -c 5 $(BIN)/chase_pmu 4096 5

test-slc: build
	@echo "[TEST] SLC latency (cpu5, 16MB warm)"
	taskset -c 5 $(BIN)/chase_pmu 16384 5

test-dram: build
	@echo "[TEST] DRAM latency cold (cpu5, 64MB)"
	taskset -c 5 $(BIN)/chase_pmu 65536 0 1 42 1

test-hugepage: build
	@echo "[TEST] Hugepage vs 4K (cpu5, 12MB)"
	@echo "--- 4K page ---"
	taskset -c 5 $(BIN)/chase_pmu 12288 5 25 42 0 0
	@echo "--- Hugepage ---"
	taskset -c 5 $(BIN)/chase_pmu 12288 5 25 42 0 1

test-evict: build
	@echo "[TEST] Evict SLC/L3 (32MB)"
	taskset -c 5 $(BIN)/evict_slc --evict_mb=32

test-migrate: build
	@echo "[TEST] Cross-cluster migrate C0-X925 -> C1-X925"
	$(BIN)/chase_migrate \
	    --src-cpu 5 --dst-cpu 15 --size-kb 16384 \
	    --warm-src 5 --measure-rounds 1 --seed 42 \
	    --hugepage 0 --label C0-X925_to_C1-X925_16MB

# ============================================================
# Debug：打印自动发现的 src→bin 映射（排查增量编译问题用）
# ============================================================
show-targets:
	@echo "=== Discovered sources ==="
	@for s in $(ALL_SRCS); do echo "  SRC: $$s"; done
	@echo "=== Derived binaries ==="
	@for b in $(ALL_BINS); do echo "  BIN: $$b"; done

# ============================================================
# Clean
# ============================================================
clean:
	@echo "[CLEAN] Removing binaries..."
	rm -f $(ALL_BINS)

distclean: clean
	@echo "[CLEAN] Removing raw data under data/..."
	find $(DATA) -name '*.txt' -delete
	find $(DATA) -name '*.csv' -delete

# ============================================================
# Help
# ============================================================
help:
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Build:"
	@echo "  make build           - Auto-discover & build all tools under tools/"
	@echo "  make show-targets    - Print src→bin mapping (debug)"
	@echo ""
	@echo "Run:"
	@echo "  make run             - Full PMU benchmark"
	@echo "  make cross-cluster   - Cross-cluster migration"
	@echo ""
	@echo "Quick tests:"
	@echo "  make test-l3         - L3 latency (4MB, cpu5)"
	@echo "  make test-slc        - SLC latency (16MB, cpu5)"
	@echo "  make test-dram       - DRAM cold latency (64MB, cpu5)"
	@echo "  make test-hugepage   - Hugepage vs 4K (12MB, cpu5)"
	@echo "  make test-evict      - Evict SLC/L3 (32MB)"
	@echo "  make test-migrate    - Cross-cluster C0-X925→C1-X925"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           - Remove binaries"
	@echo "  make distclean       - Remove binaries + raw data"
	@echo ""
	@echo "Adding a new tool:"
	@echo "  1. Put <toolname>_v<ver>.c under tools/<subdir>/"
	@echo "  2. make build   <- no Makefile edit needed"
	@echo ""
