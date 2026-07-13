#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ORIGINAL_HEAD="$(git -C "$ROOT" rev-parse HEAD)"
COMMIT="0123456789abcdef0123456789abcdef01234567"
REPO_SHA="$(printf 'a%.0s' {1..64})"
TOOLCHAIN_SHA="$(printf 'b%.0s' {1..64})"

make_partition_artifacts() {
  local dir="$1" map_log="$dir/partition-map.log" raw_cnf partition count bytes digest
  mkdir -p "$dir/formal_artifacts/recipe_bundle"
  python3 - "$map_log" <<'PY'
import pathlib
import sys

prefix = "state_step_miter/"
names = []
names += [
    f"{prefix}cmp_{side}_latched[{index}][{bit}]"
    for side in ("lhs", "rhs")
    for index in range(16)
    for bit in range(64)
]
names += [
    f"{prefix}cmp_accumulator[{index}][{bit}]"
    for index in range(16)
    for bit in range(64)
]
names += [
    f"{prefix}cmp_product[{index}][{bit}]"
    for index in range(16)
    for bit in range(64)
]
names += [f"{prefix}cmp_product_flat[{bit}]" for bit in range(1024)]
names += [
    f"{prefix}cmp_busy",
    f"{prefix}cmp_done",
    f"{prefix}cmp_finalize",
    f"{prefix}cmp_product_is_zero",
    f"{prefix}cmp_ready",
]
names += [f"{prefix}cmp_classification[{bit}]" for bit in range(2)]
names += [f"{prefix}cmp_error_code[{bit}]" for bit in range(3)]
names += [f"{prefix}cmp_i_index[{bit}]" for bit in range(4)]
names += [f"{prefix}cmp_j_index[{bit}]" for bit in range(4)]
names += [f"{prefix}cmp_mac_cycles[{bit}]" for bit in range(9)]
pathlib.Path(sys.argv[1]).write_text(
    "EISA_H_STEP_CMP_MAP_BEGIN\n" + "\n".join(names) + "\nEISA_H_STEP_CMP_MAP_END\n",
    encoding="utf-8",
)
PY
  python3 "$ROOT/tools/eisa_h/generate_state_partition_recipes.py" \
    --map-log "$map_log" \
    --base-recipe "$ROOT/scripts/yosys/formal_zd_pair_step_v1.ys" \
    --output-dir "$dir/formal_artifacts/recipe_bundle" >/dev/null
  (cd "$dir/formal_artifacts/recipe_bundle" && \
    sha256sum partition_manifest.json state_step_*.ys emit_state_step_*.sh > SHA256SUMS)
  rm "$map_log"
  for partition in latches accumulator product_and_alias control; do
    case "$partition" in
      latches|product_and_alias) count=2048 ;;
      accumulator) count=1024 ;;
      control) count=27 ;;
    esac
    mkdir -p "$dir/formal_artifacts/$partition"
    raw_cnf="$dir/$partition.cnf"
    printf 'p cnf 1 1\n1 0\n' > "$raw_cnf"
    bytes="$(stat -c %s "$raw_cnf")"
    digest="$(sha256sum "$raw_cnf" | cut -d' ' -f1)"
    gzip -n -1 -c "$raw_cnf" > "$dir/formal_artifacts/$partition/obligation.cnf.gz"
    rm "$raw_cnf"
    cp "$dir/formal_artifacts/recipe_bundle/state_step_$partition.ys" \
      "$dir/formal_artifacts/$partition/recipe.ys"
    cp "$dir/formal_artifacts/recipe_bundle/emit_state_step_$partition.sh" \
      "$dir/formal_artifacts/$partition/temporal_driver.sh"
    printf '%s\n' \
      "EISA_H_STEP_PARTITION name=$partition assert_bits=$count" \
      "Dumping CNF to file \`/tmp/$partition.cnf'." \
      "Interrupted SAT solver: TIMEOUT!" \
      > "$dir/formal_artifacts/$partition/yosys.log"
    printf 'partition=%s cnf_status=EMITTED vars=1 clauses=1 bytes=%s sha256=%s\n' \
      "$partition" "$bytes" "$digest" >> "$dir/gate.log"
    (cd "$dir/formal_artifacts/$partition" && \
      sha256sum obligation.cnf.gz recipe.ys temporal_driver.sh yosys.log > SHA256SUMS)
  done
  (cd "$dir/formal_artifacts" && \
    find . -type f ! -name BUNDLE_SHA256SUMS -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum | sed 's#  \./#  #' > BUNDLE_SHA256SUMS)
}

rehash_partition_fixture() {
  local dir="$1" partition
  for partition in latches accumulator product_and_alias control; do
    (cd "$dir/formal_artifacts/$partition" && \
      sha256sum obligation.cnf.gz recipe.ys temporal_driver.sh yosys.log > SHA256SUMS)
  done
  (cd "$dir/formal_artifacts/recipe_bundle" && \
    sha256sum partition_manifest.json state_step_*.ys emit_state_step_*.sh > SHA256SUMS)
  (cd "$dir/formal_artifacts" && \
    find . -type f ! -name BUNDLE_SHA256SUMS -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum | sed 's#  \./#  #' > BUNDLE_SHA256SUMS)
  (cd "$dir" && \
    find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
}

make_fixture() {
  local dir="$1" gate_rc="$2" source="${3:-$COMMIT}" gate_id="${4:-synthesis}"
  mkdir -p "$dir"
  printf '%s\n' "source_commit=$source" "gate_id=$gate_id" "repo_manifest_sha256=$REPO_SHA" \
    "toolchain_manifest_sha256=$TOOLCHAIN_SHA" > "$dir/request.txt"
  printf '%s\n' "slurm_job_id=12345" "slurm_node=compute-1" "source_commit=$source" "gate_id=$gate_id" \
    "repo_manifest_sha256=$REPO_SHA" "toolchain_manifest_sha256=$TOOLCHAIN_SHA" \
    > "$dir/worker_meta.txt"
  if [[ "$gate_rc" == "0" && "$gate_id" == "synthesis" ]]; then
    printf '%s\n' \
      "EISA_H_ZD_PAIR_SYNTH_GATE_PASS" \
      "EISA_H_ZD_PAIR_POSTSYNTH_GATE_PASS" \
      > "$dir/gate.log"
  elif [[ "$gate_rc" == "0" && "$gate_id" == "formal" ]]; then
    printf '%s\n' "EISA_H_ZD_PAIR_FORMAL_GATE_PASS" > "$dir/gate.log"
  elif [[ "$gate_rc" == "0" && "$gate_id" == "formal-partition-emit" ]]; then
    printf '%s\n' \
      "EISA_H_STATE_PARTITION_EMIT_PASS" \
      "partitions=4 antecedent_bits=5147 consequent_union_bits=5147" \
      > "$dir/gate.log"
  else
    printf 'gate failed rc=%s\n' "$gate_rc" > "$dir/gate.log"
  fi
  printf '%s\n' "$gate_rc" > "$dir/gate.rc"
  if [[ "$gate_rc" == "0" && "$gate_id" == "formal-partition-emit" ]]; then
    make_partition_artifacts "$dir"
  fi
  (cd "$dir" && \
    find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
}

expect_rc() {
  local expected="$1"
  shift
  set +e
  "$@" >/dev/null 2>&1
  local observed=$?
  set -e
  if [[ "$observed" != "$expected" ]]; then
    printf 'expected rc=%s observed=%s command=%q\n' "$expected" "$observed" "$*" >&2
    exit 1
  fi
}

make_fixture "$TMP/pass" 0
python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/pass" \
  --expected-commit "$COMMIT" --srun-rc 0 --gate-id synthesis >/dev/null

make_fixture "$TMP/formal-pass" 0 "$COMMIT" formal
python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/formal-pass" \
  --expected-commit "$COMMIT" --srun-rc 0 --gate-id formal >/dev/null

make_fixture "$TMP/formal-partition-emit-pass" 0 "$COMMIT" formal-partition-emit
python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/formal-partition-emit-pass" \
  --expected-commit "$COMMIT" --srun-rc 0 --gate-id formal-partition-emit

make_fixture "$TMP/formal-partition-emit-fail" 1 "$COMMIT" formal-partition-emit
expect_rc 1 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-emit-fail" --expected-commit "$COMMIT" \
  --srun-rc 1 --gate-id formal-partition-emit

make_fixture "$TMP/formal-partition-emit-blocked" 42 "$COMMIT" formal-partition-emit
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-emit-blocked" --expected-commit "$COMMIT" \
  --srun-rc 42 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-unexpected-artifact"
printf 'unexpected\n' > \
  "$TMP/formal-partition-unexpected-artifact/formal_artifacts/unexpected.txt"
rehash_partition_fixture "$TMP/formal-partition-unexpected-artifact"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-unexpected-artifact" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-bad-semantics"
sed -i 's/"full_cmp_bits": 5147/"full_cmp_bits": 5146/' \
  "$TMP/formal-partition-bad-semantics/formal_artifacts/recipe_bundle/partition_manifest.json"
rehash_partition_fixture "$TMP/formal-partition-bad-semantics"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-bad-semantics" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-bad-json-type"
python3 - "$TMP/formal-partition-bad-json-type/formal_artifacts/recipe_bundle/partition_manifest.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
manifest["partitions"] = []
path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
rehash_partition_fixture "$TMP/formal-partition-bad-json-type"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-bad-json-type" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit
set +e
python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-bad-json-type" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit \
  > "$TMP/formal-partition-bad-json-type.out"
observed=$?
set -e
[[ "$observed" == "42" ]]
grep -F "SLURM_FORMAL_BLOCKED reason=invalid_return_receipt" \
  "$TMP/formal-partition-bad-json-type.out" >/dev/null

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-self-signed-driver"
printf '\nprintf "adversarial" > "$CNF"\n' >> \
  "$TMP/formal-partition-self-signed-driver/formal_artifacts/recipe_bundle/emit_state_step_control.sh"
cp "$TMP/formal-partition-self-signed-driver/formal_artifacts/recipe_bundle/emit_state_step_control.sh" \
  "$TMP/formal-partition-self-signed-driver/formal_artifacts/control/temporal_driver.sh"
python3 - "$TMP/formal-partition-self-signed-driver/formal_artifacts/recipe_bundle/partition_manifest.json" \
  "$TMP/formal-partition-self-signed-driver/formal_artifacts/recipe_bundle/emit_state_step_control.sh" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
driver_path = pathlib.Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["partitions"]["control"]["temporal_driver_sha256"] = hashlib.sha256(
    driver_path.read_bytes()
).hexdigest()
manifest_path.write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
rehash_partition_fixture "$TMP/formal-partition-self-signed-driver"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-self-signed-driver" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-duplicate-outcome"
printf '%s\n' "Interrupted SAT solver: TIMEOUT!" >> \
  "$TMP/formal-partition-duplicate-outcome/formal_artifacts/control/yosys.log"
rehash_partition_fixture "$TMP/formal-partition-duplicate-outcome"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-duplicate-outcome" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-invalid-gzip"
printf 'not gzip or DIMACS\n' > \
  "$TMP/formal-partition-invalid-gzip/formal_artifacts/control/obligation.cnf.gz"
rehash_partition_fixture "$TMP/formal-partition-invalid-gzip"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-invalid-gzip" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-truncated-gzip"
truncate -s -4 \
  "$TMP/formal-partition-truncated-gzip/formal_artifacts/control/obligation.cnf.gz"
rehash_partition_fixture "$TMP/formal-partition-truncated-gzip"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-truncated-gzip" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-missing-artifact"
rm "$TMP/formal-partition-missing-artifact/formal_artifacts/control/obligation.cnf.gz"
(cd "$TMP/formal-partition-missing-artifact/formal_artifacts" && \
  find . -type f ! -name BUNDLE_SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > BUNDLE_SHA256SUMS)
(cd "$TMP/formal-partition-missing-artifact" && \
  find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-missing-artifact" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-missing-bundle-line"
sed -i '1d' "$TMP/formal-partition-missing-bundle-line/formal_artifacts/BUNDLE_SHA256SUMS"
(cd "$TMP/formal-partition-missing-bundle-line" && \
  find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-missing-bundle-line" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-bundle-mismatch"
printf 'corruption\n' >> \
  "$TMP/formal-partition-bundle-mismatch/formal_artifacts/control/yosys.log"
(cd "$TMP/formal-partition-bundle-mismatch" && \
  find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-bundle-mismatch" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-partition-emit-pass" "$TMP/formal-partition-nested-mismatch"
printf 'corruption\n' >> \
  "$TMP/formal-partition-nested-mismatch/formal_artifacts/control/SHA256SUMS"
(cd "$TMP/formal-partition-nested-mismatch/formal_artifacts" && \
  find . -type f ! -name BUNDLE_SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > BUNDLE_SHA256SUMS)
(cd "$TMP/formal-partition-nested-mismatch" && \
  find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-partition-nested-mismatch" --expected-commit "$COMMIT" \
  --srun-rc 0 --gate-id formal-partition-emit

cp -a "$TMP/formal-pass" "$TMP/formal-artifacts-pass"
mkdir -p "$TMP/formal-artifacts-pass/formal_artifacts/reset_base"
printf 'bounded proof artifact\n' > \
  "$TMP/formal-artifacts-pass/formal_artifacts/reset_base/yosys.log"
(cd "$TMP/formal-artifacts-pass" && \
  find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/formal-artifacts-pass" \
  --expected-commit "$COMMIT" --srun-rc 0 --gate-id formal >/dev/null

cp -a "$TMP/formal-pass" "$TMP/formal-artifact-unlisted"
mkdir -p "$TMP/formal-artifact-unlisted/formal_artifacts/reset_base"
printf 'unlisted\n' > "$TMP/formal-artifact-unlisted/formal_artifacts/reset_base/yosys.log"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-artifact-unlisted" --expected-commit "$COMMIT" --srun-rc 0 --gate-id formal

cp -a "$TMP/formal-pass" "$TMP/formal-artifact-symlink"
mkdir -p "$TMP/formal-artifact-symlink/formal_artifacts/reset_base"
ln -s /etc/hosts "$TMP/formal-artifact-symlink/formal_artifacts/reset_base/yosys.log"
(cd "$TMP/formal-artifact-symlink" && \
  find . -type f -o -type l | LC_ALL=C sort | xargs sha256sum | \
  sed 's#  \./#  #' > SHA256SUMS)
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-artifact-symlink" --expected-commit "$COMMIT" --srun-rc 0 --gate-id formal

printf 'tampered\n' >> "$TMP/formal-artifacts-pass/formal_artifacts/reset_base/yosys.log"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/formal-artifacts-pass" --expected-commit "$COMMIT" --srun-rc 0 --gate-id formal

make_fixture "$TMP/blocked" 42
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/blocked" \
  --expected-commit "$COMMIT" --srun-rc 42 --gate-id synthesis

make_fixture "$TMP/fail" 1
expect_rc 1 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/fail" \
  --expected-commit "$COMMIT" --srun-rc 1 --gate-id synthesis

expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/pass" \
  --expected-commit "$COMMIT" --srun-rc 1 --gate-id synthesis

cp -a "$TMP/pass" "$TMP/corrupt"
printf 'corruption\n' >> "$TMP/corrupt/gate.log"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/corrupt" \
  --expected-commit "$COMMIT" --srun-rc 0 --gate-id synthesis

make_fixture "$TMP/wrong-source" 0 "1123456789abcdef0123456789abcdef01234567"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/wrong-source" \
  --expected-commit "$COMMIT" --srun-rc 0 --gate-id synthesis

cp -a "$TMP/pass" "$TMP/missing"
rm "$TMP/missing/worker_meta.txt"
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$TMP/missing" \
  --expected-commit "$COMMIT" --srun-rc 0 --gate-id synthesis

cp -a "$TMP/pass" "$TMP/missing-postsynth-marker"
printf '%s\n' "EISA_H_ZD_PAIR_SYNTH_GATE_PASS" \
  > "$TMP/missing-postsynth-marker/gate.log"
(cd "$TMP/missing-postsynth-marker" && \
  sha256sum request.txt worker_meta.txt gate.log gate.rc > SHA256SUMS)
expect_rc 42 python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" \
  "$TMP/missing-postsynth-marker" --expected-commit "$COMMIT" --srun-rc 0 --gate-id synthesis

duplicate="$TMP/duplicate-output"
mkdir "$duplicate"
expect_rc 42 env OUT_DIR="$duplicate" "$ROOT/scripts/slurm/run_zd_pair_synth.sh"

cat > "$TMP/mock-srun" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
if [[ "${MOCK_SRUN_MODE:-pass}" == "missing" ]]; then
  cat >/dev/null
  echo "mock scheduler rejected payload" >&2
  exit 1
fi
base64 -d > "$tmp/payload.tgz"
tar -xzf "$tmp/payload.tgz" -C "$tmp"
source_commit="$(sed -n 's/^source_commit=//p' "$tmp/request.txt")"
repo_sha="$(sed -n 's/^repo_manifest_sha256=//p' "$tmp/request.txt")"
toolchain_sha="$(sed -n 's/^toolchain_manifest_sha256=//p' "$tmp/request.txt")"
gate_id="$(sed -n 's/^gate_id=//p' "$tmp/request.txt")"
mkdir "$tmp/result"
cp "$tmp/request.txt" "$tmp/result/request.txt"
printf '%s\n' \
  "slurm_job_id=12345" \
  "slurm_node=mock-node" \
  "source_commit=$source_commit" \
  "gate_id=$gate_id" \
  "repo_manifest_sha256=$repo_sha" \
  "toolchain_manifest_sha256=$toolchain_sha" \
  > "$tmp/result/worker_meta.txt"
case "$gate_id" in
  formal)
    printf '%s\n' EISA_H_ZD_PAIR_FORMAL_GATE_PASS > "$tmp/result/gate.log"
    ;;
  formal-partition-emit)
    printf '%s\n' EISA_H_STATE_PARTITION_EMIT_PASS > "$tmp/result/gate.log"
    ;;
  *)
    printf '%s\n' \
      EISA_H_ZD_PAIR_SYNTH_GATE_PASS \
      EISA_H_ZD_PAIR_POSTSYNTH_GATE_PASS \
      > "$tmp/result/gate.log"
    ;;
esac
printf '%s\n' 0 > "$tmp/result/gate.rc"
if [[ "$gate_id" == "formal-partition-emit" ]]; then
  fixture="${MOCK_PARTITION_FIXTURE_DIR:?missing MOCK_PARTITION_FIXTURE_DIR}"
  cp "$fixture/gate.log" "$tmp/result/gate.log"
  cp -a "$fixture/formal_artifacts" "$tmp/result/formal_artifacts"
fi
(cd "$tmp/result" && \
  find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed 's#  \./#  #' > SHA256SUMS)
tar -C "$tmp/result" -czf "$tmp/result.tgz" .
printf '__SOUNIO_SLURM_RESULT__'
base64 -w0 "$tmp/result.tgz"
printf '\n'
MOCK
chmod +x "$TMP/mock-srun"

mkdir "$TMP/repo"
tar -C "$ROOT" --exclude=.git -cf - . | tar -C "$TMP/repo" -xf -
git -C "$TMP/repo" init -q
git -C "$TMP/repo" add -A
git -C "$TMP/repo" -c user.name=contract-test -c user.email=contract@example.invalid \
  commit --allow-empty -qm "contract fixture"
launcher_pass="$TMP/new-parent/nested/launcher-pass"
env SRUN_BIN="$TMP/mock-srun" OUT_DIR="$launcher_pass" \
  "$TMP/repo/scripts/slurm/run_zd_pair_synth.sh" > "$TMP/launcher-pass.out"
grep -Fx EISA_H_ZD_PAIR_SLURM_PASS "$TMP/launcher-pass.out" >/dev/null
grep -E '^srun_stderr_sha256=[0-9a-f]{64}$' "$TMP/launcher-pass.out" >/dev/null

env SRUN_BIN="$TMP/mock-srun" OUT_DIR="$TMP/launcher-formal-pass" \
  "$TMP/repo/scripts/slurm/run_zd_pair_formal.sh" > "$TMP/launcher-formal-pass.out"
grep -Fx EISA_H_ZD_PAIR_FORMAL_SLURM_PASS "$TMP/launcher-formal-pass.out" >/dev/null

env SRUN_BIN="$TMP/mock-srun" \
  MOCK_PARTITION_FIXTURE_DIR="$TMP/formal-partition-emit-pass" \
  OUT_DIR="$TMP/launcher-formal-partition-emit-pass" \
  "$TMP/repo/scripts/slurm/run_zd_pair_formal_partition_emit.sh" \
  > "$TMP/launcher-formal-partition-emit-pass.out"
grep -Fx EISA_H_STATE_PARTITION_EMIT_SLURM_PASS \
  "$TMP/launcher-formal-partition-emit-pass.out" >/dev/null

expect_rc 42 env SRUN_BIN="$TMP/mock-srun" MOCK_SRUN_MODE=missing \
  OUT_DIR="$TMP/launcher-missing" "$TMP/repo/scripts/slurm/run_zd_pair_synth.sh"
grep -F "mock scheduler rejected payload" "$TMP/launcher-missing/srun.err" >/dev/null
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$ORIGINAL_HEAD" ]]

echo "SLURM_LAUNCHER_CONTRACT_PASS cases=32"
