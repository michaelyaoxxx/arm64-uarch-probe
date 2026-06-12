#!/usr/bin/env python3
# cache_info_model.py
# Model and render Linux CPU cache topology from raw TSV collected by cache_info_collect.sh.
#
# Design:
#   - Python owns data modeling, JSON, CSV, domain de-dup, grouping and rendering.
#   - Raw facts remain distinguishable from platform annotations.
#
# Usage:
#   ./cache_info_collect.sh | python3 cache_info_model.py --table
#   ./cache_info_collect.sh | python3 cache_info_model.py --json
#   ./cache_info_collect.sh | python3 cache_info_model.py --csv --outdir ./cache_csv_out
#   python3 cache_info_model.py --input ./cache_raw.tsv --table --platform gb10

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Iterable, Any


EXPECTED_COLUMNS = [
    "cpu_id",
    "online",
    "cluster_raw",
    "physical_package_id",
    "core_id",
    "max_freq_khz",
    "max_freq_mhz",
    "cache_index",
    "cache_id",
    "level",
    "type",
    "size_raw",
    "size_kb",
    "line_bytes",
    "sets",
    "ways",
    "calc_kb",
    "shared_cpu_map",
    "shared_cpu_list",
    "allocation_policy",
    "write_policy",
    "physical_line_partition",
]


def maybe_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    s = str(x).strip()
    if re.fullmatch(r"[0-9]+", s):
        return int(s)
    return None


def int_or_str(x: Any) -> Any:
    v = maybe_int(x)
    return v if v is not None else x


def human_kb(kb: Optional[int]) -> str:
    if kb is None:
        return "?"
    if kb >= 1024 and kb % 1024 == 0:
        return f"{kb // 1024}MB"
    return f"{kb}KB"


def expand_cpu_list(cpu_list: str) -> List[int]:
    """
    Parse Linux CPU list syntax: "0-3,8,10-12".
    """
    cpu_list = (cpu_list or "").strip()
    if not cpu_list:
        return []

    out: List[int] = []
    for part in cpu_list.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([0-9]+)-([0-9]+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(range(a, b + 1))
        elif re.fullmatch(r"[0-9]+", part):
            out.append(int(part))
    return sorted(set(out))


def format_cpu_list(cpus: Iterable[int]) -> str:
    """
    Keep explicit list for readability: 0,1,2...
    """
    return ",".join(str(c) for c in sorted(cpus))


def decode_cpumap(cpumap: str) -> List[int]:
    """
    Fallback decoder for Linux cpumask hex string, e.g.:
      003ff -> 0..9
      ffc00 -> 10..19
      00000000,000000ff -> 0..7

    Prefer shared_cpu_list when available.
    """
    s = (cpumap or "").strip().lower()
    if not s or s == "?":
        return []
    s = s.replace(",", "")
    if s.startswith("0x"):
        s = s[2:]
    if not re.fullmatch(r"[0-9a-f]+", s):
        return []

    cpus: List[int] = []
    bit = 0
    for ch in reversed(s):
        nibble = int(ch, 16)
        for b in range(4):
            if (nibble >> b) & 1:
                cpus.append(bit)
            bit += 1
    return cpus


def normalize_shared_cpus(shared_cpu_list: str, shared_cpu_map: str) -> List[int]:
    cpus = expand_cpu_list(shared_cpu_list)
    if cpus:
        return cpus
    return decode_cpumap(shared_cpu_map)


@dataclass(frozen=True)
class CacheRow:
    cpu_id: Optional[int]
    online: Optional[int]
    cluster_raw: str
    physical_package_id: str
    core_id: Optional[int]
    max_freq_khz: Optional[int]
    max_freq_mhz: Optional[int]
    cache_index: Optional[int]
    cache_id: str
    level: Optional[int]
    type: str
    size_raw: str
    size_kb: Optional[int]
    line_bytes: Optional[int]
    sets: Optional[int]
    ways: Optional[int]
    calc_kb: Optional[int]
    shared_cpu_map: str
    shared_cpu_list: str
    shared_cpus: Tuple[int, ...]
    allocation_policy: str
    write_policy: str
    physical_line_partition: str
    cluster_index: Optional[int] = None

    @staticmethod
    def from_dict(d: Dict[str, str]) -> "CacheRow":
        shared_cpus = tuple(
            normalize_shared_cpus(
                d.get("shared_cpu_list", ""),
                d.get("shared_cpu_map", ""),
            )
        )

        return CacheRow(
            cpu_id=maybe_int(d.get("cpu_id")),
            online=maybe_int(d.get("online")),
            cluster_raw=str(d.get("cluster_raw", "?")),
            physical_package_id=str(d.get("physical_package_id", "?")),
            core_id=maybe_int(d.get("core_id")),
            max_freq_khz=maybe_int(d.get("max_freq_khz")),
            max_freq_mhz=maybe_int(d.get("max_freq_mhz")),
            cache_index=maybe_int(d.get("cache_index")),
            cache_id=str(d.get("cache_id", "?")),
            level=maybe_int(d.get("level")),
            type=str(d.get("type", "?")),
            size_raw=str(d.get("size_raw", "?")),
            size_kb=maybe_int(d.get("size_kb")),
            line_bytes=maybe_int(d.get("line_bytes")),
            sets=maybe_int(d.get("sets")),
            ways=maybe_int(d.get("ways")),
            calc_kb=maybe_int(d.get("calc_kb")),
            shared_cpu_map=str(d.get("shared_cpu_map", "?")),
            shared_cpu_list=str(d.get("shared_cpu_list", "")),
            shared_cpus=shared_cpus,
            allocation_policy=str(d.get("allocation_policy", "")),
            write_policy=str(d.get("write_policy", "")),
            physical_line_partition=str(d.get("physical_line_partition", "")),
        )

    def with_cluster_index(self, idx: int) -> "CacheRow":
        return CacheRow(
            cpu_id=self.cpu_id,
            online=self.online,
            cluster_raw=self.cluster_raw,
            physical_package_id=self.physical_package_id,
            core_id=self.core_id,
            max_freq_khz=self.max_freq_khz,
            max_freq_mhz=self.max_freq_mhz,
            cache_index=self.cache_index,
            cache_id=self.cache_id,
            level=self.level,
            type=self.type,
            size_raw=self.size_raw,
            size_kb=self.size_kb,
            line_bytes=self.line_bytes,
            sets=self.sets,
            ways=self.ways,
            calc_kb=self.calc_kb,
            shared_cpu_map=self.shared_cpu_map,
            shared_cpu_list=self.shared_cpu_list,
            shared_cpus=self.shared_cpus,
            allocation_policy=self.allocation_policy,
            write_policy=self.write_policy,
            physical_line_partition=self.physical_line_partition,
            cluster_index=idx,
        )

    def domain_key(self) -> Tuple[Any, ...]:
        """
        Conservative domain key.

        shared_cpus is preferred over raw shared_cpu_map so that equivalent
        masks/lists normalize to the same semantic domain.
        """
        return (
            self.level,
            self.type,
            self.size_kb,
            self.line_bytes,
            self.sets,
            self.ways,
            self.cache_id if self.cache_id not in ("", "?") else None,
            self.shared_cpus,
        )


@dataclass
class CacheDomain:
    domain_id: int
    primary_cpu: Optional[int]
    rows: List[CacheRow]

    @property
    def first(self) -> CacheRow:
        return self.rows[0]

    def cpu_list(self) -> List[int]:
        cpus = set()
        for r in self.rows:
            if r.cpu_id is not None:
                cpus.add(r.cpu_id)
        if self.first.shared_cpus:
            cpus.update(self.first.shared_cpus)
        return sorted(cpus)


@dataclass
class ClusterSummary:
    cluster_index: int
    cluster_raw: str
    cpus: List[int]
    l1d_kb: Optional[int]
    l1d_ways: Optional[int]
    l1i_kb: Optional[int]
    l1i_ways: Optional[int]
    l2_groups: List[Dict[str, Any]]
    l3_kb: Optional[int]
    l3_ways: Optional[int]
    l3_sets: Optional[int]
    l3_line_bytes: Optional[int]


@dataclass
class CoreGroup:
    cluster_index: int
    cluster_raw: str
    group_id: int
    cpus: List[int]
    max_freq_mhz: Optional[int]
    l2_kb: Optional[int]
    l2_ways: Optional[int]
    l2_sets: Optional[int]
    l1d_kb: Optional[int]
    l1d_ways: Optional[int]
    l1i_kb: Optional[int]
    l1i_ways: Optional[int]
    label: str
    label_source: str


def read_tsv(path: Optional[str]) -> List[CacheRow]:
    if path:
        f = open(path, "r", newline="")
        close = True
    else:
        f = sys.stdin
        close = False

    try:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames is None:
            return []

        missing = [c for c in EXPECTED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise SystemExit(f"ERROR: TSV missing columns: {missing}")

        rows = [CacheRow.from_dict(d) for d in reader]
    finally:
        if close:
            f.close()

    return assign_cluster_indices(rows)


def sort_cluster_raw_key(x: str) -> Tuple[int, Any]:
    if re.fullmatch(r"[0-9]+", str(x)):
        return (0, int(x))
    return (1, str(x))


def assign_cluster_indices(rows: List[CacheRow]) -> List[CacheRow]:
    clusters = sorted({r.cluster_raw for r in rows}, key=sort_cluster_raw_key)
    mapping = {c: i for i, c in enumerate(clusters)}
    return [r.with_cluster_index(mapping[r.cluster_raw]) for r in rows]


def build_domains(rows: List[CacheRow]) -> List[CacheDomain]:
    by_key: Dict[Tuple[Any, ...], List[CacheRow]] = {}
    for r in rows:
        by_key.setdefault(r.domain_key(), []).append(r)

    domains: List[CacheDomain] = []
    for i, key in enumerate(sorted(by_key.keys(), key=lambda k: str(k))):
        rs = sorted(by_key[key], key=lambda r: (-1 if r.cpu_id is None else r.cpu_id))
        primary_cpu = rs[0].cpu_id
        domains.append(CacheDomain(domain_id=i, primary_cpu=primary_cpu, rows=rs))

    return domains


def row_role_by_domain(rows: List[CacheRow], domains: List[CacheDomain]) -> Dict[Tuple[Any, ...], str]:
    """
    Map row identity to primary/shared note.
    Since dataclass is frozen, object hash is available.
    """
    note: Dict[Tuple[Any, ...], str] = {}
    for d in domains:
        primary = d.primary_cpu
        for r in d.rows:
            ident = row_identity(r)
            if r.cpu_id == primary:
                note[ident] = "primary"
            else:
                note[ident] = f"shared->cpu{primary}" if primary is not None else "shared"
    return note


def row_identity(r: CacheRow) -> Tuple[Any, ...]:
    return (
        r.cpu_id,
        r.cluster_raw,
        r.core_id,
        r.cache_index,
        r.level,
        r.type,
        r.size_kb,
        r.shared_cpu_map,
        r.shared_cpu_list,
    )


def rows_by_cluster(rows: List[CacheRow]) -> Dict[int, List[CacheRow]]:
    out: Dict[int, List[CacheRow]] = {}
    for r in rows:
        if r.cluster_index is None:
            continue
        out.setdefault(r.cluster_index, []).append(r)
    return out


def primary_rows(domains: List[CacheDomain]) -> List[CacheRow]:
    out: List[CacheRow] = []
    for d in domains:
        if d.rows:
            out.append(d.rows[0])
    return out


def build_cluster_summaries(rows: List[CacheRow], domains: List[CacheDomain]) -> List[ClusterSummary]:
    """
    Cluster summary is based on:
      - CPUs observed in all rows
      - primary cache domains for L2/L3
    """
    p_rows = primary_rows(domains)

    # cluster -> cpu set
    cluster_cpus: Dict[int, set] = {}
    cluster_raw: Dict[int, str] = {}

    for r in rows:
        if r.cluster_index is None or r.cpu_id is None:
            continue
        cluster_cpus.setdefault(r.cluster_index, set()).add(r.cpu_id)
        cluster_raw[r.cluster_index] = r.cluster_raw

    summaries: List[ClusterSummary] = []

    for ci in sorted(cluster_cpus.keys()):
        cr = cluster_raw.get(ci, "?")
        cpus = sorted(cluster_cpus[ci])

        l1d_kb = l1d_ways = l1i_kb = l1i_ways = None
        l3_kb = l3_ways = l3_sets = l3_line_bytes = None

        # For L1, all are expected uniform per core in current GB10 output.
        # We record the first observed value.
        for r in rows:
            if r.cluster_index != ci:
                continue
            if r.level == 1 and r.type == "Data" and l1d_kb is None:
                l1d_kb, l1d_ways = r.size_kb, r.ways
            elif r.level == 1 and r.type == "Instruction" and l1i_kb is None:
                l1i_kb, l1i_ways = r.size_kb, r.ways

        # L2 distribution: primary L2 rows grouped by size/ways/sets.
        l2_dist: Dict[Tuple[Any, Any, Any], List[int]] = {}
        for r in p_rows:
            if r.cluster_index != ci:
                continue
            if r.level == 2 and r.type == "Unified" and r.cpu_id is not None:
                k = (r.size_kb, r.ways, r.sets)
                l2_dist.setdefault(k, []).append(r.cpu_id)

        l2_groups: List[Dict[str, Any]] = []
        for gid, ((size_kb, ways, sets), group_cpus) in enumerate(
            sorted(l2_dist.items(), key=lambda item: (item[0][0] or -1, item[0][1] or -1))
        ):
            l2_groups.append(
                {
                    "group_id": gid,
                    "size_kb": size_kb,
                    "size_human": human_kb(size_kb),
                    "ways": ways,
                    "sets": sets,
                    "cpus": sorted(group_cpus),
                }
            )

        # L3: use primary L3 row per cluster if present.
        for r in p_rows:
            if r.cluster_index != ci:
                continue
            if r.level == 3 and r.type == "Unified":
                l3_kb, l3_ways, l3_sets, l3_line_bytes = r.size_kb, r.ways, r.sets, r.line_bytes
                break

        summaries.append(
            ClusterSummary(
                cluster_index=ci,
                cluster_raw=cr,
                cpus=cpus,
                l1d_kb=l1d_kb,
                l1d_ways=l1d_ways,
                l1i_kb=l1i_kb,
                l1i_ways=l1i_ways,
                l2_groups=l2_groups,
                l3_kb=l3_kb,
                l3_ways=l3_ways,
                l3_sets=l3_sets,
                l3_line_bytes=l3_line_bytes,
            )
        )

    return summaries


def build_core_groups(rows: List[CacheRow], platform: str = "generic") -> List[CoreGroup]:
    """
    Generic grouping:
      key = cluster_index, l2_size, l2_ways, l2_sets, max_freq_mhz

    GB10 platform:
      label is explicitly marked as inferred:
        L2 <= 512KB -> A-core inferred
        L2 >  512KB -> X-core inferred
      This is not claimed as sysfs-derived architectural identity.
    """
    # Per CPU fact collection.
    per_cpu: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        if r.cpu_id is None or r.cluster_index is None:
            continue
        d = per_cpu.setdefault(
            r.cpu_id,
            {
                "cluster_index": r.cluster_index,
                "cluster_raw": r.cluster_raw,
                "max_freq_mhz": r.max_freq_mhz,
                "l1d_kb": None,
                "l1d_ways": None,
                "l1i_kb": None,
                "l1i_ways": None,
                "l2_kb": None,
                "l2_ways": None,
                "l2_sets": None,
            },
        )
        if r.level == 1 and r.type == "Data":
            d["l1d_kb"] = r.size_kb
            d["l1d_ways"] = r.ways
        elif r.level == 1 and r.type == "Instruction":
            d["l1i_kb"] = r.size_kb
            d["l1i_ways"] = r.ways
        elif r.level == 2 and r.type == "Unified":
            d["l2_kb"] = r.size_kb
            d["l2_ways"] = r.ways
            d["l2_sets"] = r.sets

    grouped: Dict[Tuple[Any, ...], List[int]] = {}
    meta: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    for cpu, d in per_cpu.items():
        k = (
            d["cluster_index"],
            d["cluster_raw"],
            d["l2_kb"],
            d["l2_ways"],
            d["l2_sets"],
            d["max_freq_mhz"],
            d["l1d_kb"],
            d["l1d_ways"],
            d["l1i_kb"],
            d["l1i_ways"],
        )
        grouped.setdefault(k, []).append(cpu)
        meta[k] = d

    out: List[CoreGroup] = []
    group_id_by_cluster: Dict[int, int] = {}

    for k in sorted(grouped.keys(), key=lambda x: (x[0], x[2] or -1, x[5] or -1)):
        d = meta[k]
        ci = d["cluster_index"]
        gid = group_id_by_cluster.get(ci, 0)
        group_id_by_cluster[ci] = gid + 1

        l2_kb = d["l2_kb"]
        max_freq = d["max_freq_mhz"]

        label = f"CoreGroup-{gid}"
        label_source = "generic-grouping-by-l2-and-frequency"

        if platform == "gb10":
            if l2_kb is not None and l2_kb <= 512:
                label = "A-core-inferred"
                label_source = "gb10-profile-inferred-by-l2<=512KB"
            elif l2_kb is not None and l2_kb > 512:
                label = "X-core-inferred"
                label_source = "gb10-profile-inferred-by-l2>512KB"

        out.append(
            CoreGroup(
                cluster_index=ci,
                cluster_raw=str(d["cluster_raw"]),
                group_id=gid,
                cpus=sorted(grouped[k]),
                max_freq_mhz=max_freq,
                l2_kb=l2_kb,
                l2_ways=d["l2_ways"],
                l2_sets=d["l2_sets"],
                l1d_kb=d["l1d_kb"],
                l1d_ways=d["l1d_ways"],
                l1i_kb=d["l1i_kb"],
                l1i_ways=d["l1i_ways"],
                label=label,
                label_source=label_source,
            )
        )

    return out


def validation_status(r: CacheRow) -> str:
    if r.size_kb is None or r.calc_kb is None:
        return "?"
    return "OK" if r.size_kb == r.calc_kb else "MISMATCH"


def table_print(rows: List[List[Any]], headers: List[str]) -> None:
    srows = [[str(x) if x is not None else "?" for x in row] for row in rows]
    sheaders = [str(h) for h in headers]
    widths = [len(h) for h in sheaders]

    for row in srows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    fmt = "  ".join("{:<" + str(w) + "}" for w in widths)
    print(fmt.format(*sheaders))
    print(fmt.format(*["-" * w for w in widths]))
    for row in srows:
        print(fmt.format(*row))


def render_table(rows: List[CacheRow], domains: List[CacheDomain], platform: str) -> None:
    notes = row_role_by_domain(rows, domains)
    summaries = build_cluster_summaries(rows, domains)
    core_groups = build_core_groups(rows, platform=platform)

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("")
    print("═" * 110)
    print(f"  Linux CPU Cache Topology    {now}")
    print("═" * 110)
    print("")

    print("── Section 1: All CPU cache indices ───────────────────────────────────────────")
    section_rows = []
    for r in sorted(rows, key=lambda x: (x.cpu_id if x.cpu_id is not None else -1, x.cache_index if x.cache_index is not None else -1)):
        section_rows.append([
            r.cpu_id,
            r.cluster_index,
            r.cluster_raw,
            r.core_id,
            r.max_freq_mhz,
            r.cache_index,
            r.cache_id,
            r.level,
            r.type,
            r.size_kb,
            r.line_bytes,
            r.sets,
            r.ways,
            r.calc_kb,
            r.shared_cpu_map,
            r.shared_cpu_list or format_cpu_list(r.shared_cpus),
            notes.get(row_identity(r), "?"),
        ])
    table_print(
        section_rows,
        [
            "CPU", "ClIdx", "ClRaw", "Core", "MHz", "Idx", "CacheID", "Lv", "Type",
            "SizeKB", "Line", "Sets", "Ways", "CalcKB", "SharedMap", "SharedList", "Note",
        ],
    )

    print("")
    print("── Section 2: Unique cache domains ────────────────────────────────────────────")
    domain_rows = []
    for d in sorted(domains, key=lambda x: (
        x.first.level if x.first.level is not None else -1,
        x.first.type,
        x.first.size_kb if x.first.size_kb is not None else -1,
        x.primary_cpu if x.primary_cpu is not None else -1,
    )):
        f = d.first
        domain_rows.append([
            d.domain_id,
            f.level,
            f.type,
            f.size_kb,
            human_kb(f.size_kb),
            f.line_bytes,
            f.sets,
            f.ways,
            f.calc_kb,
            f.cache_id,
            f.shared_cpu_map,
            f.shared_cpu_list or format_cpu_list(f.shared_cpus),
            format_cpu_list(d.cpu_list()),
            d.primary_cpu,
        ])
    table_print(
        domain_rows,
        [
            "Domain", "Lv", "Type", "SizeKB", "Human", "Line", "Sets", "Ways",
            "CalcKB", "CacheID", "SharedMap", "SharedList", "CPUs", "Primary",
        ],
    )

    print("")
    print("── Section 3: Per-cluster summary ─────────────────────────────────────────────")
    summary_rows = []
    for s in summaries:
        l2_str_parts = []
        for g in s.l2_groups:
            l2_str_parts.append(
                f"{g['size_human']}/{g['ways']}w[cpu{format_cpu_list(g['cpus']).replace(',', ',cpu')}]"
            )
        summary_rows.append([
            s.cluster_index,
            s.cluster_raw,
            format_cpu_list(s.cpus),
            f"{human_kb(s.l1d_kb)}/{s.l1d_ways}w",
            f"{human_kb(s.l1i_kb)}/{s.l1i_ways}w",
            " ".join(l2_str_parts),
            f"{human_kb(s.l3_kb)}/{s.l3_ways}w",
            s.l3_sets,
            s.l3_line_bytes,
        ])
    table_print(
        summary_rows,
        ["ClIdx", "ClRaw", "CPUs", "L1D", "L1I", "L2_distribution", "L3", "L3_sets", "L3_line"],
    )

    print("")
    print("── Section 4: Core groups ─────────────────────────────────────────────────────")
    cg_rows = []
    for g in core_groups:
        cg_rows.append([
            g.cluster_index,
            g.cluster_raw,
            g.group_id,
            g.label,
            format_cpu_list(g.cpus),
            g.max_freq_mhz,
            f"{human_kb(g.l1d_kb)}/{g.l1d_ways}w",
            f"{human_kb(g.l1i_kb)}/{g.l1i_ways}w",
            f"{human_kb(g.l2_kb)}/{g.l2_ways}w",
            g.l2_sets,
            g.label_source,
        ])
    table_print(
        cg_rows,
        ["ClIdx", "ClRaw", "Group", "Label", "CPUs", "MHz", "L1D", "L1I", "L2", "L2_sets", "LabelSource"],
    )

    print("")
    print("── Section 5: Cross-validation ────────────────────────────────────────────────")
    val_rows = []
    for r in sorted(rows, key=lambda x: (x.cpu_id if x.cpu_id is not None else -1, x.level if x.level is not None else -1, x.type)):
        val_rows.append([
            r.cpu_id,
            r.cache_index,
            r.level,
            r.type,
            r.size_kb,
            r.calc_kb,
            validation_status(r),
        ])
    table_print(val_rows, ["CPU", "Idx", "Lv", "Type", "sysfs_KB", "calc_KB", "Match"])

    print("")
    print("── Section 6: Topology diagram ────────────────────────────────────────────────")
    render_topology(rows, domains, platform=platform)


def box_line(content: str, width: int = 76) -> str:
    max_content = width - 4
    s = content[:max_content]
    return "│ " + s + " " * (max_content - len(s)) + " │"


def box_top(width: int = 76) -> str:
    return "┌" + "─" * (width - 2) + "┐"


def box_bottom(width: int = 76) -> str:
    return "└" + "─" * (width - 2) + "┘"


def box_sep(width: int = 76) -> str:
    return "│" + "┄" * (width - 2) + "│"


def render_topology(rows: List[CacheRow], domains: List[CacheDomain], platform: str) -> None:
    summaries = build_cluster_summaries(rows, domains)
    core_groups = build_core_groups(rows, platform=platform)

    by_cluster: Dict[int, List[CoreGroup]] = {}
    for g in core_groups:
        by_cluster.setdefault(g.cluster_index, []).append(g)

    for s in summaries:
        print("")
        print(box_top())
        print(box_line(f"Cluster index {s.cluster_index}  raw_id={s.cluster_raw}"))
        print(box_line(f"CPUs: cpu[{format_cpu_list(s.cpus)}]"))
        print(box_line(""))
        for g in by_cluster.get(s.cluster_index, []):
            label = g.label
            cpu_str = format_cpu_list(g.cpus)
            print(box_line(
                f"[{label} x{len(g.cpus)}] @{g.max_freq_mhz or '?'} MHz  "
                f"L1D/I: {human_kb(g.l1d_kb)}/{g.l1d_ways}w + {human_kb(g.l1i_kb)}/{g.l1i_ways}w"
            ))
            print(box_line(
                f"cpu[{cpu_str}]  private L2: {human_kb(g.l2_kb)}/{g.l2_ways}w  sets={g.l2_sets or '?'}"
            ))
            print(box_line(""))
        print(box_sep())
        print(box_line(
            f"Shared L3: {human_kb(s.l3_kb)}  {s.l3_ways or '?'}-way  "
            f"{s.l3_line_bytes or '?'}B/line  sets={s.l3_sets or '?'}"
        ))
        print(box_bottom())

    print("")
    print(box_top())
    print(box_line("System interconnect / SLC / DRAM"))
    print(box_line(""))
    if platform == "gb10":
        print(box_line("Platform profile: gb10"))
        print(box_line("SLC/DRAM/interconnect lines below are platform annotations, not sysfs-derived."))
        print(box_line("SLC: System Level Cache, shared beyond cluster scope, if enabled by platform."))
        print(box_line("DRAM: LPDDR5x 128GB, 256-bit x16ch, approx 273GB/s annotation."))
    else:
        print(box_line("Generic profile: no non-sysfs platform annotation emitted."))
        print(box_line("Use --platform gb10 only when you explicitly want GB10-specific notes."))
    print(box_bottom())

    print("")
    print("Notes:")
    print("  - Cache geometry is sysfs-derived.")
    print("  - CoreGroup labels are grouping labels unless platform-specific inference is enabled.")
    print("  - A/X labels under --platform gb10 are inferred from L2 size rule, not direct CPU ID register decoding.")


def render_json(rows: List[CacheRow], domains: List[CacheDomain], platform: str) -> None:
    notes = row_role_by_domain(rows, domains)
    summaries = build_cluster_summaries(rows, domains)
    core_groups = build_core_groups(rows, platform=platform)

    payload: Dict[str, Any] = {
        "schema_version": "cache-topology-v2",
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "platform": platform,
        "facts": {
            "source": "linux_sysfs",
            "platform_annotations_are_sysfs_derived": False,
        },
        "rows": [],
        "domains": [],
        "clusters": [],
        "core_groups": [],
        "validation": [],
    }

    for r in sorted(rows, key=lambda x: (x.cpu_id if x.cpu_id is not None else -1, x.cache_index if x.cache_index is not None else -1)):
        d = asdict(r)
        d["shared_cpus"] = list(r.shared_cpus)
        d["note"] = notes.get(row_identity(r), "?")
        payload["rows"].append(d)

    for dmn in domains:
        f = dmn.first
        payload["domains"].append({
            "domain_id": dmn.domain_id,
            "primary_cpu": dmn.primary_cpu,
            "cpus": dmn.cpu_list(),
            "level": f.level,
            "type": f.type,
            "size_kb": f.size_kb,
            "size_human": human_kb(f.size_kb),
            "line_bytes": f.line_bytes,
            "sets": f.sets,
            "ways": f.ways,
            "calc_kb": f.calc_kb,
            "cache_id": f.cache_id,
            "shared_cpu_map": f.shared_cpu_map,
            "shared_cpu_list": f.shared_cpu_list,
            "shared_cpus": list(f.shared_cpus),
        })

    for s in summaries:
        payload["clusters"].append(asdict(s))

    for g in core_groups:
        payload["core_groups"].append(asdict(g))

    for r in rows:
        payload["validation"].append({
            "cpu_id": r.cpu_id,
            "cache_index": r.cache_index,
            "level": r.level,
            "type": r.type,
            "sysfs_kb": r.size_kb,
            "calc_kb": r.calc_kb,
            "match": validation_status(r),
        })

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def render_csv(rows: List[CacheRow], domains: List[CacheDomain], outdir: str, platform: str) -> None:
    os.makedirs(outdir, exist_ok=True)

    notes = row_role_by_domain(rows, domains)
    summaries = build_cluster_summaries(rows, domains)
    core_groups = build_core_groups(rows, platform=platform)

    all_path = os.path.join(outdir, "cpu_cache_all.csv")
    domains_path = os.path.join(outdir, "cache_domains.csv")
    clusters_path = os.path.join(outdir, "cluster_summary.csv")
    groups_path = os.path.join(outdir, "core_groups.csv")
    validation_path = os.path.join(outdir, "cross_validation.csv")

    with open(all_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "cpu_id", "online", "cluster_index", "cluster_raw", "physical_package_id", "core_id",
            "max_freq_khz", "max_freq_mhz", "cache_index", "cache_id", "level", "type",
            "size_raw", "size_kb", "line_bytes", "sets", "ways", "calc_kb",
            "shared_cpu_map", "shared_cpu_list", "shared_cpus",
            "allocation_policy", "write_policy", "physical_line_partition", "note",
        ])
        for r in rows:
            w.writerow([
                r.cpu_id, r.online, r.cluster_index, r.cluster_raw, r.physical_package_id, r.core_id,
                r.max_freq_khz, r.max_freq_mhz, r.cache_index, r.cache_id, r.level, r.type,
                r.size_raw, r.size_kb, r.line_bytes, r.sets, r.ways, r.calc_kb,
                r.shared_cpu_map, r.shared_cpu_list, format_cpu_list(r.shared_cpus),
                r.allocation_policy, r.write_policy, r.physical_line_partition,
                notes.get(row_identity(r), "?"),
            ])

    with open(domains_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "domain_id", "primary_cpu", "cpus", "level", "type", "size_kb", "size_human",
            "line_bytes", "sets", "ways", "calc_kb", "cache_id", "shared_cpu_map",
            "shared_cpu_list", "shared_cpus",
        ])
        for d in domains:
            r = d.first
            w.writerow([
                d.domain_id, d.primary_cpu, format_cpu_list(d.cpu_list()), r.level, r.type,
                r.size_kb, human_kb(r.size_kb), r.line_bytes, r.sets, r.ways, r.calc_kb,
                r.cache_id, r.shared_cpu_map, r.shared_cpu_list, format_cpu_list(r.shared_cpus),
            ])

    with open(clusters_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "cluster_index", "cluster_raw", "cpus", "l1d_kb", "l1d_ways",
            "l1i_kb", "l1i_ways", "l2_distribution", "l3_kb", "l3_human",
            "l3_ways", "l3_sets", "l3_line_bytes",
        ])
        for s in summaries:
            l2_dist = []
            for g in s.l2_groups:
                l2_dist.append(
                    f"{g['size_human']}/{g['ways']}w[cpu{format_cpu_list(g['cpus']).replace(',', ',cpu')}]"
                )
            w.writerow([
                s.cluster_index, s.cluster_raw, format_cpu_list(s.cpus),
                s.l1d_kb, s.l1d_ways, s.l1i_kb, s.l1i_ways, " ".join(l2_dist),
                s.l3_kb, human_kb(s.l3_kb), s.l3_ways, s.l3_sets, s.l3_line_bytes,
            ])

    with open(groups_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "cluster_index", "cluster_raw", "group_id", "label", "label_source",
            "cpus", "max_freq_mhz", "l1d_kb", "l1d_ways", "l1i_kb", "l1i_ways",
            "l2_kb", "l2_human", "l2_ways", "l2_sets",
        ])
        for g in core_groups:
            w.writerow([
                g.cluster_index, g.cluster_raw, g.group_id, g.label, g.label_source,
                format_cpu_list(g.cpus), g.max_freq_mhz, g.l1d_kb, g.l1d_ways,
                g.l1i_kb, g.l1i_ways, g.l2_kb, human_kb(g.l2_kb), g.l2_ways, g.l2_sets,
            ])

    with open(validation_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cpu_id", "cache_index", "level", "type", "sysfs_kb", "calc_kb", "match"])
        for r in rows:
            w.writerow([r.cpu_id, r.cache_index, r.level, r.type, r.size_kb, r.calc_kb, validation_status(r)])

    print(f"CSV output -> {outdir}/")
    for p in [all_path, domains_path, clusters_path, groups_path, validation_path]:
        with open(p, "r", newline="") as f:
            row_count = max(0, sum(1 for _ in f) - 1)
        print(f"  {os.path.basename(p):28s}  {row_count} rows")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Model and render Linux CPU cache topology from raw TSV."
    )
    ap.add_argument("--input", "-i", default=None, help="Input raw TSV file. Default: stdin.")
    ap.add_argument("--table", action="store_true", help="Render human-readable table. Default.")
    ap.add_argument("--json", action="store_true", help="Render JSON.")
    ap.add_argument("--csv", action="store_true", help="Write CSV files.")
    ap.add_argument("--topology", action="store_true", help="Render topology diagram only.")
    ap.add_argument("--outdir", default="./cache_csv_out", help="CSV output directory.")
    ap.add_argument(
        "--platform",
        default="generic",
        choices=["generic", "gb10"],
        help="Platform profile. Default: generic. gb10 enables explicit GB10 annotations.",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    rows = read_tsv(args.input)
    if not rows:
        print("ERROR: no rows loaded from input", file=sys.stderr)
        return 1

    domains = build_domains(rows)

    selected = args.table or args.json or args.csv or args.topology
    if not selected:
        args.table = True

    if args.json:
        render_json(rows, domains, platform=args.platform)

    if args.csv:
        render_csv(rows, domains, outdir=args.outdir, platform=args.platform)

    if args.topology:
        render_topology(rows, domains, platform=args.platform)

    if args.table:
        render_table(rows, domains, platform=args.platform)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
