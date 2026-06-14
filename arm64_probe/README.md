# arm64_probe

Platform-independent Python control layer for immutable domain models, strict
registry loading, generic configured-platform adapters, deterministic planning,
serialization, and the Phase 1 CLI.

Keep host inspection and environment mutation outside this package. Phase 1
commands are read-only and consume reviewed facts from `configs/`.
