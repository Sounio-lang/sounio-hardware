#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! command -v yosys >/dev/null 2>&1; then
  echo "EISA_H_ZD_PAIR_FORMAL_SURFACE_BLOCKED reason=yosys_unavailable" >&2
  exit 42
fi
YOSYS_VERSION="$(yosys -V | awk '{print $2}')"
if [[ "$YOSYS_VERSION" != "0.33" ]]; then
  printf 'EISA_H_ZD_PAIR_FORMAL_SURFACE_BLOCKED reason=unsupported_yosys_version observed=%s expected=0.33\n' \
    "$YOSYS_VERSION" >&2
  exit 42
fi

persist_surface_logs() {
  local destination log
  [[ -n "${EISA_H_FORMAL_ARTIFACT_DIR:-}" ]] || return 0
  destination="$EISA_H_FORMAL_ARTIFACT_DIR/surface"
  mkdir -p "$destination"
  for log in "$TMP"/*.log; do
    [[ -f "$log" ]] && cp "$log" "$destination/$(basename "$log")"
  done
  (cd "$destination" && sha256sum * > SHA256SUMS)
}

for run in primary replay; do
  set +e
  (cd "$ROOT" && timeout 300s yosys -Q -T \
    -s scripts/yosys/formal_zd_pair_surface_v1.ys > "$TMP/$run.log" 2>&1)
  rc=$?
  set -e
  if [[ "$rc" == "124" || "$rc" == "137" ]]; then
    persist_surface_logs
    printf 'EISA_H_ZD_PAIR_FORMAL_SURFACE_BLOCKED reason=timeout run=%s rc=%s log_sha256=%s\n' \
      "$run" "$rc" "$(sha256sum "$TMP/$run.log" | cut -d' ' -f1)" >&2
    exit 42
  fi
  if [[ "$rc" != "0" ]]; then
    persist_surface_logs
    printf 'EISA_H_ZD_PAIR_FORMAL_SURFACE_FAIL reason=yosys_failed run=%s rc=%s log_sha256=%s\n' \
      "$run" "$rc" "$(sha256sum "$TMP/$run.log" | cut -d' ' -f1)" >&2
    exit 1
  fi
done
if ! cmp "$TMP/primary.log" "$TMP/replay.log"; then
  persist_surface_logs
  printf 'EISA_H_ZD_PAIR_FORMAL_SURFACE_FAIL reason=replay_mismatch primary_sha256=%s replay_sha256=%s\n' \
    "$(sha256sum "$TMP/primary.log" | cut -d' ' -f1)" \
    "$(sha256sum "$TMP/replay.log" | cut -d' ' -f1)" >&2
  exit 1
fi
persist_surface_logs

python3 - "$TMP/primary.log" <<'PY'
import hashlib
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
if "ERROR:" in text or "Warning: Selection" in text:
    raise SystemExit("formal surface log contains an error or selection warning")
counts = [int(value) for value in re.findall(r"^(\d+) objects\.$", text, re.MULTILINE)]
expected = [1042, 4122, 5147]
if counts[-3:] != expected:
    raise SystemExit(f"formal surface mismatch: observed={counts[-3:]} expected={expected}")

def mapping_hash(name: str) -> str:
    begin = f"EISA_H_{name}_EQUIV_MAP_BEGIN"
    end = f"EISA_H_{name}_EQUIV_MAP_END"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise SystemExit(f"missing or duplicate mapping markers for {name}")
    section = text.split(begin, 1)[1].split(end, 1)[0]
    pairs = re.findall(r"^  Unproven \$equiv .*?: (.+)$", section, re.MULTILINE)
    expected_count = {"PUBLIC": 1042, "STATE": 4122, "PROOF": 5147}[name]
    if len(pairs) != expected_count or len(set(pairs)) != expected_count:
        raise SystemExit(
            f"mapping cardinality mismatch for {name}: "
            f"observed={len(pairs)} unique={len(set(pairs))} expected={expected_count}"
        )
    payload = ("\n".join(sorted(pairs)) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()

public_hash = mapping_hash("PUBLIC")
state_hash = mapping_hash("STATE")
proof_hash = mapping_hash("PROOF")
observed_hashes = {
    "PUBLIC": public_hash,
    "STATE": state_hash,
    "PROOF": proof_hash,
}
expected_hashes = {
    "PUBLIC": "a01c87792b972a115ebd57836a4eb2f1d5d7c11014ae8d4adcef88870fba5123",
    "STATE": "36255aaf229111de447a2f6f4245c011a7847a599c7d9f98cc34ae479b11b2a7",
    "PROOF": "57f65e8af872f8dc4c45282f536041bd644e0dd8c5f1ed052cf533bd7cf3df79",
}
if observed_hashes != expected_hashes:
    raise SystemExit(
        f"formal mapping identity mismatch: observed={observed_hashes} "
        f"expected={expected_hashes}"
    )
print(
    "EISA_H_ZD_PAIR_FORMAL_SURFACE_VALIDATION_PASS "
    "public_equiv_bits=1042 state_relation_bits=4122 proof_relation_bits=5147 "
    f"public_map_sha256={public_hash} state_map_sha256={state_hash} "
    f"proof_map_sha256={proof_hash}"
)
PY

printf '%s\n' \
  "EISA_H_ZD_PAIR_FORMAL_SURFACE_GATE_PASS" \
  "deterministic_replay=VERIFIED tool=yosys version=$YOSYS_VERSION" \
  "surface_log_sha256=$(sha256sum "$TMP/primary.log" | cut -d' ' -f1)" \
  "equivalence_proof=NOT_CLAIMED reset_base=SEPARATE_OBLIGATION inductive_step=SEPARATE_OBLIGATION"
