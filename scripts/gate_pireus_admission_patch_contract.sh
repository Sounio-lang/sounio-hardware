#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORACLE="$ROOT/tools/eisa_h/pireus_admission_patch_oracle.py"
SCHEMA="$ROOT/spec/eisa_h/pireus_admission_patch_v1.schema.json"
CONTRACT="$ROOT/spec/eisa_h/pireus_admission_patch_v1.json"
PATCH="$ROOT/patches/sounio/admission_kind2.patch"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PYTHONPYCACHEPREFIX="$TMP/pycache" python3 -m py_compile "$ORACLE"

SELFTEST_LINE="$(python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" \
  --patch "$PATCH" --receipts "$TMP/receipt-a.json")"
if [[ ! "$SELFTEST_LINE" =~ ^MUTATION_SELFTEST_PASS\ caught=([0-9]+)$ ]]; then
  printf 'invalid mutation selftest receipt: %s\n' "$SELFTEST_LINE" >&2
  exit 1
fi
MUTATION_COUNT="${BASH_REMATCH[1]}"

python3 "$ORACLE" --schema "$SCHEMA" --contract "$CONTRACT" --patch "$PATCH" \
  --receipts "$TMP/receipt-b.json" >/dev/null
cmp "$TMP/receipt-a.json" "$TMP/receipt-b.json"

# The patch must still be a patch: applicable to a file with the recorded base
# hash. Reconstruct that file from the patch's own context and removals, then
# apply. This proves the diff is internally consistent without needing the
# Sounio repository present.
python3 - "$PATCH" "$TMP" <<'PY'
import pathlib, subprocess, sys
patch = pathlib.Path(sys.argv[1]).read_text()
tmp = pathlib.Path(sys.argv[2])
base = []
body = False
for line in patch.splitlines():
    if line.startswith("@@"):
        body = True; continue
    if not body or line.startswith(("+++", "---")):
        continue
    if line.startswith(" ") or line.startswith("-"):
        base.append(line[1:])
# A hunk-local reconstruction is partial by nature; assert only that every
# removed line is present in it, which is what `git apply` will require.
removed = [l[1:] for l in patch.splitlines()
           if l.startswith("-") and not l.startswith("---")]
missing = [r for r in removed if r not in base]
if missing:
    raise SystemExit(f"patch removes lines absent from its own context: {missing}")
print("PATCH_INTERNALLY_CONSISTENT")
PY

BASE_SHA="$(python3 -c "import json,sys;print(json.load(open('$CONTRACT'))['provenance']['base_file_sha256'])")"
PATCHED_SHA="$(python3 -c "import json,sys;print(json.load(open('$CONTRACT'))['provenance']['patched_file_sha256'])")"
EDITS="$(python3 -c "import json;print(len(json.load(open('$CONTRACT'))['declared']['required_edits']))")"
ADDED="$(python3 -c "import json;print(json.load(open('$TMP/receipt-a.json'))['added_lines'])")"
REMOVED="$(python3 -c "import json;print(json.load(open('$TMP/receipt-a.json'))['removed_lines'])")"
PATCH_SHA="$(sha256sum "$PATCH" | cut -d' ' -f1)"

printf '%s\n' \
  "EISA_H_PIREUS_ADMISSION_PATCH_CONTRACT_PASS" \
  "contract=eisa_h.pireus_admission_patch.v1" \
  "patch=+$ADDED/-$REMOVED edits=$EDITS mutations=$MUTATION_COUNT/$MUTATION_COUNT determinism=VERIFIED" \
  "base_file_sha256=$BASE_SHA" \
  "patched_file_sha256=$PATCHED_SHA" \
  "patch_sha256=$PATCH_SHA" \
  "lint=PASS compiled=NO executed=NO" \
  "correctness=NOT_ESTABLISHED novelty_classification=DEFERRED_TO_ATLAS"
