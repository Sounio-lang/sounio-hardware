#!/usr/bin/env python3
"""Generate exact consequent-partition recipes for the EISA-H state step."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


FULL_COUNT = 5147
FULL_MAP_SHA256 = "855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35"
EXPECTED_PARTITIONS = {
    "latches": (2048, "54a3e6384fb662a56e08e0b0d899d94d2ad7bcfc6fd44cfee79f4933e7b6b9e3"),
    "accumulator": (1024, "0f3a495682f2ae93ef620ed30e229ad52239eccc06b244bc666a74b3c4c2d2b8"),
    "product_and_alias": (2048, "7f4607dde489da1140c30ec205962baee8ba0441b6493237464d792cc6d94cf7"),
    "control": (27, "d0f0885a182150eed6d1f5544105a071469c8bf75560cabc6390c0227a2efa61"),
}
TEMPORAL_FLAGS = (
    "-seq 2",
    "-set-at 1 trigger 0",
    "-set-def-inputs",
    "-set-init-def",
    "-prove-skip 1",
    "-prove-asserts",
)


def names_sha256(names: list[str]) -> str:
    payload = "\n".join(sorted(names)) + "\n"
    return hashlib.sha256(payload.encode()).hexdigest()


def extract_cmp_names(log: pathlib.Path) -> list[str]:
    text = log.read_text(encoding="utf-8")
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
    if len(names) != FULL_COUNT or len(set(names)) != FULL_COUNT:
        raise SystemExit(
            f"state-step cmp map mismatch: observed={len(names)} "
            f"unique={len(set(names))} expected={FULL_COUNT}"
        )
    observed_sha256 = names_sha256(names)
    if observed_sha256 != FULL_MAP_SHA256:
        raise SystemExit(
            "state-step cmp map identity mismatch: "
            f"observed={observed_sha256} expected={FULL_MAP_SHA256}"
        )
    return names


def classify(name: str) -> str:
    local_name = name.removeprefix("state_step_miter/")
    if local_name.startswith(("cmp_lhs_latched[", "cmp_rhs_latched[")):
        return "latches"
    if local_name.startswith("cmp_accumulator["):
        return "accumulator"
    if local_name.startswith(("cmp_product[", "cmp_product_flat[")):
        return "product_and_alias"
    return "control"


def write_recipe(base: str, names: list[str], output: pathlib.Path, partition: str) -> None:
    lines = [base.rstrip(), "", "cd state_step_miter"]
    for name in sorted(names):
        local_name = name.removeprefix("state_step_miter/")
        lines.append(f"add -assert \\{local_name}")
    lines.extend(
        [
            f"select -assert-count {len(names)} t:$assert",
            f"log EISA_H_STEP_PARTITION name={partition} assert_bits={len(names)}",
            "",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def write_driver(output_dir: pathlib.Path, partition: str) -> pathlib.Path:
    output = output_dir / f"emit_state_step_{partition}.sh"
    text = f'''#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" != "2" ]]; then
  echo "usage: $0 ABSOLUTE_CNF_PATH ABSOLUTE_LOG_PATH" >&2
  exit 2
fi
CNF="$1"
LOG="$2"
if [[ ! "$CNF" =~ ^/[A-Za-z0-9_./-]+$ || ! "$LOG" =~ ^/[A-Za-z0-9_./-]+$ ]]; then
  echo "partition emitter requires absolute paths without whitespace" >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
yosys -Q -T -s "$SCRIPT_DIR/state_step_{partition}.ys" -p \\
  "sat -seq 2 -set-at 1 trigger 0 -set-def-inputs -set-init-def -prove-skip 1 -prove-asserts -verify-no-timeout -timeout 1 -dump_cnf $CNF" \\
  > "$LOG" 2>&1
'''
    for flag in TEMPORAL_FLAGS:
        if text.count(flag) != 1:
            raise SystemExit(f"temporal driver flag mismatch partition={partition} flag={flag}")
    output.write_text(text, encoding="utf-8")
    output.chmod(0o755)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-log", required=True, type=pathlib.Path)
    parser.add_argument("--base-recipe", required=True, type=pathlib.Path)
    parser.add_argument("--output-dir", required=True, type=pathlib.Path)
    args = parser.parse_args()

    names = extract_cmp_names(args.map_log)
    partitions = {name: [] for name in EXPECTED_PARTITIONS}
    for name in names:
        partitions[classify(name)].append(name)

    union: set[str] = set()
    manifest_partitions = {}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    base = args.base_recipe.read_text(encoding="utf-8")
    for partition, partition_names in partitions.items():
        expected_count, expected_sha256 = EXPECTED_PARTITIONS[partition]
        observed_sha256 = names_sha256(partition_names)
        if len(partition_names) != expected_count or observed_sha256 != expected_sha256:
            raise SystemExit(
                f"partition mismatch name={partition} count={len(partition_names)} "
                f"sha256={observed_sha256} expected_count={expected_count} "
                f"expected_sha256={expected_sha256}"
            )
        overlap = union.intersection(partition_names)
        if overlap:
            raise SystemExit(f"partition overlap name={partition} example={min(overlap)}")
        union.update(partition_names)
        recipe = args.output_dir / f"state_step_{partition}.ys"
        write_recipe(base, partition_names, recipe, partition)
        driver = write_driver(args.output_dir, partition)
        manifest_partitions[partition] = {
            "assert_bits": len(partition_names),
            "cmp_map_sha256": observed_sha256,
            "recipe_sha256": hashlib.sha256(recipe.read_bytes()).hexdigest(),
            "temporal_driver_sha256": hashlib.sha256(driver.read_bytes()).hexdigest(),
        }

    if union != set(names) or names_sha256(list(union)) != FULL_MAP_SHA256:
        raise SystemExit("partition union does not reproduce the full cmp map")

    manifest = {
        "schema_version": 1,
        "antecedent": "full state_step_miter trigger=0 at step 1",
        "consequent": "partition asserts at step 2",
        "temporal_flags": list(TEMPORAL_FLAGS),
        "full_cmp_bits": FULL_COUNT,
        "full_cmp_map_sha256": FULL_MAP_SHA256,
        "partition_count": len(partitions),
        "pairwise_disjoint": True,
        "exact_union": True,
        "partitions": manifest_partitions,
    }
    manifest_path = args.output_dir / "partition_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        "EISA_H_STATE_PARTITION_RECIPES_PASS "
        f"partitions={len(partitions)} cmp_bits={len(union)} "
        f"cmp_map_sha256={names_sha256(list(union))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
