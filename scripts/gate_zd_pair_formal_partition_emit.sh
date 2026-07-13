#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ARTIFACT_DIR="${EISA_H_FORMAL_PARTITION_ARTIFACT_DIR:-}"
partitions=(latches accumulator product_and_alias control)

if [[ -z "$ARTIFACT_DIR" ]]; then
  echo "EISA_H_STATE_PARTITION_EMIT_BLOCKED reason=artifact_dir_required" >&2
  exit 42
fi
if [[ -e "$ARTIFACT_DIR" ]]; then
  echo "EISA_H_STATE_PARTITION_EMIT_BLOCKED reason=artifact_dir_exists" >&2
  exit 42
fi
mkdir -p "$ARTIFACT_DIR"

EISA_H_PARTITION_RECIPE_DIR="$TMP/recipes" \
  bash "$ROOT/scripts/gate_zd_pair_formal_partition_surface.sh"
cp -a "$TMP/recipes" "$ARTIFACT_DIR/recipe_bundle"

pids=()
for partition in "${partitions[@]}"; do
  mkdir -p "$ARTIFACT_DIR/$partition"
  "$TMP/recipes/emit_state_step_$partition.sh" \
    "$TMP/$partition.cnf" "$ARTIFACT_DIR/$partition/yosys.log" &
  pids+=("$!")
done
emit_rc=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    emit_rc=1
  fi
done
if [[ "$emit_rc" != "0" ]]; then
  echo "EISA_H_STATE_PARTITION_EMIT_FAIL reason=temporal_driver_failed" >&2
  exit 1
fi

for partition in "${partitions[@]}"; do
  python3 - "$partition" "$TMP/$partition.cnf" "$ARTIFACT_DIR/$partition/yosys.log" <<'PY'
import pathlib
import sys

partition = sys.argv[1]
cnf = pathlib.Path(sys.argv[2])
text = pathlib.Path(sys.argv[3]).read_text(encoding="utf-8")
dump_marker = f"Dumping CNF to file `{cnf}'."
outcomes = (
    text.count("Interrupted SAT solver: TIMEOUT!")
    + text.count("SAT proof finished - no model found: SUCCESS!")
)
if text.count(dump_marker) != 1 or outcomes != 1:
    raise SystemExit(
        f"partition={partition} incomplete_driver_log "
        f"dump_markers={text.count(dump_marker)} outcomes={outcomes}"
    )
outcome_positions = [
    position
    for marker in (
        "Interrupted SAT solver: TIMEOUT!",
        "SAT proof finished - no model found: SUCCESS!",
    )
    if (position := text.find(marker)) >= 0
]
if text.find(dump_marker) >= min(outcome_positions):
    raise SystemExit(f"partition={partition} solver_outcome_preceded_cnf_dump")
print(f"partition={partition} driver_log=COMPLETE_CNF_BEFORE_SOLVER_OUTCOME")
PY
  python3 - "$partition" "$TMP/$partition.cnf" <<'PY'
import hashlib
import pathlib
import sys

partition = sys.argv[1]
path = pathlib.Path(sys.argv[2])
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
                raise SystemExit(f"partition={partition} invalid_header line={line_number}")
            variables, declared_clauses = map(int, fields[2:])
            if variables <= 0 or declared_clauses <= 0:
                raise SystemExit(f"partition={partition} nonpositive_header")
            continue
        if variables is None:
            raise SystemExit(f"partition={partition} clause_before_header")
        try:
            literals = [int(value) for value in line.split()]
        except ValueError as error:
            raise SystemExit(f"partition={partition} invalid_clause line={line_number}") from error
        if not literals or literals[-1] != 0 or any(value == 0 for value in literals[:-1]):
            raise SystemExit(f"partition={partition} invalid_clause line={line_number}")
        if any(abs(value) > variables for value in literals[:-1]):
            raise SystemExit(f"partition={partition} literal_out_of_range line={line_number}")
        observed_clauses += 1
if variables is None or observed_clauses != declared_clauses:
    raise SystemExit(
        f"partition={partition} clause_count_mismatch "
        f"declared={declared_clauses} observed={observed_clauses}"
    )
print(
    f"partition={partition} cnf_status=EMITTED vars={variables} "
    f"clauses={declared_clauses} bytes={path.stat().st_size} sha256={digest.hexdigest()}"
)
PY
  gzip -n -1 -c "$TMP/$partition.cnf" > "$ARTIFACT_DIR/$partition/obligation.cnf.gz"
  cp "$TMP/recipes/state_step_$partition.ys" "$ARTIFACT_DIR/$partition/recipe.ys"
  cp "$TMP/recipes/emit_state_step_$partition.sh" "$ARTIFACT_DIR/$partition/temporal_driver.sh"
  (cd "$ARTIFACT_DIR/$partition" && sha256sum obligation.cnf.gz recipe.ys temporal_driver.sh yosys.log > SHA256SUMS)
done

(cd "$ARTIFACT_DIR" && \
  find . -type f ! -name BUNDLE_SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > BUNDLE_SHA256SUMS)
echo "EISA_H_STATE_PARTITION_EMIT_PASS"
echo "partitions=4 antecedent_bits=5147 consequent_union_bits=5147"
