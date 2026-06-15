from typing import Protocol

from arm64_probe.domain.models import Platform


class PlatformResolver(Protocol):
    def resolve_single(
        self,
        platform: Platform,
        cluster: str | None,
        core_group: str | None,
        cpu_override: int | None,
    ) -> tuple[int | None, str]: ...

    def resolve_pair(
        self,
        platform: Platform,
        cpu_mode: str,
        cluster: str | None,
        core_group: str | None,
        src_override: int | None,
        dst_override: int | None,
    ) -> tuple[int | None, int | None, str]: ...
