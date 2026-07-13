#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$TMP/receipt" <<'PY'
import pathlib
import sys

from tools.eisa_h.validate_postsynth_receipt import EXPECTED_SIMULATION_RECEIPT

pathlib.Path(sys.argv[1]).write_text(EXPECTED_SIMULATION_RECEIPT, encoding="utf-8")
PY
cp "$TMP/receipt" "$TMP/raw"
printf '%s\n' '/tmp/worker/tb.sv:301: $finish called at 2662846000 (1ps)' >> "$TMP/raw"
python3 "$ROOT/tools/eisa_h/normalize_iverilog_log.py" \
  "$TMP/raw" "$TMP/normalized" >/dev/null
cmp "$TMP/receipt" "$TMP/normalized"

if python3 "$ROOT/tools/eisa_h/normalize_iverilog_log.py" \
    "$TMP/receipt" "$TMP/missing-output" >/dev/null; then
  echo "missing Icarus finish-line mutation unexpectedly passed" >&2
  exit 1
fi
printf '%s\n' '/tmp/worker/tb.sv:301: $finish called at 2662846000 (1ps)' >> "$TMP/raw"
if python3 "$ROOT/tools/eisa_h/normalize_iverilog_log.py" \
    "$TMP/raw" "$TMP/duplicate-output" >/dev/null; then
  echo "duplicate Icarus finish-line mutation unexpectedly passed" >&2
  exit 1
fi

echo "POSTSYNTH_LOG_CONTRACT_PASS cases=3"
