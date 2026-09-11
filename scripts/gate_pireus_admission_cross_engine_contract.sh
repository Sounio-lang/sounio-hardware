#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="$ROOT/tools/eisa_h/pireus_admission_cross_engine_oracle.py"
SCHEMA="$ROOT/spec/eisa_h/pireus_admission_cross_engine_v1.schema.json"
CONTRACT="$ROOT/spec/eisa_h/pireus_admission_cross_engine_v1.json"
VECTORS="$ROOT/vectors/eisa_h/pireus_admission_cross_engine_v1.json"
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

# The phase code is recoverable from the sign table at the sixteen basis pairs,
# so a tensor digest identifies one construction. Checked over the whole code
# space rather than argued -- an injectivity claim that nobody ranges over is
# the kind of premise that stays true in the comment and false in the code.
INJECTIVITY="$(python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" --vectors "$VECTORS" --exhaustive)"
if [[ ! "$INJECTIVITY" =~ ^PHASE_CODE_INJECTIVITY_VERIFIED\ codes=65536$ ]]; then
  printf 'injectivity check did not range over the code space: %s\n' "$INJECTIVITY" >&2
  exit 1
fi

CASE_COUNT="$(wc -l < "$TMP/receipts-a.jsonl" | tr -d ' ')"
OPERATORS="$(grep -c '"kind":"operator"' "$TMP/receipts-a.jsonl" || true)"
MATCHES="$(grep -c '"agreement":"CROSS_ENGINE_MATCH"' "$TMP/receipts-a.jsonl" || true)"
if [[ "$MATCHES" != "$CASE_COUNT" ]]; then
  printf 'only %s of %s receipts reported cross-engine agreement\n' "$MATCHES" "$CASE_COUNT" >&2
  exit 1
fi
ENGINE_SHA="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["provenance"]["engine_source_sha256"])' "$CONTRACT")"
RECEIPT_SHA="$(sha256sum "$TMP/receipts-a.jsonl" | cut -d' ' -f1)"

printf '%s\n' \
  "EISA_H_PIREUS_ADMISSION_CROSS_ENGINE_CONTRACT_PASS" \
  "contract=eisa_h.pireus_admission_cross_engine.v1" \
  "engine=admission.sio sha256=$ENGINE_SHA executed=RECORDED compiled_by=souc" \
  "cases=$CASE_COUNT operators=$OPERATORS agreement=$MATCHES/$CASE_COUNT injectivity=65536/65536" \
  "mutations=$MUTATION_COUNT/$MUTATION_COUNT determinism=VERIFIED" \
  "receipt_sha256=$RECEIPT_SHA" \
  "execution_surface=software_oracle_over_recorded_engine_receipts establishes=cross_implementation_agreement_only" \
  "engine_correctness=NOT_ESTABLISHED novelty=NOT_ESTABLISHED fp_parity=NOT_ESTABLISHED"
