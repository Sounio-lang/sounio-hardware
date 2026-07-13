#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if ! command -v yosys >/dev/null 2>&1; then
  echo "EISA_H_STATE_PARTITION_SURFACE_BLOCKED reason=yosys_unavailable" >&2
  exit 42
fi
YOSYS_VERSION="$(yosys -V | awk '{print $2}')"
if [[ "$YOSYS_VERSION" != "0.33" ]]; then
  printf 'EISA_H_STATE_PARTITION_SURFACE_BLOCKED reason=unsupported_yosys_version observed=%s expected=0.33\n' \
    "$YOSYS_VERSION" >&2
  exit 42
fi
if [[ -n "${EISA_H_PARTITION_RECIPE_DIR:-}" ]]; then
  mkdir -p "$EISA_H_PARTITION_RECIPE_DIR"
  if find "$EISA_H_PARTITION_RECIPE_DIR" -mindepth 1 -print -quit | grep -q .; then
    echo "EISA_H_STATE_PARTITION_SURFACE_BLOCKED reason=persist_destination_not_empty" >&2
    exit 42
  fi
fi

(cd "$ROOT" && yosys -Q -T -s scripts/yosys/formal_zd_pair_step_v1.ys \
  > "$TMP/state_step.log" 2>&1)
python3 "$ROOT/tools/eisa_h/generate_state_partition_recipes.py" \
  --map-log "$TMP/state_step.log" \
  --base-recipe "$ROOT/scripts/yosys/formal_zd_pair_step_v1.ys" \
  --output-dir "$TMP/partitions"

python3 - "$TMP/partitions/partition_manifest.json" <<'PY'
import json
import pathlib
import sys

manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = {
    "latches": (2048, "54a3e6384fb662a56e08e0b0d899d94d2ad7bcfc6fd44cfee79f4933e7b6b9e3", "1ee4f3418314cdb7518632f65ca2a6e5591332f2956dd6999f890692737bcbe4", "beaab6b0c3dbb645dbc5414b2212a86635d5eeec6a92575b25fdfde79d1c29a5"),
    "accumulator": (1024, "0f3a495682f2ae93ef620ed30e229ad52239eccc06b244bc666a74b3c4c2d2b8", "927ff5924cd28d508f0bc7ff87f5dffe6931974513e2f24a70bb26eb1b1e7819", "836d7c68b3a9312702ae3d813ddcd29c96043435bdd4f91f36d4ab525b8150e1"),
    "product_and_alias": (2048, "7f4607dde489da1140c30ec205962baee8ba0441b6493237464d792cc6d94cf7", "7f54f21de7683b4e226b081e934c8ec38a2ad6dfb805fbc5db623c79505e362a", "1f2c918dcb77e3f9648892eb7e59856f161970d744982be64ba6e573ccd97e8f"),
    "control": (27, "d0f0885a182150eed6d1f5544105a071469c8bf75560cabc6390c0227a2efa61", "5502179a5fcff831954c2bb127767129453d09abe32bfc2a88a22fe8bf57bea8", "e69acecc35d6042208842a89b183f77f8e71a8697735b61f98b1139fe0e453f2"),
}
if manifest["full_cmp_bits"] != 5147:
    raise SystemExit("partition union count mismatch")
if manifest["full_cmp_map_sha256"] != "855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35":
    raise SystemExit("partition union identity mismatch")
if manifest["partition_count"] != 4 or not manifest["pairwise_disjoint"] or not manifest["exact_union"]:
    raise SystemExit("partition coverage contract mismatch")
for name, (count, digest, recipe_digest, driver_digest) in expected.items():
    observed = manifest["partitions"][name]
    if (observed["assert_bits"], observed["cmp_map_sha256"], observed["recipe_sha256"], observed["temporal_driver_sha256"]) != (count, digest, recipe_digest, driver_digest):
        raise SystemExit(f"partition identity mismatch: {name}")
print("EISA_H_STATE_PARTITION_GEOMETRY_PASS antecedent_bits=5147 consequent_bits=5147 partitions=4")
PY

partitions=(latches accumulator product_and_alias control)
pids=()
for partition in "${partitions[@]}"; do
  bash -n "$TMP/partitions/emit_state_step_$partition.sh"
  (cd "$ROOT" && yosys -Q -T -s "$TMP/partitions/state_step_$partition.ys" \
    > "$TMP/$partition.log" 2>&1) &
  pids+=("$!")
done
recipe_rc=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    recipe_rc=1
  fi
done
if [[ "$recipe_rc" != "0" ]]; then
  echo "EISA_H_STATE_PARTITION_SURFACE_FAIL reason=generated_recipe_rejected" >&2
  exit 1
fi
for partition in "${partitions[@]}"; do
  grep -Fx "EISA_H_STEP_PARTITION name=$partition assert_bits=$(python3 - "$TMP/partitions/partition_manifest.json" "$partition" <<'PY'
import json
import pathlib
import sys
manifest = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(manifest["partitions"][sys.argv[2]]["assert_bits"])
PY
)" "$TMP/$partition.log" >/dev/null
done

python3 - "$TMP/partitions" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / "partition_manifest.json").read_text(encoding="utf-8"))
flags = manifest["temporal_flags"]
mutations = 0
for partition, receipt in manifest["partitions"].items():
    path = root / f"emit_state_step_{partition}.sh"
    text = path.read_text(encoding="utf-8")
    expected = receipt["temporal_driver_sha256"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"temporal driver identity mismatch: {partition}")
    for flag in flags:
        if text.count(flag) != 1:
            raise SystemExit(f"temporal flag count mismatch: {partition} {flag}")
        mutated = text.replace(flag, "", 1).encode()
        if hashlib.sha256(mutated).hexdigest() == expected:
            raise SystemExit(f"temporal mutation was not rejected: {partition} {flag}")
        mutations += 1
print(f"EISA_H_STATE_PARTITION_TEMPORAL_BINDING_PASS drivers=4 mutations_rejected={mutations}")
PY

if [[ -n "${EISA_H_PARTITION_RECIPE_DIR:-}" ]]; then
  bundle_files=(partition_manifest.json)
  for partition in "${partitions[@]}"; do
    bundle_files+=("state_step_$partition.ys" "emit_state_step_$partition.sh")
  done
  for file in "${bundle_files[@]}"; do
    cp "$TMP/partitions/$file" "$EISA_H_PARTITION_RECIPE_DIR/$file"
  done
  (cd "$EISA_H_PARTITION_RECIPE_DIR" && \
    sha256sum "${bundle_files[@]}" > SHA256SUMS)
  printf 'EISA_H_STATE_PARTITION_RECIPES_PERSISTED dir=%s\n' "$EISA_H_PARTITION_RECIPE_DIR"
fi

echo "EISA_H_STATE_PARTITION_SURFACE_PASS tool=yosys version=$YOSYS_VERSION"
