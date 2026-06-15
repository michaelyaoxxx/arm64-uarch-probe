# Platform Configurations

Hardware-platform facts, semantic CPU sets, capabilities, and parameter
defaults. Add a new platform as declarative data that satisfies the shared
platform contract. Do not place backend implementation or orchestration here.

`environment_defaults` supplies platform facts used to complete explicit host
requests, such as `{"hugepage-size-kb": 2048}`. Defaults never request a host
mutation on their own.
