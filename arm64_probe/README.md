# arm64_probe

Platform-independent Python control layer for immutable domain models, strict
registry loading, generic configured-platform adapters, deterministic planning,
serialization, the Phase 1 CLI, the read-only `probe doctor` host inspection,
and the recoverable environment transaction/recovery flow used by
`probe restore`.

Keep host inspection read-only and environment mutation capability-driven. The
`arm64_probe/environment/` package owns the durable journal, the host-wide
`MutationLock`, the recoverable `EnvironmentCoordinator`, the signal-aware
`CommonSignalScope`, and the `EnvironmentRecovery` service. None of these
modules import a specific platform, experiment, or sysfs path; they consume
the registered controllers that the selected `HostBackend` exposes.
