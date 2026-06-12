#!/usr/bin/env bash
# cache_info_collect.sh
# Sysfs raw collector for Linux CPU cache topology.
#
# Design:
#   - Bash only collects raw sysfs facts.
#   - No topology inference.
#   - No JSON/CSV rendering.
#   - Source-safe: main executes only when invoked directly.
#
# Output:
#   TSV with header by default.
#
# Usage:
#   ./cache_info_collect.sh
#   ./cache_info_collect.sh --no-header
#   ./cache_info_collect.sh --raw-out ./cache_raw.tsv
#
# Pipeline:
#   ./cache_info_collect.sh | python3 cache_info_model.py --table

set -o pipefail

CACHE_COLLECT_HEADER=1
CACHE_COLLECT_RAW_OUT=""

cache_collect_usage() {
  cat <<'EOF'
Usage:
  cache_info_collect.sh [options]

Options:
  --no-header          Do not print TSV header
  --raw-out PATH       Write TSV output to PATH
  -h, --help           Show help

Output columns:
  cpu_id
  online
  cluster_raw
  physical_package_id
  core_id
  max_freq_khz
  max_freq_mhz
  cache_index
  cache_id
  level
  type
  size_raw
  size_kb
  line_bytes
  sets
  ways
  calc_kb
  shared_cpu_map
  shared_cpu_list
  allocation_policy
  write_policy
  physical_line_partition
EOF
}

cache_collect_parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --no-header)
        CACHE_COLLECT_HEADER=0
        shift
        ;;
      --raw-out)
        CACHE_COLLECT_RAW_OUT="${2:-}"
        if [[ -z "$CACHE_COLLECT_RAW_OUT" ]]; then
          echo "ERROR: --raw-out requires PATH" >&2
          return 1
        fi
        shift 2
        ;;
      --raw-out=*)
        CACHE_COLLECT_RAW_OUT="${1#--raw-out=}"
        shift
        ;;
      -h|--help)
        cache_collect_usage
        exit 0
        ;;
      *)
        echo "ERROR: unknown option: $1" >&2
        cache_collect_usage >&2
        return 1
        ;;
    esac
  done
}

cache_collect_sysfs_read() {
  local path="$1"
  local default="${2:-?}"

  if [[ -r "$path" ]]; then
    # Keep single-line sysfs value.
    # tr removes potential newline only.
    tr -d '\n' < "$path"
  else
    printf '%s' "$default"
  fi
}

cache_collect_size_to_kb() {
  local raw="$1"
  raw="${raw//[[:space:]]/}"

  # Bash nocasematch is shell-global; save current state approximately.
  local had_nocasematch=0
  shopt -q nocasematch && had_nocasematch=1
  shopt -s nocasematch

  if [[ "$raw" =~ ^([0-9]+)K(B)?$ ]]; then
    echo "${BASH_REMATCH[1]}"
  elif [[ "$raw" =~ ^([0-9]+)M(B)?$ ]]; then
    echo $(( BASH_REMATCH[1] * 1024 ))
  elif [[ "$raw" =~ ^([0-9]+)G(B)?$ ]]; then
    echo $(( BASH_REMATCH[1] * 1024 * 1024 ))
  elif [[ "$raw" =~ ^([0-9]+)$ ]]; then
    echo $(( raw / 1024 ))
  else
    echo "?"
  fi

  if (( had_nocasematch == 0 )); then
    shopt -u nocasematch
  fi
}

cache_collect_expand_cpu_spec() {
  local spec="$1"
  local result=()
  local part a b i

  IFS=',' read -ra parts <<< "$spec"
  for part in "${parts[@]}"; do
    if [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then
      a="${BASH_REMATCH[1]}"
      b="${BASH_REMATCH[2]}"
      for (( i=a; i<=b; i++ )); do
        result+=("$i")
      done
    elif [[ "$part" =~ ^[0-9]+$ ]]; then
      result+=("$part")
    fi
  done

  printf '%s\n' "${result[@]}" | sort -n
}

cache_collect_get_online_cpus() {
  local online_path="/sys/devices/system/cpu/online"
  local spec

  if [[ -r "$online_path" ]]; then
    spec="$(cache_collect_sysfs_read "$online_path" "")"
    cache_collect_expand_cpu_spec "$spec"
    return
  fi

  # Fallback: enumerate cpu directories.
  local p cid
  for p in /sys/devices/system/cpu/cpu[0-9]*; do
    [[ -d "$p" ]] || continue
    cid="${p##*/cpu}"
    [[ "$cid" =~ ^[0-9]+$ ]] && echo "$cid"
  done | sort -n
}

cache_collect_cpu_online_state() {
  local cpu_id="$1"
  local online_file="/sys/devices/system/cpu/cpu${cpu_id}/online"

  # cpu0 may not have online file on some kernels; treat as online if directory exists.
  if [[ -r "$online_file" ]]; then
    cache_collect_sysfs_read "$online_file" "?"
  else
    if [[ -d "/sys/devices/system/cpu/cpu${cpu_id}" ]]; then
      echo "1"
    else
      echo "0"
    fi
  fi
}

cache_collect_print_header() {
  cat <<'EOF'
cpu_id	online	cluster_raw	physical_package_id	core_id	max_freq_khz	max_freq_mhz	cache_index	cache_id	level	type	size_raw	size_kb	line_bytes	sets	ways	calc_kb	shared_cpu_map	shared_cpu_list	allocation_policy	write_policy	physical_line_partition
EOF
}

cache_collect_cpu() {
  local cpu_id="$1"
  local base="/sys/devices/system/cpu/cpu${cpu_id}"
  local online cluster_raw physical_package_id core_id
  local max_freq_khz max_freq_mhz

  [[ -d "$base" ]] || return 0

  online="$(cache_collect_cpu_online_state "$cpu_id")"

  cluster_raw="$(cache_collect_sysfs_read "${base}/topology/cluster_id" "?")"
  physical_package_id="$(cache_collect_sysfs_read "${base}/topology/physical_package_id" "?")"
  if [[ "$cluster_raw" == "?" ]]; then
    cluster_raw="$physical_package_id"
  fi

  core_id="$(cache_collect_sysfs_read "${base}/topology/core_id" "?")"

  max_freq_khz="$(cache_collect_sysfs_read "${base}/cpufreq/cpuinfo_max_freq" "")"
  if [[ -z "$max_freq_khz" || "$max_freq_khz" == "?" ]]; then
    max_freq_khz="$(cache_collect_sysfs_read "${base}/cpufreq/scaling_max_freq" "0")"
  fi

  if [[ "$max_freq_khz" =~ ^[0-9]+$ && "$max_freq_khz" -gt 0 ]]; then
    max_freq_mhz=$(( max_freq_khz / 1000 ))
  else
    max_freq_mhz="?"
  fi

  local idx_path idx
  for idx_path in "${base}/cache/index"*; do
    [[ -d "$idx_path" ]] || continue

    idx="${idx_path##*/index}"

    local cache_id level type size_raw size_kb line_bytes sets ways calc_kb
    local shared_cpu_map shared_cpu_list allocation_policy write_policy physical_line_partition

    cache_id="$(cache_collect_sysfs_read "${idx_path}/id" "?")"
    level="$(cache_collect_sysfs_read "${idx_path}/level" "?")"
    type="$(cache_collect_sysfs_read "${idx_path}/type" "?")"
    size_raw="$(cache_collect_sysfs_read "${idx_path}/size" "?")"
    size_kb="$(cache_collect_size_to_kb "$size_raw")"

    line_bytes="$(cache_collect_sysfs_read "${idx_path}/coherency_line_size" "?")"
    sets="$(cache_collect_sysfs_read "${idx_path}/number_of_sets" "?")"
    ways="$(cache_collect_sysfs_read "${idx_path}/ways_of_associativity" "?")"

    if [[ "$ways" =~ ^[0-9]+$ && "$sets" =~ ^[0-9]+$ && "$line_bytes" =~ ^[0-9]+$ ]]; then
      calc_kb=$(( ways * sets * line_bytes / 1024 ))
    else
      calc_kb="?"
    fi

    shared_cpu_map="$(cache_collect_sysfs_read "${idx_path}/shared_cpu_map" "?")"
    shared_cpu_list="$(cache_collect_sysfs_read "${idx_path}/shared_cpu_list" "")"

    allocation_policy="$(cache_collect_sysfs_read "${idx_path}/allocation_policy" "")"
    write_policy="$(cache_collect_sysfs_read "${idx_path}/write_policy" "")"
    physical_line_partition="$(cache_collect_sysfs_read "${idx_path}/physical_line_partition" "")"

    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$cpu_id" \
      "$online" \
      "$cluster_raw" \
      "$physical_package_id" \
      "$core_id" \
      "$max_freq_khz" \
      "$max_freq_mhz" \
      "$idx" \
      "$cache_id" \
      "$level" \
      "$type" \
      "$size_raw" \
      "$size_kb" \
      "$line_bytes" \
      "$sets" \
      "$ways" \
      "$calc_kb" \
      "$shared_cpu_map" \
      "$shared_cpu_list" \
      "$allocation_policy" \
      "$write_policy" \
      "$physical_line_partition"
  done
}

cache_collect_main() {
  cache_collect_parse_args "$@" || return 1

  local tmp_out=""
  if [[ -n "$CACHE_COLLECT_RAW_OUT" ]]; then
    tmp_out="$(mktemp)"
  fi

  {
    if (( CACHE_COLLECT_HEADER == 1 )); then
      cache_collect_print_header
    fi

    local cpu_id
    while IFS= read -r cpu_id; do
      [[ -n "$cpu_id" ]] || continue
      cache_collect_cpu "$cpu_id"
    done < <(cache_collect_get_online_cpus)
  } | {
    if [[ -n "$CACHE_COLLECT_RAW_OUT" ]]; then
      cat > "$tmp_out"
      mkdir -p "$(dirname "$CACHE_COLLECT_RAW_OUT")"
      mv "$tmp_out" "$CACHE_COLLECT_RAW_OUT"
      echo "Raw TSV output -> ${CACHE_COLLECT_RAW_OUT}" >&2
    else
      cat
    fi
  }
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  cache_collect_main "$@"
fi
