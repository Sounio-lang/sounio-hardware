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
RESET_WALL_SECONDS="${EISA_H_RESET_WALL_SECONDS:-600}"
RESET_SOLVER_SECONDS="${EISA_H_RESET_SOLVER_SECONDS:-540}"
STEP_WALL_SECONDS="${EISA_H_STEP_WALL_SECONDS:-1800}"
STEP_SOLVER_SECONDS="${EISA_H_STEP_SOLVER_SECONDS:-1740}"

cnf_receipt() {
  local obligation="$1" cnf="$2"
  python3 - "$obligation" "$cnf" <<'PY'
import hashlib
import pathlib
import sys

obligation = sys.argv[1]
path = pathlib.Path(sys.argv[2])
if not path.is_file() or path.stat().st_size == 0:
    raise SystemExit(f"obligation={obligation} cnf_status=MISSING")

digest = hashlib.sha256()
variables = None
declared_clauses = None
observed_clauses = 0
with path.open("rb") as stream:
    for line_number, raw in enumerate(stream, 1):
        digest.update(raw)
        line = raw.strip()
        if not line or line.startswith(b"c"):
            continue
        if line.startswith(b"p"):
            fields = line.split()
            if variables is not None or len(fields) != 4 or fields[:2] != [b"p", b"cnf"]:
                raise SystemExit(
                    f"obligation={obligation} cnf_status=INVALID line={line_number}"
                )
            variables, declared_clauses = map(int, fields[2:])
            if variables <= 0 or declared_clauses <= 0:
                raise SystemExit(f"obligation={obligation} cnf_status=INVALID header=nonpositive")
            continue
        if variables is None:
            raise SystemExit(f"obligation={obligation} cnf_status=INVALID reason=clause_before_header")
        try:
            literals = [int(value) for value in line.split()]
        except ValueError as error:
            raise SystemExit(
                f"obligation={obligation} cnf_status=INVALID line={line_number}"
            ) from error
        if not literals or literals[-1] != 0 or any(value == 0 for value in literals[:-1]):
            raise SystemExit(f"obligation={obligation} cnf_status=INVALID line={line_number}")
        if any(abs(value) > variables for value in literals[:-1]):
            raise SystemExit(f"obligation={obligation} cnf_status=INVALID line={line_number}")
        observed_clauses += 1

if variables is None or observed_clauses != declared_clauses:
    raise SystemExit(
        f"obligation={obligation} cnf_status=INVALID "
        f"declared_clauses={declared_clauses} observed_clauses={observed_clauses}"
    )
print(
    f"obligation={obligation} cnf_status=EMITTED vars={variables} "
    f"clauses={declared_clauses} bytes={path.stat().st_size} sha256={digest.hexdigest()}"
)
PY
}

step_geometry_receipt() {
  local log="$1"
  python3 - "$log" <<'PY'
import hashlib
import pathlib
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
begin = "EISA_H_STEP_CMP_MAP_BEGIN"
end = "EISA_H_STEP_CMP_MAP_END"
if text.count(begin) != 1 or text.count(end) != 1:
    raise SystemExit("state-step cmp map markers are missing or duplicated")
section = text.split(begin, 1)[1].split(end, 1)[0]
names = [
    line.strip()
    for line in section.splitlines()
    if line.startswith("state_step_miter/cmp")
]
if len(names) != 5147 or len(set(names)) != 5147:
    raise SystemExit(
        f"state-step cmp map mismatch: observed={len(names)} "
        f"unique={len(set(names))} expected=5147"
    )
digest = hashlib.sha256(("\n".join(sorted(names)) + "\n").encode()).hexdigest()
expected = "855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35"
if digest != expected:
    raise SystemExit(
        f"state-step cmp map identity mismatch: observed={digest} expected={expected}"
    )
if text.count("EISA_H_CLOSURE_EXTRAS_PROVED count=32") != 1:
    raise SystemExit("state-step closure extras were not discharged exactly once")
print(
    "obligation=state_step geometry=EXACT_PROOF_RELATION "
    f"cmp_bits=5147 cmp_map_sha256={digest} closure_extras_proved=32"
)
PY
}

miter_geometry_receipt() {
  local obligation="$1" log="$2"
  python3 - "$obligation" "$log" <<'PY'
import pathlib
import re
import sys

obligation = sys.argv[1]
text = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
prefix = "RESET" if obligation == "reset_base" else "STEP"
module = "relation_reset_miter" if obligation == "reset_base" else "state_step_miter"
begin = f"EISA_H_{prefix}_MITER_EQUIV_STATUS_BEGIN"
end = f"EISA_H_{prefix}_MITER_EQUIV_STATUS_END"
if text.count(begin) != 1 or text.count(end) != 1:
    raise SystemExit(f"{obligation} miter status markers are missing or duplicated")
section = text.split(begin, 1)[1].split(end, 1)[0]
match = re.search(
    rf"Found (\d+) \$equiv cells in {module}:\n"
    rf"  Of those cells (\d+) are proven and (\d+) are unproven\.",
    section,
)
if match is None or tuple(map(int, match.groups())) != (5179, 32, 5147):
    raise SystemExit(
        f"{obligation} miter geometry mismatch: "
        f"observed={match.groups() if match else None} expected=(5179, 32, 5147)"
    )
print(
    f"obligation={obligation} miter_equiv_cells=5179 "
    "proven_support_cells=32 unproven_relation_cells=5147"
)
PY
}

persist_obligation() {
  local obligation="$1" cnf="$2" log="$3" destination
  [[ -n "${EISA_H_FORMAL_ARTIFACT_DIR:-}" ]] || return 0
  destination="$EISA_H_FORMAL_ARTIFACT_DIR/$obligation"
  mkdir -p "$destination"
  cp "$log" "$destination/yosys.log"
  if [[ -s "$cnf" ]]; then
    gzip -n -1 -c "$cnf" > "$destination/obligation.cnf.gz"
  fi
  (cd "$destination" && sha256sum * > SHA256SUMS)
  printf 'obligation=%s persisted_artifact_dir=%s\n' "$obligation" "$destination"
}

run_obligation() {
  local obligation="$1" timeout_seconds="$2" recipe="$3" sat_command="$4"
  local log="$TMP/$obligation.log" cnf="$TMP/$obligation.cnf" rc
  sat_command="${sat_command//__CNF__/$cnf}"
  set +e
  (cd "$ROOT" && timeout "${timeout_seconds}s" yosys -Q -T \
    -s "$recipe" -p "$sat_command" > "$log" 2>&1)
  rc=$?
  set -e
  if ! cnf_receipt "$obligation" "$cnf"; then
    persist_obligation "$obligation" "$cnf" "$log"
    if [[ "$rc" == "124" || "$rc" == "137" ]]; then
      printf 'EISA_H_ZD_PAIR_FORMAL_BLOCKED reason=timeout_without_valid_cnf obligation=%s rc=%s log_sha256=%s\n' \
        "$obligation" "$rc" "$(sha256sum "$log" | cut -d' ' -f1)" >&2
      exit 42
    fi
    printf 'EISA_H_ZD_PAIR_FORMAL_FAIL reason=invalid_or_missing_cnf obligation=%s rc=%s\n' \
      "$obligation" "$rc" >&2
    exit 1
  fi
  if [[ "$obligation" == "state_step" ]]; then
    if ! step_geometry_receipt "$log"; then
      persist_obligation "$obligation" "$cnf" "$log"
      echo "EISA_H_ZD_PAIR_FORMAL_FAIL reason=invalid_state_step_geometry" >&2
      exit 1
    fi
  fi
  if ! miter_geometry_receipt "$obligation" "$log"; then
    persist_obligation "$obligation" "$cnf" "$log"
    printf 'EISA_H_ZD_PAIR_FORMAL_FAIL reason=invalid_miter_geometry obligation=%s\n' \
      "$obligation" >&2
    exit 1
  fi
  persist_obligation "$obligation" "$cnf" "$log"
  if grep -q 'proof did time out' "$log"; then
    printf 'EISA_H_ZD_PAIR_FORMAL_BLOCKED reason=obligation_solver_timeout obligation=%s rc=%s log_sha256=%s\n' \
      "$obligation" "$rc" "$(sha256sum "$log" | cut -d' ' -f1)" >&2
    exit 42
  fi
  if [[ "$rc" == "124" || "$rc" == "137" ]]; then
    printf 'EISA_H_ZD_PAIR_FORMAL_BLOCKED reason=obligation_timeout obligation=%s rc=%s log_sha256=%s\n' \
      "$obligation" "$rc" "$(sha256sum "$log" | cut -d' ' -f1)" >&2
    exit 42
  fi
  if [[ "$rc" != "0" ]]; then
    printf 'EISA_H_ZD_PAIR_FORMAL_FAIL reason=obligation_failed obligation=%s rc=%s log_sha256=%s\n' \
      "$obligation" "$rc" "$(sha256sum "$log" | cut -d' ' -f1)" >&2
    tail -60 "$log" >&2
    exit 1
  fi
  if [[ "$(grep -c 'SAT proof finished - no model found: SUCCESS!' "$log" || true)" != "1" ]]; then
    printf 'EISA_H_ZD_PAIR_FORMAL_FAIL reason=missing_success_marker obligation=%s\n' \
      "$obligation" >&2
    exit 1
  fi
  printf 'obligation=%s proof=UNSAT log_sha256=%s\n' \
    "$obligation" "$(sha256sum "$log" | cut -d' ' -f1)"
}

python3 "$ROOT/tools/eisa_h/validate_formal_receipt.py" "$ROOT" --contract-only
bash "$ROOT/scripts/gate_zd_pair_formal_surface.sh"

run_obligation reset_base "$RESET_WALL_SECONDS" scripts/yosys/formal_zd_pair_reset_base_v1.ys \
  "sat -seq 2 -set-at 1 rst_n 0 -set-at 2 rst_n 1 -set-def-inputs -prove-skip 1 -prove-asserts -verify -timeout $RESET_SOLVER_SECONDS -dump_cnf __CNF__"

run_obligation state_step "$STEP_WALL_SECONDS" scripts/yosys/formal_zd_pair_step_v1.ys \
  "sat -seq 2 -set-at 1 trigger 0 -set-def-inputs -set-init-def -prove-skip 1 -prove trigger 0 -verify -timeout $STEP_SOLVER_SECONDS -dump_cnf __CNF__"

printf '%s\n' \
  "EISA_H_ZD_PAIR_FORMAL_CANDIDATE" \
  "formal=eisa_h.sedenion_zd_pair.formal.v1" \
  "tool=yosys version=$YOSYS_VERSION" \
  "proof=RESET_BASE_PLUS_ONE_STEP_RELATION_CLOSURE" \
  "public_equiv_bits=1042 state_relation_bits=4122 proof_relation_bits=5147" \
  "arbitrary_initial_state_equivalence=NOT_CLAIMED timing=NOT_CLAIMED silicon=NOT_CLAIMED"
echo "EISA_H_ZD_PAIR_FORMAL_BLOCKED reason=state_step_reference_evidence_not_pinned required=independent_cnf_unsat_certificate_replay" >&2
exit 42
