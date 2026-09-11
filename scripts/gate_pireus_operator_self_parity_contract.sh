#!/usr/bin/env bash
set -euo pipefail

# Unlike the other three PIREUS contract gates in this repository, this one
# compiles and runs a probe. The receipts it judges are produced during the
# gate, not only read from fixtures: a contract that has only ever judged
# fixtures has never been executed.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="$ROOT/tools/eisa_h/pireus_operator_self_parity_oracle.py"
SCHEMA="$ROOT/spec/eisa_h/pireus_operator_self_parity_v1.schema.json"
CONTRACT="$ROOT/spec/eisa_h/pireus_operator_self_parity_v1.json"
VECTORS="$ROOT/vectors/eisa_h/pireus_operator_self_parity_v1.json"
PROBE_SRC="$ROOT/src/eisa_h/pireus_operator_self_parity.cpp"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PYTHONPYCACHEPREFIX="$TMP/pycache" python3 -m py_compile "$ORACLE"

# -ffp-contract=off is load-bearing, not hygiene: contraction would fuse a
# product and a sum into one rounding and the receipt asserts it did not.
g++ -O2 -std=c++20 -ffp-contract=off -frounding-math -o "$TMP/probe" "$PROBE_SRC"

# Measure across several lane maps, and across the base as well as the twisted
# operator, so the conditional twist control is exercised in both directions.
: > "$TMP/measured.jsonl"
for spec in "1128 1 0" "1128 3 5" "1128 7 11" "1128 15 9" "0 1 0" "2 5 3"; do
  # shellcheck disable=SC2086
  "$TMP/probe" $spec >> "$TMP/measured.jsonl"
done

MEASURED="$(wc -l < "$TMP/measured.jsonl" | tr -d ' ')"
PASSING="$(grep -c '"result":"PASS"' "$TMP/measured.jsonl" || true)"
if [[ "$MEASURED" -eq 0 || "$PASSING" != "$MEASURED" ]]; then
  printf 'probe did not pass on every configuration: %s/%s\n' "$PASSING" "$MEASURED" >&2
  cat "$TMP/measured.jsonl" >&2
  exit 1
fi

# The probe must be falsifiable by its own arithmetic, not only by the oracle.
# Rebuild it with the sign table poisoned and require the parity to break.
sed 's/if (m.corrupt_sign_table)/if (true)/' "$PROBE_SRC" > "$TMP/sabotaged.cpp"
g++ -O2 -std=c++20 -ffp-contract=off -frounding-math -o "$TMP/sabotaged" "$TMP/sabotaged.cpp"
if "$TMP/sabotaged" 1128 1 0 | grep -q '"mismatching_lanes":0'; then
  printf 'sabotaged probe still reported zero mismatching lanes\n' >&2
  exit 1
fi

SELFTEST_LINE="$(python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" \
  --vectors "$VECTORS" --measured "$TMP/measured.jsonl" \
  --receipts "$TMP/receipts-a.jsonl" --selftest)"
if [[ ! "$SELFTEST_LINE" =~ ^MUTATION_SELFTEST_PASS\ caught=([0-9]+)$ ]]; then
  printf 'invalid mutation selftest receipt: %s\n' "$SELFTEST_LINE" >&2
  exit 1
fi
MUTATION_COUNT="${BASH_REMATCH[1]}"

python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" --vectors "$VECTORS" \
  --measured "$TMP/measured.jsonl" --receipts "$TMP/receipts-b.jsonl"
cmp "$TMP/receipts-a.jsonl" "$TMP/receipts-b.jsonl"

CASE_COUNT="$(wc -l < "$TMP/receipts-a.jsonl" | tr -d ' ')"
ACCEPTED="$(grep -c '"accepted":true' "$TMP/receipts-a.jsonl" || true)"
REJECTED="$(grep -c '"accepted":false' "$TMP/receipts-a.jsonl" || true)"
RECEIPT_SHA="$(sha256sum "$TMP/receipts-a.jsonl" | cut -d' ' -f1)"
PROBE_SHA="$(sha256sum "$PROBE_SRC" | cut -d' ' -f1)"

printf '%s\n' \
  "EISA_H_PIREUS_OPERATOR_SELF_PARITY_CONTRACT_PASS" \
  "contract=eisa_h.pireus_operator_self_parity.v1" \
  "probe=EXECUTED configurations=$MEASURED passing=$PASSING sabotage=DETECTED" \
  "reference_operator=phase_code:1128 controls=sign,lane,twist_drop" \
  "cases=$CASE_COUNT accepted=$ACCEPTED rejected=$REJECTED mutations=$MUTATION_COUNT/$MUTATION_COUNT determinism=VERIFIED" \
  "probe_sha256=$PROBE_SHA" \
  "receipt_sha256=$RECEIPT_SHA" \
  "execution_surface=native_x86_64 establishes=two_materialisations_agree" \
  "utility=NOT_ESTABLISHED performance=NOT_MEASURED portability=NOT_ESTABLISHED"
