#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="$ROOT/tools/eisa_h/pireus_material_parity_oracle.py"
SCHEMA="$ROOT/spec/eisa_h/pireus_material_parity_v1.schema.json"
CONTRACT="$ROOT/spec/eisa_h/pireus_material_parity_v1.json"
VECTORS="$ROOT/vectors/eisa_h/pireus_material_parity_v1.json"
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
ACCEPTED="$(grep -c 'ACCEPTED_MATERIAL_PARITY' "$TMP/receipts-a.jsonl" || true)"
REJECTED="$(grep -c 'REJECTED_RECEIPT' "$TMP/receipts-a.jsonl" || true)"
RECEIPT_SHA="$(sha256sum "$TMP/receipts-a.jsonl" | cut -d' ' -f1)"
CONTRACT_SHA="$(sha256sum "$CONTRACT" | cut -d' ' -f1)"

printf '%s\n' \
  "EISA_H_PIREUS_MATERIAL_PARITY_CONTRACT_PASS" \
  "contract=eisa_h.pireus_material_parity.v1" \
  "cases=$CASE_COUNT accepted=$ACCEPTED rejected=$REJECTED mutations=$MUTATION_COUNT/$MUTATION_COUNT determinism=VERIFIED" \
  "contract_sha256=$CONTRACT_SHA" \
  "receipt_sha256=$RECEIPT_SHA" \
  "execution_surface=software_oracle validates=receipt_admissibility_only hardware=NOT_MEASURED"
