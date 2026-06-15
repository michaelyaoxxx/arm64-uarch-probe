CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -g

override BUILD_DIR := build
override BIN_DIR := $(BUILD_DIR)/bin
override HOST_OS := $(shell uname -s)
override REQUESTED_GOALS := $(if $(MAKECMDGOALS),$(MAKECMDGOALS),all)

override CHASE_PMU_SRC := src/chase_pmu/chase_pmu_v2.7.3.c
override EVICT_SLC_SRC := src/evict_slc/evict_slc_v1.2.c
override CHASE_MIGRATE_SRC := src/chase_migrate/chase_migrate_v1.0.c

override CHASE_PMU_BIN := $(BIN_DIR)/chase_pmu
override EVICT_SLC_BIN := $(BIN_DIR)/evict_slc
override CHASE_MIGRATE_BIN := $(BIN_DIR)/chase_migrate

override LINUX_BINS := $(CHASE_PMU_BIN) $(EVICT_SLC_BIN) $(CHASE_MIGRATE_BIN)

ifeq ($(HOST_OS),Linux)
override HOST_BINS := $(LINUX_BINS)
else ifeq ($(HOST_OS),Darwin)
override HOST_BINS := $(EVICT_SLC_BIN)
else
override HOST_BINS :=
ifneq ($(filter all build build-linux,$(REQUESTED_GOALS)),)
$(error [ERROR] unsupported host: $(HOST_OS))
endif
endif

.PHONY: all build build-linux check legacy-check shell-check show-targets probe probe-help phase1-check phase2-check doctor clean help

all: build

build: $(HOST_BINS)
	@echo "[OK] Built probes supported on $(HOST_OS)"

ifeq ($(HOST_OS),Linux)
build-linux: $(LINUX_BINS)
	@echo "[OK] Built all Linux ARM64 probes"
else
build-linux:
	@echo "[ERROR] build-linux requires Linux" >&2
	@exit 2
endif

$(BIN_DIR):
	@mkdir -p $@

$(CHASE_PMU_BIN): $(CHASE_PMU_SRC) | $(BIN_DIR)
	$(CC) $(CFLAGS) -o $@ $<

$(EVICT_SLC_BIN): $(EVICT_SLC_SRC) | $(BIN_DIR)
	$(CC) $(CFLAGS) -o $@ $<

$(CHASE_MIGRATE_BIN): $(CHASE_MIGRATE_SRC) | $(BIN_DIR)
	$(CC) $(CFLAGS) -o $@ $<

check:
	python3 -m unittest discover -s tests -p 'test_*.py' -v
	$(MAKE) shell-check

legacy-check:
	python3 scripts/legacy_manifest.py verify

shell-check:
	@for script in runner/*.sh; do \
		echo "[CHECK] bash -n $$script"; \
		bash -n "$$script" || exit 1; \
	done

show-targets:
	@echo "$(CHASE_PMU_SRC) -> $(CHASE_PMU_BIN) [Linux]"
	@echo "$(EVICT_SLC_SRC) -> $(EVICT_SLC_BIN) [Linux,Darwin]"
	@echo "$(CHASE_MIGRATE_SRC) -> $(CHASE_MIGRATE_BIN) [Linux]"

probe:
	./probe $(PROBE_ARGS)

probe-help:
	./probe --help

doctor:
	./probe doctor $(PROBE_ARGS)

phase1-check:
	python3 -m unittest discover -s tests -p 'test_*.py' -v
	python3 scripts/legacy_manifest.py verify

phase2-check:
	python3 -m unittest discover -s tests -p 'test_*.py' -v
	python3 scripts/legacy_manifest.py verify

clean:
	@test "$(BUILD_DIR)" = "build" || { \
		echo "[ERROR] refusing to clean unexpected directory: $(BUILD_DIR)" >&2; \
		exit 2; \
	}
	rm -rf $(BUILD_DIR)

help:
	@echo "Usage: make <target>"
	@echo "  build         Build probes supported on the current host"
	@echo "  build-linux   Build all Linux ARM64 probes; rejects non-Linux"
	@echo "  check         Run unit/contract and shell-syntax checks"
	@echo "  legacy-check  Verify frozen runner and data evidence"
	@echo "  show-targets  Show source, output, and platform support"
	@echo "  probe         Run ./probe with PROBE_ARGS"
	@echo "  probe-help    Show the Phase 1 control-interface help"
	@echo "  doctor        Run ./probe doctor with PROBE_ARGS"
	@echo "  phase1-check  Run Phase 1 Python tests and legacy verification"
	@echo "  phase2-check  Run Phase 2 Python tests and legacy verification"
	@echo "  clean         Remove build products"
