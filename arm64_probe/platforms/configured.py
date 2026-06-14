from arm64_probe.domain.models import NamedCpuSet, Platform


def _sets(items: tuple[NamedCpuSet, ...]) -> dict[str, tuple[int, ...]]:
    return {item.id: item.cpus for item in items}


def _all_cpus(platform: Platform) -> set[int]:
    return {cpu for cluster in platform.clusters for cpu in cluster.cpus}


def _selected_cpus(
    platform: Platform,
    cluster: str | None,
    core_group: str | None,
) -> tuple[int, ...]:
    clusters = _sets(platform.clusters)
    groups = _sets(platform.core_groups)
    if cluster is not None and cluster not in clusters:
        raise ValueError(f"unknown cluster: {cluster}")
    if core_group is not None and core_group not in groups:
        raise ValueError(f"unknown core group: {core_group}")
    selected = _all_cpus(platform)
    if cluster is not None:
        selected.intersection_update(clusters[cluster])
    if core_group is not None:
        selected.intersection_update(groups[core_group])
    return tuple(sorted(selected))


def _source(cluster: str | None, core_group: str | None) -> str:
    if core_group is not None:
        return f"platform-selector:{core_group}"
    if cluster is not None:
        return f"platform-selector:{cluster}"
    return "platform-default"


def _semantic_cpu(
    platform: Platform,
    cluster: str | None,
    core_group: str | None,
) -> int | None:
    selected = _selected_cpus(platform, cluster, core_group)
    if not selected:
        return None
    if core_group is not None:
        clusters = (cluster,) if cluster is not None else tuple(
            sorted(item.id for item in platform.clusters)
        )
        representatives = dict(platform.representative_cpus)
        for cluster_id in clusters:
            representative = representatives.get(f"{cluster_id}.{core_group}")
            if representative in selected:
                return representative
    return selected[0]


class ConfiguredPlatformAdapter:
    def resolve_single(
        self,
        platform: Platform,
        cluster: str | None,
        core_group: str | None,
        cpu_override: int | None,
    ) -> tuple[int | None, str]:
        if cpu_override is not None:
            if cpu_override not in _all_cpus(platform):
                raise ValueError(f"CPU {cpu_override} is not part of {platform.id}")
            return cpu_override, "cli"
        return _semantic_cpu(platform, cluster, core_group), _source(
            cluster,
            core_group,
        )

    def resolve_pair(
        self,
        platform: Platform,
        cpu_mode: str,
        cluster: str | None,
        core_group: str | None,
        src_override: int | None,
        dst_override: int | None,
    ) -> tuple[int | None, int | None, str]:
        source = _source(cluster, core_group)
        src: int | None
        dst: int | None
        if cpu_mode == "pair-same-core":
            src = dst = _semantic_cpu(platform, cluster, core_group)
        elif cpu_mode == "pair-same-cluster":
            clusters = _sets(platform.clusters)
            source_cluster = cluster or sorted(clusters)[0]
            source_cpus = _selected_cpus(platform, source_cluster, core_group)
            src = source_cpus[0] if source_cpus else None
            dst = source_cpus[1] if len(source_cpus) > 1 else None
        elif cpu_mode == "pair-cross-cluster":
            clusters = _sets(platform.clusters)
            source_cluster = cluster or sorted(clusters)[0]
            other_clusters = [item for item in sorted(clusters) if item != source_cluster]
            src = _semantic_cpu(platform, source_cluster, core_group)
            dst = (
                _semantic_cpu(platform, other_clusters[0], core_group)
                if other_clusters
                else None
            )
        else:
            raise ValueError(f"unknown CPU mode: {cpu_mode}")
        if src_override is not None:
            src, _ = self.resolve_single(platform, None, None, src_override)
        if dst_override is not None:
            dst, _ = self.resolve_single(platform, None, None, dst_override)
        return src, dst, source
