#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! command -v iverilog >/dev/null 2>&1 || ! command -v vvp >/dev/null 2>&1; then
  printf '%s\n' "EISA_H_ZD_PAIR_RTL_BLOCKED reason=iverilog_unavailable" >&2
  exit 42
fi

bash "$ROOT/scripts/gate_zd_pair_contract.sh" > "$TMP/contract.log"
grep -Fx "EISA_H_ZD_PAIR_CONTRACT_PASS" "$TMP/contract.log" >/dev/null
python3 "$ROOT/tools/eisa_h/validate_rtl_manifest.py" "$ROOT" > "$TMP/manifest.log"
grep -F "RTL_MANIFEST_PASS " "$TMP/manifest.log" >/dev/null
python3 "$ROOT/tools/eisa_h/check_basis_rom.py" "$ROOT" > "$TMP/basis-rom.log"
grep -F "EISA_H_BASIS_ROM_PASS " "$TMP/basis-rom.log" >/dev/null

iverilog -g2012 -Wall -s tb_sed16_zd_pair_v1 \
  -o "$TMP/tb_sed16_zd_pair_v1.vvp" \
  "$ROOT/rtl/eisa_h_sed16_zd_pair_v1.sv" \
  "$ROOT/tb/eisa_h/tb_sed16_zd_pair_v1.sv"
EXPECTED_RECEIPT="EISA_H_ZD_PAIR_RTL_PASS rtl_cases=15 contract_cases=9 adversarial_cases=6 basis_sign_combinations=1024 interface_cases=1 mac_cycles=256 latency_cycles=257 handshake=VERIFIED"
vvp "$TMP/tb_sed16_zd_pair_v1.vvp" | tee "$TMP/rtl.log"
grep -Fx "$EXPECTED_RECEIPT" "$TMP/rtl.log" >/dev/null
vvp "$TMP/tb_sed16_zd_pair_v1.vvp" > "$TMP/rtl-replay.log"
cmp "$TMP/rtl.log" "$TMP/rtl-replay.log"

MUTATION_COUNT=0
run_rtl_mutation() {
  local name="$1"
  local expression="$2"
  sed "$expression" "$ROOT/rtl/eisa_h_sed16_zd_pair_v1.sv" > "$TMP/rtl-$name.sv"
  iverilog -g2012 -s tb_sed16_zd_pair_v1 \
    -o "$TMP/tb-$name.vvp" \
    "$TMP/rtl-$name.sv" \
    "$ROOT/tb/eisa_h/tb_sed16_zd_pair_v1.sv"
  if vvp "$TMP/tb-$name.vvp" > "$TMP/$name.log" 2>&1; then
    printf 'RTL mutation unexpectedly passed: %s\n' "$name" >&2
    exit 1
  fi
  MUTATION_COUNT=$((MUTATION_COUNT + 1))
}

run_rtl_mutation sign "s/256'hcd4c/256'hdd4c/"
run_rtl_mutation counter "s/mac_cycles <= mac_cycles + 9'd1;/mac_cycles <= mac_cycles + 9'd0;/"
run_rtl_mutation threshold 's/1518500249/1518500250/g'
run_rtl_mutation signedness 's/raw = left \* right;/raw = left;/'
run_rtl_mutation handshake "s/assign ready = !busy && !finalize;/assign ready = 1'b1;/"

python3 - "$ROOT/spec/eisa_h/sedenion_zd_pair_rtl_v1.json" "$TMP/manifest-tamper.json" <<'PY'
import json
import pathlib
import sys

source, target = map(pathlib.Path, sys.argv[1:])
value = json.loads(source.read_text(encoding="utf-8"))
value["artifacts"]["rtl_sha256"] = "0" * 64
target.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
PY
if python3 "$ROOT/tools/eisa_h/validate_rtl_manifest.py" "$ROOT" "$TMP/manifest-tamper.json" > "$TMP/manifest-tamper.log" 2>&1; then
  printf '%s\n' "RTL manifest mutation unexpectedly passed" >&2
  exit 1
fi
MUTATION_COUNT=$((MUTATION_COUNT + 1))

RTL_SHA="$(sha256sum "$ROOT/rtl/eisa_h_sed16_zd_pair_v1.sv" | cut -d' ' -f1)"
TB_SHA="$(sha256sum "$ROOT/tb/eisa_h/tb_sed16_zd_pair_v1.sv" | cut -d' ' -f1)"
MANIFEST_SHA="$(sha256sum "$ROOT/spec/eisa_h/sedenion_zd_pair_rtl_v1.json" | cut -d' ' -f1)"
IVERILOG_VERSION="$(iverilog -V 2>/dev/null | awk 'NR == 1 { print $4 }')"

printf '%s\n' \
  "EISA_H_ZD_PAIR_RTL_GATE_PASS" \
  "implementation=eisa_h.sedenion_zd_pair.rtl.v1" \
  "semantic_cases=10 rtl_cases=9 adversarial_cases=6 basis_sign_combinations=1024 interface_cases=1" \
  "datapath=iterative-single-mac mac_cycles=256 finalize_cycles=1 latency_cycles=257 handshake=VERIFIED" \
  "determinism=VERIFIED mutations=$MUTATION_COUNT/$MUTATION_COUNT" \
  "rtl_sha256=$RTL_SHA" \
  "testbench_sha256=$TB_SHA" \
  "manifest_sha256=$MANIFEST_SHA" \
  "simulator=iverilog version=$IVERILOG_VERSION" \
  "execution_surface=rtl_simulation synthesis=NOT_CLAIMED silicon=NOT_CLAIMED"
