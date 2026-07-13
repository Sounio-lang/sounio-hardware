#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ORIGINAL_HEAD="$(git -C "$ROOT" rev-parse HEAD)"
COMMIT="0123456789abcdef0123456789abcdef01234567"
REPO_SHA="$(printf 'a%.0s' {1..64})"
TOOLCHAIN_SHA="$(printf 'b%.0s' {1..64})"

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
  else
    printf 'gate failed rc=%s\n' "$gate_rc" > "$dir/gate.log"
  fi
  printf '%s\n' "$gate_rc" > "$dir/gate.rc"
  (cd "$dir" && sha256sum request.txt worker_meta.txt gate.log gate.rc > SHA256SUMS)
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
if [[ "$gate_id" == "formal" ]]; then
  printf '%s\n' EISA_H_ZD_PAIR_FORMAL_GATE_PASS > "$tmp/result/gate.log"
else
  printf '%s\n' \
    EISA_H_ZD_PAIR_SYNTH_GATE_PASS \
    EISA_H_ZD_PAIR_POSTSYNTH_GATE_PASS \
    > "$tmp/result/gate.log"
fi
printf '%s\n' 0 > "$tmp/result/gate.rc"
(cd "$tmp/result" && sha256sum request.txt worker_meta.txt gate.log gate.rc > SHA256SUMS)
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

expect_rc 42 env SRUN_BIN="$TMP/mock-srun" MOCK_SRUN_MODE=missing \
  OUT_DIR="$TMP/launcher-missing" "$TMP/repo/scripts/slurm/run_zd_pair_synth.sh"
grep -F "mock scheduler rejected payload" "$TMP/launcher-missing/srun.err" >/dev/null
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$ORIGINAL_HEAD" ]]

echo "SLURM_LAUNCHER_CONTRACT_PASS cases=13"
