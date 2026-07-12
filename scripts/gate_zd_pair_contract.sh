#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="$ROOT/tools/eisa_h/zd_pair_oracle.py"
SCHEMA="$ROOT/spec/eisa_h/sedenion_zd_pair_v1.schema.json"
CONTRACT="$ROOT/spec/eisa_h/sedenion_zd_pair_v1.json"
VECTORS="$ROOT/vectors/eisa_h/sedenion_zd_pair_v1.json"
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
RECEIPT_SHA="$(sha256sum "$TMP/receipts-a.jsonl" | cut -d' ' -f1)"
TABLE_SHA="$(python3 "$ORACLE" --print-table-hash)"

printf '%s\n' \
  "EISA_H_ZD_PAIR_CONTRACT_PASS" \
  "contract=eisa_h.sedenion_zd_pair.v1" \
  "cases=$CASE_COUNT mutations=$MUTATION_COUNT/$MUTATION_COUNT determinism=VERIFIED" \
  "basis_table_sha256=$TABLE_SHA" \
  "receipt_sha256=$RECEIPT_SHA" \
  "execution_surface=software_oracle rtl=NOT_IMPLEMENTED"
