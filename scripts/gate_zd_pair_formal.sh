#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! command -v yosys >/dev/null 2>&1; then
  echo "EISA_H_ZD_PAIR_FORMAL_BLOCKED reason=yosys_unavailable" >&2
  exit 42
fi
YOSYS_VERSION="$(yosys -V | awk '{print $2}')"
if [[ "$YOSYS_VERSION" != "0.33" ]]; then
  printf 'EISA_H_ZD_PAIR_FORMAL_BLOCKED reason=unsupported_yosys_version observed=%s expected=0.33\n' \
    "$YOSYS_VERSION" >&2
  exit 42
fi

run_proof() {
  local name="$1" rc
  set +e
  (cd "$ROOT" && timeout 1800s yosys -Q -T \
    -s scripts/yosys/formal_zd_pair_v1.ys > "$TMP/$name.log" 2>&1)
  rc=$?
  set -e
  if [[ "$rc" == "124" || "$rc" == "137" ]]; then
    printf 'EISA_H_ZD_PAIR_FORMAL_BLOCKED reason=timeout run=%s rc=%s\n' "$name" "$rc" >&2
    exit 42
  fi
  if [[ "$rc" != "0" ]]; then
    printf 'EISA_H_ZD_PAIR_FORMAL_FAIL run=%s rc=%s\n' "$name" "$rc" >&2
    tail -60 "$TMP/$name.log" >&2
    exit 1
  fi
}

run_proof primary
run_proof replay
cmp "$TMP/primary.log" "$TMP/replay.log"

python3 - "$TMP/primary.log" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
status = re.findall(r"Found (\d+) \$equiv cells in equiv:\n  Of those cells (\d+) are proven and (\d+) are unproven\.", text)
if len(status) != 1:
    raise SystemExit(f"unexpected final equivalence status count: {len(status)}")
cells, proven, unproven = map(int, status[0])
if cells <= 0 or proven != cells or unproven != 0:
    raise SystemExit(f"invalid proof totals: {cells}/{proven}/{unproven}")
print(f"EISA_H_ZD_PAIR_FORMAL_CANDIDATE equiv_cells={cells} proven={proven} unproven={unproven}")
PY
printf 'proof_log_sha256=%s\n' "$(sha256sum "$TMP/primary.log" | cut -d' ' -f1)"

VALIDATION="$(python3 "$ROOT/tools/eisa_h/validate_formal_receipt.py" \
  "$ROOT" "$TMP/primary.log")"
[[ "$VALIDATION" == EISA_H_ZD_PAIR_FORMAL_VALIDATION_PASS* ]]

printf '%s\n' \
  "EISA_H_ZD_PAIR_FORMAL_GATE_PASS" \
  "formal=eisa_h.sedenion_zd_pair.formal.v1" \
  "$VALIDATION" \
  "deterministic_replay=VERIFIED tool=yosys version=$YOSYS_VERSION" \
  "formal_surface=OBSERVABLE_SYNC_CONDITIONAL_TEMPORAL_INDUCTION_NON_DIVERGENCE" \
  "reset_anchor=SEPARATE_POST_SYNTHESIS_SIMULATION_RECEIPT arbitrary_initial_state_equivalence=NOT_CLAIMED formal_equivalence_without_precondition=NOT_CLAIMED"
