#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PARTITION="${PARTITION:-all}"
CPUS="${CPUS:-4}"
MEMORY="${MEMORY:-4G}"
GATE_ID="${EISA_H_GATE_ID:-synthesis}"
case "$GATE_ID" in
  synthesis) DEFAULT_TIME_LIMIT="01:00:00" ;;
  formal) DEFAULT_TIME_LIMIT="00:30:00" ;;
  *) echo "SLURM_GATE_BLOCKED reason=unsupported_gate gate_id=$GATE_ID" >&2; exit 42 ;;
esac
TIME_LIMIT="${TIME_LIMIT:-$DEFAULT_TIME_LIMIT}"
RUN_ID="${RUN_ID:-eisa-h-zd-$GATE_ID-$(date -u +%Y%m%dT%H%M%S.%NZ)-$$-$RANDOM}"
OUT_DIR="${OUT_DIR:-/tmp/sounio-hardware-slurm/$RUN_ID}"
STAGE="$(mktemp -d)"
PAYLOAD="$STAGE/payload.tgz"
WORKER_ROOT="/tmp/zdtool"
SRUN_BIN="${SRUN_BIN:-srun}"
trap 'rm -rf "$STAGE"' EXIT

if ! mkdir -p "$(dirname "$OUT_DIR")" 2>/dev/null; then
  echo "SLURM_SYNTH_BLOCKED reason=cannot_create_output_parent artifact_dir=$OUT_DIR" >&2
  exit 42
fi
if ! mkdir "$OUT_DIR" 2>/dev/null; then
  echo "SLURM_SYNTH_BLOCKED reason=output_dir_exists artifact_dir=$OUT_DIR" >&2
  exit 42
fi
if [[ -n "$(git -C "$ROOT" status --porcelain=v1)" ]]; then
  echo "SLURM_SYNTH_BLOCKED reason=dirty_worktree" >&2
  exit 42
fi
for tool in "$SRUN_BIN" base64 tar python3 yosys yosys-abc iverilog vvp ldd strings; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "SLURM_SYNTH_BLOCKED reason=missing_local_tool tool=$tool" >&2
    exit 42
  fi
done
SOURCE_COMMIT="$(git -C "$ROOT" rev-parse HEAD)"
YOSYS_BIN="$(command -v yosys)"
YOSYS_ABC_BIN="$(command -v yosys-abc)"
IVERILOG_BIN="$(command -v iverilog)"
VVP_BIN="$(command -v vvp)"
LOADER_PATH="$(ldd "$YOSYS_BIN" 2>/dev/null | awk '$1 ~ /^\/.*ld-linux/ { print $1; exit }')"
if [[ -z "$LOADER_PATH" || ! -f "$LOADER_PATH" ]]; then
  echo "SLURM_SYNTH_BLOCKED reason=unresolved_elf_loader" >&2
  exit 42
fi
LOADER_SHA="$(sha256sum "$LOADER_PATH" | cut -d' ' -f1)"
for binary in "$YOSYS_ABC_BIN" "$IVERILOG_BIN" "$VVP_BIN"; do
  binary_loader="$(ldd "$binary" 2>/dev/null | awk '$1 ~ /^\/.*ld-linux/ { print $1; exit }')"
  if [[ "$binary_loader" != "$LOADER_PATH" ]]; then
    echo "SLURM_SYNTH_BLOCKED reason=heterogeneous_elf_loaders binary=$binary" >&2
    exit 42
  fi
done

resolve_embedded_dir() {
  local binary="$1" marker="$2" candidate
  while IFS= read -r candidate; do
    if [[ -d "$candidate" && -e "$candidate/$marker" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done < <(strings "$binary" | sed -En '/^\/.*\/yosys\/$/p; /^\/.*\/ivl\/?$/p' | LC_ALL=C sort -u)
  return 1
}

if ! YOSYS_DATA_DIR="$(resolve_embedded_dir "$YOSYS_BIN" simlib.v)"; then
  echo "SLURM_SYNTH_BLOCKED reason=unresolved_yosys_data_dir" >&2
  exit 42
fi
if ! IVL_DIR="$(resolve_embedded_dir "$IVERILOG_BIN" ivl)"; then
  echo "SLURM_SYNTH_BLOCKED reason=unresolved_iverilog_module_dir" >&2
  exit 42
fi

mkdir -p "$STAGE/repo" "$STAGE/toolchain/bin" "$STAGE/toolchain/data" \
  "$STAGE/toolchain/ivl" "$STAGE/toolchain/lib"
git -C "$ROOT" archive "$SOURCE_COMMIT" | tar -xf - -C "$STAGE/repo"
(cd "$STAGE/repo" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
  > "$STAGE/repo.SHA256SUMS"
REPO_MANIFEST_SHA="$(sha256sum "$STAGE/repo.SHA256SUMS" | cut -d' ' -f1)"

cp "$YOSYS_BIN" "$STAGE/toolchain/bin/yosys"
cp "$YOSYS_ABC_BIN" "$STAGE/toolchain/bin/yosys-abc"
cp "$IVERILOG_BIN" "$STAGE/toolchain/bin/iverilog.real"
cp "$VVP_BIN" "$STAGE/toolchain/bin/vvp.real"
cp -a "$YOSYS_DATA_DIR/." "$STAGE/toolchain/data/"
cp -a "$IVL_DIR/." "$STAGE/toolchain/ivl/"

copy_dependency() {
  local dependency="$1" destination existing
  destination="$STAGE/toolchain/lib/$(basename "$dependency")"
  if [[ -e "$destination" ]]; then
    existing="$(sha256sum "$destination" | cut -d' ' -f1)"
    if [[ "$existing" != "$(sha256sum "$dependency" | cut -d' ' -f1)" ]]; then
      echo "SLURM_SYNTH_BLOCKED reason=library_basename_collision library=$(basename "$dependency")" >&2
      exit 42
    fi
    return
  fi
  cp -L "$dependency" "$destination"
}

collect_dependencies() {
  local target="$1" dependency
  while IFS= read -r dependency; do
    [[ -n "$dependency" ]] && copy_dependency "$dependency"
  done < <(ldd "$target" 2>/dev/null | awk \
    '$2 == "=>" && $3 ~ /^\// { print $3 } $1 ~ /^\// { print $1 }')
}

for binary in "$YOSYS_BIN" "$YOSYS_ABC_BIN" "$IVERILOG_BIN" "$VVP_BIN"; do
  collect_dependencies "$binary"
done
while IFS= read -r -d '' module; do
  collect_dependencies "$module"
done < <(find "$IVL_DIR" -type f \
  \( -perm /111 -o -name '*.vpi' \) -print0)

if ! python3 - "$STAGE/toolchain/bin/yosys" "${YOSYS_DATA_DIR%/}/" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
data = path.read_bytes()
old = sys.argv[2].encode()
new = b"/tmp/zdtool/data/"
if len(old) != len(new) or data.count(old) != 1:
    raise SystemExit("unexpected Yosys data-path encoding")
path.write_bytes(data.replace(old, new))
PY
then
  echo "SLURM_SYNTH_BLOCKED reason=unsupported_yosys_data_path_encoding" >&2
  exit 42
fi

printf '%s\n' '#!/usr/bin/env bash' \
  "exec $WORKER_ROOT/bin/iverilog.real -B $WORKER_ROOT/ivl \"\$@\"" \
  > "$STAGE/toolchain/bin/iverilog"
printf '%s\n' '#!/usr/bin/env bash' \
  "exec $WORKER_ROOT/bin/vvp.real -M $WORKER_ROOT/ivl \"\$@\"" \
  > "$STAGE/toolchain/bin/vvp"
chmod +x "$STAGE/toolchain/bin/"*

(cd "$STAGE/toolchain" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
  > "$STAGE/toolchain.SHA256SUMS"
TOOLCHAIN_MANIFEST_SHA="$(sha256sum "$STAGE/toolchain.SHA256SUMS" | cut -d' ' -f1)"

printf '%s\n' \
  "run_id=$RUN_ID" \
  "gate_id=$GATE_ID" \
  "source_commit=$SOURCE_COMMIT" \
  "repo_manifest_sha256=$REPO_MANIFEST_SHA" \
  "toolchain_manifest_sha256=$TOOLCHAIN_MANIFEST_SHA" \
  "toolchain_platform=linux-x86_64-glibc-loader-pinned" \
  "elf_loader_path=$LOADER_PATH" \
  "elf_loader_sha256=$LOADER_SHA" \
  "partition=$PARTITION" \
  "cpus=$CPUS" \
  "memory=$MEMORY" \
  "time_limit=$TIME_LIMIT" \
  > "$STAGE/request.txt"
tar -C "$STAGE" -czf "$PAYLOAD" repo toolchain request.txt repo.SHA256SUMS \
  toolchain.SHA256SUMS

WORKER_OUT="$OUT_DIR/worker.out"
set +e
base64 -w0 "$PAYLOAD" | "$SRUN_BIN" \
  -p "$PARTITION" -N1 -n1 -c "$CPUS" --mem="$MEMORY" --time="$TIME_LIMIT" \
  --chdir=/tmp bash -lc '
set -euo pipefail
ROOT=/tmp/zdtool
exec 9>/tmp/zdtool.lock
flock -x 9
rm -rf "$ROOT"
mkdir -p "$ROOT"
base64 -d > "$ROOT/payload.tgz"
tar -xzf "$ROOT/payload.tgz" -C "$ROOT"
(cd "$ROOT/toolchain" && sha256sum -c "$ROOT/toolchain.SHA256SUMS" >/dev/null)
expected_toolchain_manifest=$(sed -n "s/^toolchain_manifest_sha256=//p" "$ROOT/request.txt")
observed_toolchain_manifest=$(sha256sum "$ROOT/toolchain.SHA256SUMS" | cut -d" " -f1)
[[ -n "$expected_toolchain_manifest" && "$observed_toolchain_manifest" == "$expected_toolchain_manifest" ]]
loader_path=$(sed -n "s/^elf_loader_path=//p" "$ROOT/request.txt")
loader_sha=$(sed -n "s/^elf_loader_sha256=//p" "$ROOT/request.txt")
[[ -f "$loader_path" && "$loader_sha" == "$(sha256sum "$loader_path" | cut -d" " -f1)" ]]
mv "$ROOT/toolchain/"* "$ROOT/"
rmdir "$ROOT/toolchain"
export PATH="$ROOT/bin:$PATH"
export LD_LIBRARY_PATH="$ROOT/lib:${LD_LIBRARY_PATH:-}"
(cd "$ROOT/repo" && sha256sum -c "$ROOT/repo.SHA256SUMS" >/dev/null)
expected_repo_manifest=$(sed -n "s/^repo_manifest_sha256=//p" "$ROOT/request.txt")
observed_repo_manifest=$(sha256sum "$ROOT/repo.SHA256SUMS" | cut -d" " -f1)
[[ -n "$expected_repo_manifest" && "$observed_repo_manifest" == "$expected_repo_manifest" ]]
gate_id=$(sed -n "s/^gate_id=//p" "$ROOT/request.txt")
case "$gate_id" in
  synthesis) gate_script=scripts/gate_zd_pair_synth.sh ;;
  formal) gate_script=scripts/gate_zd_pair_formal.sh ;;
  *) exit 42 ;;
esac
mkdir -p "$ROOT/result"
cp "$ROOT/request.txt" "$ROOT/result/request.txt"
printf "%s\n" \
  "slurm_job_id=${SLURM_JOB_ID:-unknown}" \
  "slurm_node=$(hostname)" \
  "gate_id=$gate_id" \
  "source_commit=$(sed -n "s/^source_commit=//p" "$ROOT/request.txt")" \
  "repo_manifest_sha256=$observed_repo_manifest" \
  "toolchain_manifest_sha256=$observed_toolchain_manifest" \
  "worker_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "yosys_version=$(yosys -V)" \
  "iverilog_version=$(iverilog -V 2>&1 | sed -n "1p")" \
  > "$ROOT/result/worker_meta.txt"
cd "$ROOT/repo"
if [[ "$gate_id" == "formal" ]]; then
  export EISA_H_FORMAL_ARTIFACT_DIR="$ROOT/result/formal_artifacts"
fi
set +e
bash "$gate_script" > "$ROOT/result/gate.log" 2>&1
rc=$?
set -e
printf "%s\n" "$rc" > "$ROOT/result/gate.rc"
(cd "$ROOT/result" && \
  find . -type f ! -path ./SHA256SUMS -print0 | LC_ALL=C sort -z | \
  xargs -0 sha256sum | sed "s#  \\./#  #" > SHA256SUMS)
tar -C "$ROOT/result" -czf "$ROOT/result.tgz" .
printf "__SOUNIO_SLURM_RESULT__"
base64 -w0 "$ROOT/result.tgz"
printf "\n"
exit "$rc"
' > "$WORKER_OUT" 2> "$OUT_DIR/srun.err"
srun_rc=$?
set -e

RESULT_LINE="$(sed -n 's/^__SOUNIO_SLURM_RESULT__//p' "$WORKER_OUT" | tail -1)"
if [[ -z "$RESULT_LINE" ]]; then
  echo "SLURM_SYNTH_BLOCKED reason=missing_result_payload srun_rc=$srun_rc worker_log=$WORKER_OUT stderr_log=$OUT_DIR/srun.err" >&2
  tail -40 "$OUT_DIR/srun.err" >&2 || true
  exit 42
fi
printf '%s' "$RESULT_LINE" | base64 -d > "$OUT_DIR/result.tgz"
tar -xzf "$OUT_DIR/result.tgz" -C "$OUT_DIR"
set +e
python3 "$ROOT/tools/eisa_h/validate_slurm_result.py" "$OUT_DIR" \
  --expected-commit "$SOURCE_COMMIT" --srun-rc "$srun_rc" --gate-id "$GATE_ID"
validation_rc=$?
set -e
if [[ "$validation_rc" != "0" ]]; then
  tail -40 "$OUT_DIR/gate.log" >&2 || true
else
  printf 'srun_stderr_sha256=%s\n' "$(sha256sum "$OUT_DIR/srun.err" | cut -d' ' -f1)"
fi
exit "$validation_rc"
