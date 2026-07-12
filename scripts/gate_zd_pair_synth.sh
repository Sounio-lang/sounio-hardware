#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! command -v yosys >/dev/null 2>&1; then
  printf '%s\n' "EISA_H_ZD_PAIR_SYNTH_BLOCKED reason=yosys_unavailable" >&2
  exit 42
fi
YOSYS_VERSION="$(yosys -V | awk '{print $2}')"
if [[ "$YOSYS_VERSION" != "0.33" ]]; then
  printf 'EISA_H_ZD_PAIR_SYNTH_BLOCKED reason=unsupported_yosys_version observed=%s expected=0.33\n' \
    "$YOSYS_VERSION" >&2
  exit 42
fi

bash "$ROOT/scripts/gate_zd_pair_contract.sh" > "$TMP/contract.log"
bash "$ROOT/scripts/gate_zd_pair_rtl.sh" > "$TMP/rtl.log"
grep -Fx "EISA_H_ZD_PAIR_RTL_GATE_PASS" "$TMP/rtl.log" >/dev/null
python3 "$ROOT/tools/eisa_h/check_basis_rom.py" "$ROOT" > "$TMP/basis-rom.log"
grep -F "EISA_H_BASIS_ROM_PASS " "$TMP/basis-rom.log" >/dev/null

run_synthesis() {
  local name="$1"
  local receipt_command
  receipt_command="tee -o $TMP/$name-stat.json stat -json; write_json $TMP/$name-netlist.json"
  if (cd "$ROOT" && timeout 120s yosys -Q \
      -s scripts/yosys/synth_zd_pair_v1.ys -p "$receipt_command" > "$TMP/$name-yosys.log" 2>&1); then
    :
  else
    local rc=$?
    if [[ "$rc" == "124" || "$rc" == "137" ]]; then
      printf 'EISA_H_ZD_PAIR_SYNTH_BLOCKED run=%s reason=timeout rc=%s\n' "$name" "$rc" >&2
      tail -40 "$TMP/$name-yosys.log" >&2
      exit 42
    fi
    printf 'EISA_H_ZD_PAIR_SYNTH_FAIL run=%s rc=%s\n' "$name" "$rc" >&2
    tail -40 "$TMP/$name-yosys.log" >&2
    exit 1
  fi
  grep -F "Found and reported 0 problems." "$TMP/$name-yosys.log" >/dev/null
  grep -F "End of script." "$TMP/$name-yosys.log" >/dev/null
  local warning_count
  warning_count="$(grep -c '^Warning:' "$TMP/$name-yosys.log" || true)"
  if [[ "$warning_count" != "6" ]] || grep '^Warning:' "$TMP/$name-yosys.log" | \
      grep -Ev '^Warning: Replacing memory \\(lhs|rhs|lhs_latched|rhs_latched|accumulator|product) with list of registers\.' >/dev/null; then
    printf 'unexpected Yosys warning surface in run %s\n' "$name" >&2
    grep '^Warning:' "$TMP/$name-yosys.log" >&2 || true
    exit 1
  fi
}

run_synthesis a
run_synthesis b
cmp "$TMP/a-stat.json" "$TMP/b-stat.json"
cmp "$TMP/a-netlist.json" "$TMP/b-netlist.json"

VALIDATION="$(python3 "$ROOT/tools/eisa_h/validate_synth_receipt.py" \
  "$ROOT" "$TMP/a-stat.json" "$TMP/a-netlist.json")"
[[ "$VALIDATION" == EISA_H_ZD_PAIR_SYNTH_VALIDATION_PASS* ]]

MUTATION_COUNT=0
python3 - "$ROOT/spec/eisa_h/sedenion_zd_pair_synth_v1.json" "$TMP/manifest-tamper.json" <<'PY'
import json
import pathlib
import sys

source, target = map(pathlib.Path, sys.argv[1:])
value = json.loads(source.read_text(encoding="utf-8"))
value["reference_statistics"]["num_cells"] += 1
target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
PY
if python3 "$ROOT/tools/eisa_h/validate_synth_receipt.py" \
  "$ROOT" "$TMP/a-stat.json" "$TMP/a-netlist.json" "$TMP/manifest-tamper.json" >/dev/null 2>&1; then
  printf '%s\n' "synthesis manifest mutation unexpectedly passed" >&2
  exit 1
fi
MUTATION_COUNT=$((MUTATION_COUNT + 1))

python3 - "$TMP/a-stat.json" "$TMP/stat-tamper.json" <<'PY'
import json
import pathlib
import sys

source, target = map(pathlib.Path, sys.argv[1:])
value = json.loads(source.read_text(encoding="utf-8"))
value["modules"]["\\eisa_h_sed16_zd_pair_v1"]["num_cells"] += 1
target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
PY
if python3 "$ROOT/tools/eisa_h/validate_synth_receipt.py" \
  "$ROOT" "$TMP/stat-tamper.json" "$TMP/a-netlist.json" >/dev/null 2>&1; then
  printf '%s\n' "synthesis statistics mutation unexpectedly passed" >&2
  exit 1
fi
MUTATION_COUNT=$((MUTATION_COUNT + 1))

python3 - "$TMP/a-netlist.json" "$TMP/netlist-tamper.json" <<'PY'
import json
import pathlib
import sys

source, target = map(pathlib.Path, sys.argv[1:])
value = json.loads(source.read_text(encoding="utf-8"))
value["modules"]["eisa_h_sed16_zd_pair_v1"]["ports"]["product_flat"]["bits"].pop()
target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
PY
if python3 "$ROOT/tools/eisa_h/validate_synth_receipt.py" \
  "$ROOT" "$TMP/a-stat.json" "$TMP/netlist-tamper.json" >/dev/null 2>&1; then
  printf '%s\n' "synthesized port mutation unexpectedly passed" >&2
  exit 1
fi
MUTATION_COUNT=$((MUTATION_COUNT + 1))

sed "s/256'hcd4c/256'hdd4c/" "$ROOT/rtl/eisa_h_sed16_zd_pair_v1.sv" > "$TMP/rtl-rom-tamper.sv"
if python3 "$ROOT/tools/eisa_h/check_basis_rom.py" "$ROOT" "$TMP/rtl-rom-tamper.sv" >/dev/null 2>&1; then
  printf '%s\n' "basis ROM mutation unexpectedly passed" >&2
  exit 1
fi
MUTATION_COUNT=$((MUTATION_COUNT + 1))

STAT_SHA="$(sha256sum "$TMP/a-stat.json" | cut -d' ' -f1)"
NETLIST_SHA="$(sha256sum "$TMP/a-netlist.json" | cut -d' ' -f1)"
RECIPE_SHA="$(sha256sum "$ROOT/scripts/yosys/synth_zd_pair_v1.ys" | cut -d' ' -f1)"
MANIFEST_SHA="$(sha256sum "$ROOT/spec/eisa_h/sedenion_zd_pair_synth_v1.json" | cut -d' ' -f1)"

printf '%s\n' \
  "EISA_H_ZD_PAIR_SYNTH_GATE_PASS" \
  "synthesis=eisa_h.sedenion_zd_pair.synth.v1" \
  "cells=38133 sequential_cells=4122 processes=0 memories=0" \
  "same_tool_same_host_replay=VERIFIED mutations=$MUTATION_COUNT/$MUTATION_COUNT" \
  "stat_sha256=$STAT_SHA" \
  "netlist_sha256=$NETLIST_SHA" \
  "recipe_sha256=$RECIPE_SHA" \
  "manifest_sha256=$MANIFEST_SHA" \
  "tool=yosys version=$YOSYS_VERSION target=generic-cell-netlist" \
  "execution_surface=generic_synthesis equivalence=NOT_CLAIMED timing=NOT_CLAIMED silicon=NOT_CLAIMED"
