CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -g

BUILD_DIR := build
BIN_DIR := $(BUILD_DIR)/bin
UNAME_S := $(shell uname -s)

CHASE_PMU_SRC := src/chase_pmu/chase_pmu_v2.7.3.c
EVICT_SLC_SRC := src/evict_slc/evict_slc_v1.2.c
CHASE_MIGRATE_SRC := src/chase_migrate/chase_migrate_v1.0.c

CHASE_PMU_BIN := $(BIN_DIR)/chase_pmu
EVICT_SLC_BIN := $(BIN_DIR)/evict_slc
CHASE_MIGRATE_BIN := $(BIN_DIR)/chase_migrate

LINUX_BINS := $(CHASE_PMU_BIN) $(EVICT_SLC_BIN) $(CHASE_MIGRATE_BIN)

ifeq ($(UNAME_S),Linux)
HOST_BINS := $(LINUX_BINS)
else
HOST_BINS := $(EVICT_SLC_BIN)
endif

.PHONY: all build build-linux check legacy-check shell-check show-targets clean help

all: build

build: $(HOST_BINS)
	@echo "[OK] Built probes supported on $(UNAME_S)"

build-linux:
	@if [ "$(UNAME_S)" != "Linux" ]; then \
		echo "[ERROR] build-linux requires Linux" >&2; \
		exit 2; \
	fi
	@$(MAKE) $(LINUX_BINS)

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

clean:
	rm -rf $(BUILD_DIR)

help:
	@echo "Usage: make <target>"
	@echo "  build         Build probes supported on the current host"
	@echo "  build-linux   Build all Linux ARM64 probes; rejects non-Linux"
	@echo "  check         Run unit/contract and shell-syntax checks"
	@echo "  legacy-check  Verify frozen runner and data evidence"
	@echo "  show-targets  Show source, output, and platform support"
	@echo "  clean         Remove build products"
