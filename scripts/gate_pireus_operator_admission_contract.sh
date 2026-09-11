#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="$ROOT/tools/eisa_h/pireus_operator_admission_oracle.py"
SCHEMA="$ROOT/spec/eisa_h/pireus_operator_admission_v1.schema.json"
CONTRACT="$ROOT/spec/eisa_h/pireus_operator_admission_v1.json"
VECTORS="$ROOT/vectors/eisa_h/pireus_operator_admission_v1.json"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PYTHONPYCACHEPREFIX="$TMP/pycache" python3 -m py_compile "$ORACLE"

SELFTEST_LINE="$(python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" --vectors "$VECTORS" --receipts "$TMP/receipts-a.jsonl" --selftest)"
if [[ ! "$SELFTEST_LINE" =~ ^MUTATION_SELFTEST_PASS\ caught=([0-9]+)$ ]]; then
  printf 'invalid mutation selftest receipt: %s\n' "$SELFTEST_LINE" >&2
  exit 1
fi
MUTATION_COUNT="${BASH_REMATCH[1]}"

python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" --vectors "$VECTORS" --receipts "$TMP/receipts-b.jsonl"
cmp "$TMP/receipts-a.jsonl" "$TMP/receipts-b.jsonl"

CASE_COUNT="$(wc -l < "$TMP/receipts-a.jsonl" | tr -d ' ')"
ACCEPTED="$(grep -c '"accepted":true' "$TMP/receipts-a.jsonl" || true)"
REJECTED="$(grep -c '"accepted":false' "$TMP/receipts-a.jsonl" || true)"
RECEIPT_SHA="$(sha256sum "$TMP/receipts-a.jsonl" | cut -d' ' -f1)"

# The reference operator is re-derived from the phase code here, independently
# of the contract file, so this line cannot be satisfied by editing the JSON.
python3 "$ORACLE" --emit 1128 > "$TMP/ref.json"
python3 - "$TMP/ref.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
expect = {"quadratic_code": 198, "affine_class": 26, "associator_defects": 1848,
          "commutator_defects": 90, "anticommutator_failures": 120,
          "square_negatives": 5, "unit_index": 0,
          "novel_relative_to_v1_grammar": True,
          "tensor_reconstruction_failures": 0}
bad = {k: (r[k], v) for k, v in expect.items() if r[k] != v}
if bad:
    raise SystemExit(f"reference operator drift: {bad}")
PY

printf '%s\n' \
  "EISA_H_PIREUS_OPERATOR_ADMISSION_CONTRACT_PASS" \
  "contract=eisa_h.pireus_operator_admission.v1" \
  "reference_operator=phase_code:1128 quadratic_code:198 affine_class:26" \
  "invariants=associator:1848 commutator:90 anticommutator:120 square_negatives:5" \
  "cases=$CASE_COUNT accepted=$ACCEPTED rejected=$REJECTED mutations=$MUTATION_COUNT/$MUTATION_COUNT determinism=VERIFIED" \
  "receipt_sha256=$RECEIPT_SHA" \
  "execution_surface=software_oracle validates=proposal_admissibility_only" \
  "utility=NOT_ESTABLISHED material_parity=NOT_MEASURED formal_v13_v14=OPEN"
