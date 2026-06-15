# Profile Configurations

Committed scenario compositions, parameter overrides, and environment
requirements. Profiles describe intent; they do not invoke runners or mutate
the host.

Supported environment requests are `cpu-governor`, minimum/maximum CPU
frequency in kHz, `hugepages` with optional `hugepage-size-kb`, and
`transparent-hugepage`. A plan preview records these as privileged host
mutation requirements; execution still requires explicit authorization.
