#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="$ROOT/tools/eisa_h/pireus_proposal_wire_oracle.py"
SCHEMA="$ROOT/spec/eisa_h/pireus_proposal_wire_v1.schema.json"
CONTRACT="$ROOT/spec/eisa_h/pireus_proposal_wire_v1.json"
VECTORS="$ROOT/vectors/eisa_h/pireus_proposal_wire_v1.json"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PYTHONPYCACHEPREFIX="$TMP/pycache" python3 -m py_compile "$ORACLE"

SELFTEST_LINE="$(python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" \
  --vectors "$VECTORS" --receipts "$TMP/receipts-a.jsonl" --selftest)"
if [[ ! "$SELFTEST_LINE" =~ ^MUTATION_SELFTEST_PASS\ caught=([0-9]+)$ ]]; then
  printf 'invalid mutation selftest receipt: %s\n' "$SELFTEST_LINE" >&2
  exit 1
fi
MUTATION_COUNT="${BASH_REMATCH[1]}"

python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" --vectors "$VECTORS" \
  --receipts "$TMP/receipts-b.jsonl"
cmp "$TMP/receipts-a.jsonl" "$TMP/receipts-b.jsonl"

CASE_COUNT="$(wc -l < "$TMP/receipts-a.jsonl" | tr -d ' ')"
ACCEPTED="$(grep -c '"accepted":true' "$TMP/receipts-a.jsonl" || true)"
REJECTED="$(grep -c '"accepted":false' "$TMP/receipts-a.jsonl" || true)"
RECEIPT_SHA="$(sha256sum "$TMP/receipts-a.jsonl" | cut -d' ' -f1)"

printf '%s\n' \
  "EISA_H_PIREUS_PROPOSAL_WIRE_CONTRACT_PASS" \
  "contract=eisa_h.pireus_proposal_wire.v1" \
  "v1_keys=16 v2_keys=17 v1_mask=65087 v2_mask=130623 max_bytes=4096" \
  "cases=$CASE_COUNT accepted=$ACCEPTED rejected=$REJECTED mutations=$MUTATION_COUNT/$MUTATION_COUNT determinism=VERIFIED" \
  "receipt_sha256=$RECEIPT_SHA" \
  "execution_surface=software_oracle derived_by=source_reading" \
  "correspondence_with_admission_sio=NOT_ESTABLISHED semantic_admission=NOT_DECIDED"
