#!/usr/bin/env bash
# gb10_cache_info.sh  v1.9
# fix1: source 模式下 SEEN_DOMAIN/TAGGED_ROWS 等全局变量残留导致所有 tag=shared
# fix2: source 模式下 declare -A 数组跨次执行状态污染
# 修复策略：所有全局状态变量在脚本入口处强制 unset + 重新声明

# ─── 全局状态强制重置（兼容 bash 和 source 两种执行方式）────────────────────────
unset SEEN_DOMAIN TAGGED_ROWS ALL_ROWS ONLINE_CPUS
unset _BOX_TOP _BOX_BOT _BOX_SEP _BOX_BLK BOX_INNER
declare -A SEEN_DOMAIN
TAGGED_ROWS=()
ALL_ROWS=()

OUTPUT_MODE="table"
CSV_DIR="./cache_csv_out"

for arg in "$@"; do
  case "$arg" in
    --json)     OUTPUT_MODE="json" ;;
    --csv)      OUTPUT_MODE="csv"  ;;
    --outdir=*) CSV_DIR="${arg#--outdir=}" ;;
  esac
done

# ─── 工具函数 ─────────────────────────────────────────────────────────────────
sysfs_read() {
  local path="$1" default="${2:-?}"
  [[ -r "$path" ]] && cat "$path" || echo "$default"
}

size_to_kb() {
  local raw="$1"
  if   [[ "$raw" =~ ^([0-9]+)K$ ]]; then echo "${BASH_REMATCH[1]}"
  elif [[ "$raw" =~ ^([0-9]+)M$ ]]; then echo $(( BASH_REMATCH[1] * 1024 ))
  elif [[ "$raw" =~ ^([0-9]+)$  ]]; then echo $(( raw / 1024 ))
  else echo "?"
  fi
}

kb_to_human() {
  local kb="$1"
  if [[ "$kb" =~ ^[0-9]+$ ]]; then
    if (( kb >= 1024 && kb % 1024 == 0 )); then
      echo "$(( kb / 1024 ))MB"
    else
      echo "${kb}KB"
    fi
  else
    echo "$kb"
  fi
}

decode_cpumap() {
  local hex="${1//,/}"; hex="${hex##0x}"
  local cpus="" bit=0
  local rev_hex; rev_hex=$(echo "$hex" | rev)
  local i char nibble b
  for (( i=0; i<${#rev_hex}; i++ )); do
    char="${rev_hex:$i:1}"
    nibble=$(( 16#$char ))
    for (( b=0; b<4; b++ )); do
      (( (nibble >> b) & 1 )) && cpus+="${bit},"
      (( bit++ ))
    done
  done
  echo "${cpus%,}"
}

get_online_cpus() {
  local online_path="/sys/devices/system/cpu/online"
  local result=()
  if [[ -r "$online_path" ]]; then
    local spec; spec=$(cat "$online_path")
    local part a b i
    IFS=',' read -ra parts <<< "$spec"
    for part in "${parts[@]}"; do
      if [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then
        a="${BASH_REMATCH[1]}"; b="${BASH_REMATCH[2]}"
        for (( i=a; i<=b; i++ )); do result+=("$i"); done
      elif [[ "$part" =~ ^[0-9]+$ ]]; then
        result+=("$part")
      fi
    done
  else
    for p in /sys/devices/system/cpu/cpu[0-9]*/topology; do
      [[ -d "$p" ]] || continue
      local cid="${p%/topology}"; cid="${cid##*/cpu}"
      [[ "$cid" =~ ^[0-9]+$ ]] && result+=("$cid")
    done
    IFS=$'\n' result=($(sort -n <<<"${result[*]}")); unset IFS
  fi
  echo "${result[@]}"
}

collect_cpu() {
  local cpu_id="$1"
  local base="/sys/devices/system/cpu/cpu${cpu_id}"
  local cluster core freq_mhz freq_raw

  cluster=$(sysfs_read "${base}/topology/cluster_id" \
            "$(sysfs_read "${base}/topology/physical_package_id" "?")")
  core=$(sysfs_read "${base}/topology/core_id" "?")
  freq_raw=$(sysfs_read "${base}/cpufreq/cpuinfo_max_freq" \
             "$(sysfs_read "${base}/cpufreq/scaling_max_freq" "0")")
  if [[ "$freq_raw" =~ ^[0-9]+$ && "$freq_raw" -gt 0 ]]; then
    freq_mhz=$(( freq_raw / 1000 ))
  else
    freq_mhz="?"
  fi

  local idx_path
  for idx_path in "${base}/cache/index"*; do
    [[ -d "$idx_path" ]] || continue
    local lv tp size_raw size_kb line sets ways shared_map calc_kb
    lv=$(sysfs_read "${idx_path}/level" "?")
    tp=$(sysfs_read "${idx_path}/type"  "?")
    size_raw=$(sysfs_read "${idx_path}/size" "0K")
    line=$(sysfs_read "${idx_path}/coherency_line_size"   "?")
    sets=$(sysfs_read "${idx_path}/number_of_sets"        "?")
    ways=$(sysfs_read "${idx_path}/ways_of_associativity" "?")
    shared_map=$(sysfs_read "${idx_path}/shared_cpu_map"  "?")
    size_kb=$(size_to_kb "$size_raw")
    if [[ "$ways" =~ ^[0-9]+$ && "$sets" =~ ^[0-9]+$ && "$line" =~ ^[0-9]+$ ]]; then
      calc_kb=$(( ways * sets * line / 1024 ))
    else
      calc_kb="?"
    fi
    echo "${cpu_id}|${cluster}|${core}|${freq_mhz}|${lv}|${tp}|${size_kb}|${line}|${sets}|${ways}|${calc_kb}|${shared_map}"
  done
}

# ─── 主采集 ───────────────────────────────────────────────────────────────────
ONLINE_CPUS=( $(get_online_cpus) )
for cpu_id in "${ONLINE_CPUS[@]}"; do
  while IFS= read -r row; do
    ALL_ROWS+=("$row")
  done < <(collect_cpu "$cpu_id")
done

# ─── 共享域去重标注 ────────────────────────────────────────────────────────────
# SEEN_DOMAIN 已在脚本入口 unset+重声明，此处直接使用
for row in "${ALL_ROWS[@]}"; do
  IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap <<< "$row"
  local_key="${lv}|${tp}|${smap}"
  if [[ -z "${SEEN_DOMAIN[$local_key]+x}" ]]; then
    SEEN_DOMAIN[$local_key]="$cid"
    tag="primary"
  else
    tag="shared→cpu${SEEN_DOMAIN[$local_key]}"
  fi
  TAGGED_ROWS+=("${row}|${tag}")
done

# ─── build_cluster_rows ───────────────────────────────────────────────────────
build_cluster_rows() {
  local row cid cl co fr lv tp sz line sets ways calc smap tag
  local cpu_cl_key seen_cpu_cluster="" l2raw l2_str l3_human
  local entry ecpu esz cpulist
  # source 安全：函数内 declare -A 是 local 作用域，每次调用自动重置
  declare -A CL_CPUSET CL_L1D CL_L1I CL_L3 CL_L3W CL_L3S CL_L2

  for row in "${TAGGED_ROWS[@]}"; do
    IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap tag <<< "$row"
    [[ "$tag" != "primary" ]] && continue
    cpu_cl_key="${cid}:${cl}"
    if [[ "$seen_cpu_cluster" != *"|${cpu_cl_key}|"* ]]; then
      seen_cpu_cluster+="|${cpu_cl_key}|"
      CL_CPUSET[$cl]+="${cid},"
    fi
    case "${lv}|${tp}" in
      "1|Data")        CL_L1D[$cl]="$sz" ;;
      "1|Instruction") CL_L1I[$cl]="$sz" ;;
      "2|Unified")     CL_L2[$cl]+="${cid}:${sz}," ;;
      "3|Unified")     CL_L3[$cl]="$sz"; CL_L3W[$cl]="$ways"; CL_L3S[$cl]="$sets" ;;
    esac
  done

  for cl in $(echo "${!CL_CPUSET[@]}" | tr ' ' '\n' | sort -n); do
    cpulist="${CL_CPUSET[$cl]%,}"
    l2raw="${CL_L2[$cl]:-}"
    declare -A L2_DIST=()
    IFS=',' read -ra l2entries <<< "$l2raw"
    for entry in "${l2entries[@]}"; do
      [[ -z "$entry" ]] && continue
      ecpu="${entry%%:*}"; esz="${entry##*:}"
      L2_DIST[$esz]+="${ecpu},"
    done
    l2_str=""
    for esz in $(echo "${!L2_DIST[@]}" | tr ' ' '\n' | sort -n); do
      local cpus_of_sz="${L2_DIST[$esz]%,}"
      l2_str+="$(kb_to_human $esz)[cpu${cpus_of_sz//,/,cpu}] "
    done
    unset L2_DIST
    l3_human=$(kb_to_human "${CL_L3[$cl]:-?}")
    echo "${cl}|${cpulist}|${CL_L1D[$cl]:-?}|${CL_L1I[$cl]:-?}|${l2_str% }|${l3_human}|${CL_L3W[$cl]:-?}|${CL_L3S[$cl]:-?}"
  done
}

# ─── box 绘图工具 ─────────────────────────────────────────────────────────────
BOX_INNER=70
_repeat() {
  local char="$1" n="$2" result="" i
  for (( i=0; i<n; i++ )); do result+="$char"; done
  echo "$result"
}
_init_box() {
  local dashes dots spaces
  dashes=$(_repeat "─" $BOX_INNER)
  dots=$(_repeat "┄" $BOX_INNER)
  spaces=$(_repeat " " $BOX_INNER)
  _BOX_TOP="┌${dashes}┐"
  _BOX_BOT="└${dashes}┘"
  _BOX_SEP="│${dots}│"
  _BOX_BLK="│${spaces}│"
}
box_top()    { echo "$_BOX_TOP"; }
box_bottom() { echo "$_BOX_BOT"; }
box_sep()    { echo "$_BOX_SEP"; }
box_blank()  { echo "$_BOX_BLK"; }
box_line() {
  local content="$1"
  local max_content=$(( BOX_INNER - 1 ))
  local content_len="${#content}"
  if (( content_len > max_content )); then
    content="${content:0:$max_content}"
    content_len=$max_content
  fi
  local pad_n=$(( max_content - content_len ))
  local pad; pad=$(_repeat " " $pad_n)
  echo "│ ${content}${pad}│"
}
_init_box   # source 安全：_BOX_* 是普通全局变量，每次脚本入口 unset 后重新赋值

# ─── Section 5: 拓扑图 ────────────────────────────────────────────────────────
print_topology_diagram() {
  local row cid cl co fr lv tp sz line sets ways calc smap tag
  local cpu_cl_key a_cpus x_cpus a_freq x_freq a_l2 x_l2 l3 l3ways
  local a_count x_count _arr
  # 函数内 declare -A = local，每次调用自动从空白开始，source 安全
  declare -A CL_A_CPUS CL_X_CPUS CL_A_FREQ CL_X_FREQ CL_A_L2 CL_X_L2
  declare -A CL_L3KB CL_L3WAYS CL_CPU_SEEN

  for row in "${TAGGED_ROWS[@]}"; do
    IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap tag <<< "$row"

    # L3：无条件采集，first-write-wins
    if [[ "${lv}|${tp}" == "3|Unified" && -z "${CL_L3KB[$cl]+x}" ]]; then
      CL_L3KB[$cl]="$sz"
      CL_L3WAYS[$cl]="$ways"
    fi

    # L2 + CPU list：仅 primary 行
    [[ "$tag" != "primary" ]] && continue

    if [[ "${lv}|${tp}" == "2|Unified" ]]; then
      cpu_cl_key="${cid}:${cl}"
      if [[ -z "${CL_CPU_SEEN[$cpu_cl_key]+x}" ]]; then
        CL_CPU_SEEN[$cpu_cl_key]=1
        if [[ "$sz" -le 512 ]]; then
          CL_A_CPUS[$cl]+="${cid},"
          CL_A_FREQ[$cl]="$fr"
          CL_A_L2[$cl]=$(kb_to_human "$sz")
        else
          CL_X_CPUS[$cl]+="${cid},"
          CL_X_FREQ[$cl]="$fr"
          CL_X_L2[$cl]=$(kb_to_human "$sz")
        fi
      fi
    fi
  done

  if [[ ${#CL_L3KB[@]} -eq 0 ]]; then
    echo "  [No topology data collected — L3 not found in sysfs]"
    return
  fi

  for cl in $(echo "${!CL_L3KB[@]}" | tr ' ' '\n' | sort -n); do
    a_cpus="${CL_A_CPUS[$cl]%,}"
    x_cpus="${CL_X_CPUS[$cl]%,}"
    a_freq="${CL_A_FREQ[$cl]:-?}"
    x_freq="${CL_X_FREQ[$cl]:-?}"
    a_l2="${CL_A_L2[$cl]:-?}"
    x_l2="${CL_X_L2[$cl]:-?}"
    l3=$(kb_to_human "${CL_L3KB[$cl]}")
    l3ways="${CL_L3WAYS[$cl]:-16}"
    a_count=0; x_count=0
    if [[ -n "$a_cpus" ]]; then
      IFS=',' read -ra _arr <<< "$a_cpus"; a_count=${#_arr[@]}
    fi
    if [[ -n "$x_cpus" ]]; then
      IFS=',' read -ra _arr <<< "$x_cpus"; x_count=${#_arr[@]}
    fi

    echo ""
    box_top
    box_line "Cluster ${cl}"
    box_blank
    box_line "  [A-core x${a_count}]  @${a_freq} MHz   L1D/I: 64KB/4w   L2: ${a_l2}/8w"
    box_line "  cpu[${a_cpus}]"
    box_blank
    box_line "  [X-core x${x_count}]  @${x_freq} MHz   L1D/I: 64KB/4w   L2: ${x_l2}/8w"
    box_line "  cpu[${x_cpus}]"
    box_blank
    box_sep
    box_line "  Shared L3: ${l3}   ${l3ways}-way   64B/line   all CPUs in cluster"
    box_bottom
  done

  echo ""
  box_top
  box_line "  System Interconnect  (cross-cluster via DSU/CMN Mesh)"
  box_blank
  box_line "  SLC (System Level Cache) — shared across all clusters"
  box_blank
  box_line "  DRAM: LPDDR5x   128GB   256-bit x 16ch   ~273 GB/s"
  box_bottom

  echo ""
  echo "  Note: L1D = L1I = 64KB / 4-way / 256-sets  (private per core)"
  echo "        L2: private per core | L3: shared within cluster only"
  echo "        Cross-cluster L3 access goes via System Interconnect"
}

# ─── print_table ──────────────────────────────────────────────────────────────
print_table() {
  local row cid cl co fr lv tp sz line sets ways calc smap tag match cpu_list

  echo ""
  printf "═%.0s" {1..100}; echo ""
  echo "  GB10 CPU Cache Topology    $(date '+%Y-%m-%d %H:%M:%S')"
  printf "═%.0s" {1..100}; echo ""
  echo ""

  echo "── Section 1: All CPUs ──────────────────────────────────────────────────────────"
  {
    echo "CPU|Cluster|Core|MaxMHz|Lv|Type|Size_KB|Line|Sets|Ways|Calc_KB|SharedMap|Note"
    for row in "${TAGGED_ROWS[@]}"; do echo "$row"; done
  } | column -t -s '|'

  echo ""
  echo "── Section 2: Unique Cache Domains ─────────────────────────────────────────────"
  {
    echo "Lv|Type|Size_KB|Line|Sets|Ways|Calc_KB|SharedMap|CPUs"
    for row in "${TAGGED_ROWS[@]}"; do
      IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap tag <<< "$row"
      [[ "$tag" != "primary" ]] && continue
      cpu_list=$(decode_cpumap "$smap")
      echo "${lv}|${tp}|${sz}|${line}|${sets}|${ways}|${calc}|${smap}|${cpu_list}"
    done
  } | sort -t'|' -k1,1n -k2,2 | column -t -s '|'

  echo ""
  echo "── Section 3: Per-Cluster Summary ──────────────────────────────────────────────"
  {
    echo "Cluster|CPUs|L1D_KB|L1I_KB|L2_distribution|L3|L3_ways|L3_sets"
    build_cluster_rows
  } | column -t -s '|'

  echo ""
  echo "── Section 4: Cross-validation ─────────────────────────────────────────────────"
  {
    echo "CPU|Lv|Type|sysfs_KB|calc_KB|Match"
    for row in "${TAGGED_ROWS[@]}"; do
      IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap tag <<< "$row"
      [[ "$tag" != "primary" ]] && continue
      if [[ "$sz" =~ ^[0-9]+$ && "$calc" =~ ^[0-9]+$ ]]; then
        [[ "$sz" -eq "$calc" ]] && match="OK" || match="MISMATCH"
      else
        match="?"
      fi
      echo "${cid}|${lv}|${tp}|${sz}|${calc}|${match}"
    done
  } | column -t -s '|'

  echo ""
  echo "── Section 5: Topology Diagram ─────────────────────────────────────────────────"
  print_topology_diagram

  echo ""
}

# ─── print_csv ────────────────────────────────────────────────────────────────
print_csv() {
  local row cid cl co fr lv tp sz line sets ways calc smap tag match cpu_list sz_human
  mkdir -p "$CSV_DIR"
  local ts; ts=$(date '+%Y%m%d_%H%M%S')

  local f1="${CSV_DIR}/cpu_cache_all.csv"
  {
    echo "cpu_id,cluster_id,core_id,max_freq_MHz,level,type,size_KB,line_bytes,sets,ways,calc_KB,shared_cpu_map,note"
    for row in "${TAGGED_ROWS[@]}"; do echo "${row//|/,}"; done
  } > "$f1"

  local f2="${CSV_DIR}/cache_domains.csv"
  {
    echo "level,type,size_KB,size_human,line_bytes,sets,ways,calc_KB,shared_cpu_map,cpu_list"
    for row in "${TAGGED_ROWS[@]}"; do
      IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap tag <<< "$row"
      [[ "$tag" != "primary" ]] && continue
      cpu_list=$(decode_cpumap "$smap")
      sz_human=$(kb_to_human "$sz")
      echo "${lv},${tp},${sz},${sz_human},${line},${sets},${ways},${calc},${smap},\"${cpu_list}\""
    done
  } | sort -t',' -k1,1n -k2,2 > "$f2"

  local f3="${CSV_DIR}/cluster_summary.csv"
  {
    echo "cluster_id,cpu_list,l1d_KB,l1i_KB,l2_distribution,l3_size,l3_ways,l3_sets"
    build_cluster_rows | while IFS='|' read -r cl cpus l1d l1i l2dist l3 l3w l3s; do
      echo "${cl},\"${cpus}\",${l1d},${l1i},\"${l2dist}\",${l3},${l3w},${l3s}"
    done
  } > "$f3"

  local f4="${CSV_DIR}/cross_validation.csv"
  {
    echo "cpu_id,level,type,sysfs_KB,calc_KB,match"
    for row in "${TAGGED_ROWS[@]}"; do
      IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap tag <<< "$row"
      [[ "$tag" != "primary" ]] && continue
      if [[ "$sz" =~ ^[0-9]+$ && "$calc" =~ ^[0-9]+$ ]]; then
        [[ "$sz" -eq "$calc" ]] && match="OK" || match="MISMATCH"
      else
        match="?"
      fi
      echo "${cid},${lv},${tp},${sz},${calc},${match}"
    done
  } > "$f4"

  echo "CSV output → ${CSV_DIR}/"
  echo ""
  local f fname rows
  for f in "$f1" "$f2" "$f3" "$f4"; do
    fname=$(basename "$f")
    rows=$(( $(wc -l < "$f") - 1 ))
    printf "  %-28s  %d rows\n" "$fname" "$rows"
  done
  echo ""
  echo "  Timestamp: ${ts}"
}

# ─── print_json ───────────────────────────────────────────────────────────────
print_json() {
  local row cid cl co fr lv tp sz line sets ways calc smap tag comma
  echo "["
  local total=${#TAGGED_ROWS[@]} i=0
  for row in "${TAGGED_ROWS[@]}"; do
    IFS='|' read -r cid cl co fr lv tp sz line sets ways calc smap tag <<< "$row"
    comma=","; (( i == total-1 )) && comma=""
    printf '  {"cpu":%s,"cluster":"%s","core":"%s","freq_MHz":"%s","level":%s,"type":"%s","size_KB":%s,"line":%s,"sets":%s,"ways":%s,"calc_KB":"%s","shared_map":"%s","note":"%s"}%s\n' \
      "$cid" "$cl" "$co" "$fr" "$lv" "$tp" "$sz" "$line" "$sets" "$ways" "$calc" "$smap" "$tag" "$comma"
    (( i++ ))
  done
  echo "]"
}

case "$OUTPUT_MODE" in
  table) print_table ;;
  csv)   print_csv   ;;
  json)  print_json  ;;
esac
