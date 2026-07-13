#!/usr/bin/env python3
"""Validate a returned Slurm synthesis receipt without trusting its metadata."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pathlib
import re

REQUIRED_FILES = {"request.txt", "worker_meta.txt", "gate.log", "gate.rc"}
ARTIFACT_PREFIX = "formal_artifacts/"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PARTITIONS = ("latches", "accumulator", "product_and_alias", "control")
EXPECTED_PARTITIONS = {
    "latches": (2048, "54a3e6384fb662a56e08e0b0d899d94d2ad7bcfc6fd44cfee79f4933e7b6b9e3"),
    "accumulator": (1024, "0f3a495682f2ae93ef620ed30e229ad52239eccc06b244bc666a74b3c4c2d2b8"),
    "product_and_alias": (2048, "7f4607dde489da1140c30ec205962baee8ba0441b6493237464d792cc6d94cf7"),
    "control": (27, "d0f0885a182150eed6d1f5544105a071469c8bf75560cabc6390c0227a2efa61"),
}
FULL_CMP_SHA256 = "855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35"
TEMPORAL_FLAGS = (
    "-seq 2",
    "-set-at 1 trigger 0",
    "-set-def-inputs",
    "-set-init-def",
    "-prove-skip 1",
    "-prove-asserts",
)
PARTITION_EMIT_REQUIRED_ARTIFACTS = {
    "formal_artifacts/BUNDLE_SHA256SUMS",
    "formal_artifacts/recipe_bundle/partition_manifest.json",
    "formal_artifacts/recipe_bundle/SHA256SUMS",
    *{
        f"formal_artifacts/recipe_bundle/{prefix}{partition}{suffix}"
        for partition in PARTITIONS
        for prefix, suffix in (
            ("state_step_", ".ys"),
            ("emit_state_step_", ".sh"),
        )
    },
    *{
        f"formal_artifacts/{partition}/{name}"
        for partition in PARTITIONS
        for name in (
            "obligation.cnf.gz",
            "recipe.ys",
            "temporal_driver.sh",
            "yosys.log",
            "SHA256SUMS",
        )
    },
}
GATES = {
    "synthesis": {
        "markers": (
            "EISA_H_ZD_PAIR_SYNTH_GATE_PASS",
            "EISA_H_ZD_PAIR_POSTSYNTH_GATE_PASS",
        ),
        "pass": "EISA_H_ZD_PAIR_SLURM_PASS",
    },
    "formal": {
        "markers": ("EISA_H_ZD_PAIR_FORMAL_GATE_PASS",),
        "pass": "EISA_H_ZD_PAIR_FORMAL_SLURM_PASS",
    },
    "formal-partition-emit": {
        "markers": (
            "EISA_H_STATE_PARTITION_EMIT_PASS",
            "partitions=4 antecedent_bits=5147 consequent_union_bits=5147",
        ),
        "pass": "EISA_H_STATE_PARTITION_EMIT_SLURM_PASS",
        "required_artifacts": PARTITION_EMIT_REQUIRED_ARTIFACTS,
    },
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_kv(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            raise ValueError(f"malformed metadata line in {path}: {line!r}")
        key, value = line.split("=", 1)
        if not key or key in result:
            raise ValueError(f"duplicate or empty metadata key in {path}: {key!r}")
        result[key] = value
    return result


def validate_checksums(root: pathlib.Path) -> set[str]:
    manifest = root / "SHA256SUMS"
    if not manifest.is_file():
        raise ValueError("missing SHA256SUMS")
    observed_files: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
        if match is None:
            raise ValueError(f"malformed checksum line: {line!r}")
        expected, name = match.groups()
        relative = pathlib.PurePosixPath(name)
        allowed_artifact = name.startswith(ARTIFACT_PREFIX)
        if (
            name in observed_files
            or relative.is_absolute()
            or ".." in relative.parts
            or (name not in REQUIRED_FILES and not allowed_artifact)
        ):
            raise ValueError(f"unexpected or duplicate checksum target: {name}")
        path = root / name
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"missing checksum target: {name}") from error
        if (
            path.is_symlink()
            or root not in resolved.parents
            or not resolved.is_file()
            or sha256(resolved) != expected
        ):
            raise ValueError(f"checksum mismatch: {name}")
        observed_files.add(name)
    missing = REQUIRED_FILES - observed_files
    if missing:
        raise ValueError(f"checksum coverage mismatch: missing={sorted(missing)}")
    artifact_root = root / ARTIFACT_PREFIX.rstrip("/")
    actual_artifacts = (
        {
            path.relative_to(root).as_posix()
            for path in artifact_root.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        if artifact_root.exists()
        else set()
    )
    listed_artifacts = {
        name for name in observed_files if name.startswith(ARTIFACT_PREFIX)
    }
    if listed_artifacts != actual_artifacts:
        raise ValueError(
            "artifact checksum coverage mismatch: "
            f"listed={sorted(listed_artifacts)} actual={sorted(actual_artifacts)}"
        )
    return observed_files


def validate_partition_bundle(root: pathlib.Path) -> None:
    artifact_root = root / "formal_artifacts"
    manifest = artifact_root / "BUNDLE_SHA256SUMS"
    listed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_./-]+)", line)
        if match is None:
            raise ValueError(f"malformed partition bundle checksum line: {line!r}")
        expected, name = match.groups()
        relative = pathlib.PurePosixPath(name)
        if name in listed or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe or duplicate partition bundle target: {name}")
        path = artifact_root / name
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"missing partition bundle target: {name}") from error
        if (
            path.is_symlink()
            or artifact_root not in resolved.parents
            or not resolved.is_file()
            or sha256(resolved) != expected
        ):
            raise ValueError(f"partition bundle checksum mismatch: {name}")
        listed.add(name)
    actual = {
        path.relative_to(artifact_root).as_posix()
        for path in artifact_root.rglob("*")
        if path.is_file() and path.name != "BUNDLE_SHA256SUMS"
    }
    if listed != actual:
        raise ValueError(
            "partition bundle checksum coverage mismatch: "
            f"listed={sorted(listed)} actual={sorted(actual)}"
        )
    validate_fixed_manifest(
        artifact_root / "recipe_bundle",
        {
            "partition_manifest.json",
            *{
                f"{prefix}{partition}{suffix}"
                for partition in PARTITIONS
                for prefix, suffix in (
                    ("state_step_", ".ys"),
                    ("emit_state_step_", ".sh"),
                )
            },
        },
    )
    for partition in PARTITIONS:
        validate_fixed_manifest(
            artifact_root / partition,
            {"obligation.cnf.gz", "recipe.ys", "temporal_driver.sh", "yosys.log"},
        )
    validate_partition_semantics(root)


def validate_fixed_manifest(directory: pathlib.Path, expected_names: set[str]) -> None:
    manifest = directory / "SHA256SUMS"
    observed: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None:
            raise ValueError(f"malformed nested checksum line in {manifest}: {line!r}")
        expected, name = match.groups()
        path = directory / name
        if name in observed or name not in expected_names or not path.is_file():
            raise ValueError(f"unexpected nested checksum target in {manifest}: {name}")
        if path.is_symlink() or sha256(path) != expected:
            raise ValueError(f"nested checksum mismatch in {manifest}: {name}")
        observed.add(name)
    if observed != expected_names:
        raise ValueError(
            f"nested checksum coverage mismatch in {manifest}: "
            f"observed={sorted(observed)} expected={sorted(expected_names)}"
        )


def names_sha256(names: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(names)) + "\n").encode()).hexdigest()


def validate_partition_semantics(root: pathlib.Path) -> None:
    artifact_root = root / "formal_artifacts"
    recipe_root = artifact_root / "recipe_bundle"
    repository_root = pathlib.Path(__file__).resolve().parents[2]
    formal_contract = json.loads(
        (repository_root / "spec/eisa_h/sedenion_zd_pair_formal_v1.json").read_text(
            encoding="utf-8"
        )
    )
    pinned_partitioning = formal_contract["surface"]["state_step_partitioning"]
    pinned_partitions = pinned_partitioning["partitions"]
    if (
        formal_contract["schema_version"] != 6
        or pinned_partitioning["partition_count"] != 4
        or pinned_partitioning["consequent_union_bits"] != 5147
        or set(pinned_partitions) != set(PARTITIONS)
    ):
        raise ValueError("local formal partition contract mismatch")
    manifest = json.loads(
        (recipe_root / "partition_manifest.json").read_text(encoding="utf-8")
    )
    if set(manifest) != {
        "schema_version",
        "antecedent",
        "consequent",
        "temporal_flags",
        "full_cmp_bits",
        "full_cmp_map_sha256",
        "partition_count",
        "pairwise_disjoint",
        "exact_union",
        "partitions",
    }:
        raise ValueError("partition manifest field set mismatch")
    if (
        manifest["schema_version"] != 1
        or manifest["antecedent"] != "full state_step_miter trigger=0 at step 1"
        or manifest["consequent"] != "partition asserts at step 2"
        or manifest["temporal_flags"] != list(TEMPORAL_FLAGS)
        or manifest["full_cmp_bits"] != 5147
        or manifest["full_cmp_map_sha256"] != FULL_CMP_SHA256
        or manifest["partition_count"] != 4
        or manifest["pairwise_disjoint"] is not True
        or manifest["exact_union"] is not True
        or set(manifest["partitions"]) != set(PARTITIONS)
    ):
        raise ValueError("partition manifest semantic mismatch")

    base_recipe = (repository_root / "scripts/yosys/formal_zd_pair_step_v1.ys").read_text(
        encoding="utf-8"
    ).rstrip()
    gate_log = (root / "gate.log").read_text(encoding="utf-8")
    receipts = {}
    receipt_re = re.compile(
        r"^partition=(\w+) cnf_status=EMITTED vars=(\d+) clauses=(\d+) "
        r"bytes=(\d+) sha256=([0-9a-f]{64})$",
        re.MULTILINE,
    )
    for match in receipt_re.finditer(gate_log):
        partition, variables, clauses, byte_count, digest = match.groups()
        if partition in receipts:
            raise ValueError(f"duplicate CNF receipt: {partition}")
        receipts[partition] = tuple(map(int, (variables, clauses, byte_count))) + (digest,)
    if set(receipts) != set(PARTITIONS):
        raise ValueError(f"CNF receipt set mismatch: {sorted(receipts)}")

    union: list[str] = []
    for partition in PARTITIONS:
        expected_count, expected_map_sha256 = EXPECTED_PARTITIONS[partition]
        partition_manifest = manifest["partitions"][partition]
        pinned_partition = pinned_partitions[partition]
        if set(partition_manifest) != {
            "assert_bits",
            "cmp_map_sha256",
            "recipe_sha256",
            "temporal_driver_sha256",
        }:
            raise ValueError(f"partition manifest field mismatch: {partition}")
        if (
            partition_manifest["assert_bits"] != expected_count
            or partition_manifest["cmp_map_sha256"] != expected_map_sha256
            or pinned_partition["assert_bits"] != expected_count
            or pinned_partition["cmp_map_sha256"] != expected_map_sha256
            or partition_manifest["recipe_sha256"]
            != pinned_partition["recipe_sha256"]
            or partition_manifest["temporal_driver_sha256"]
            != pinned_partition["temporal_driver_sha256"]
        ):
            raise ValueError(f"partition identity mismatch: {partition}")

        recipe = recipe_root / f"state_step_{partition}.ys"
        driver = recipe_root / f"emit_state_step_{partition}.sh"
        recipe_text = recipe.read_text(encoding="utf-8")
        separator = "\n\ncd state_step_miter\n"
        if recipe_text.count(separator) != 1:
            raise ValueError(f"partition recipe separator mismatch: {partition}")
        prefix, suffix = recipe_text.split(separator)
        if prefix != base_recipe:
            raise ValueError(f"partition recipe base mismatch: {partition}")
        lines = suffix.splitlines()
        add_lines = [line for line in lines if line.startswith("add -assert \\")]
        expected_trailer = [
            f"select -assert-count {expected_count} t:$assert",
            f"log EISA_H_STEP_PARTITION name={partition} assert_bits={expected_count}",
        ]
        if len(add_lines) != expected_count or lines[-2:] != expected_trailer:
            raise ValueError(f"partition recipe assertion mismatch: {partition}")
        cmp_names = [
            "state_step_miter/" + line.removeprefix("add -assert \\")
            for line in add_lines
        ]
        if len(set(cmp_names)) != expected_count or names_sha256(cmp_names) != expected_map_sha256:
            raise ValueError(f"partition recipe cmp map mismatch: {partition}")
        union.extend(cmp_names)
        if sha256(recipe) != pinned_partition["recipe_sha256"]:
            raise ValueError(f"partition recipe digest mismatch: {partition}")

        driver_text = driver.read_text(encoding="utf-8")
        if (
            any(driver_text.count(flag) != 1 for flag in TEMPORAL_FLAGS)
            or driver_text.count(f"state_step_{partition}.ys") != 1
            or driver_text.count("-verify-no-timeout -timeout 1 -dump_cnf $CNF") != 1
            or sha256(driver) != pinned_partition["temporal_driver_sha256"]
        ):
            raise ValueError(f"partition temporal driver mismatch: {partition}")

        partition_root = artifact_root / partition
        if (
            (partition_root / "recipe.ys").read_bytes() != recipe.read_bytes()
            or (partition_root / "temporal_driver.sh").read_bytes() != driver.read_bytes()
        ):
            raise ValueError(f"partition recipe copy mismatch: {partition}")
        yosys_log = (partition_root / "yosys.log").read_text(encoding="utf-8")
        dump_match = re.search(r"Dumping CNF to file `([^']+)'.", yosys_log)
        outcome_positions = [
            position
            for marker in (
                "Interrupted SAT solver: TIMEOUT!",
                "SAT proof finished - no model found: SUCCESS!",
            )
            if (position := yosys_log.find(marker)) >= 0
        ]
        if (
            yosys_log.count(
                f"EISA_H_STEP_PARTITION name={partition} assert_bits={expected_count}"
            ) != 1
            or dump_match is None
            or yosys_log.count("Dumping CNF to file `") != 1
            or sum(
                yosys_log.count(marker)
                for marker in (
                    "Interrupted SAT solver: TIMEOUT!",
                    "SAT proof finished - no model found: SUCCESS!",
                )
            )
            != 1
            or len(outcome_positions) != 1
            or dump_match.start() >= outcome_positions[0]
            or pathlib.PurePosixPath(dump_match.group(1)).name != f"{partition}.cnf"
        ):
            raise ValueError(f"partition Yosys log semantic mismatch: {partition}")
        validate_dimacs_gzip(partition_root / "obligation.cnf.gz", receipts[partition])

    if len(union) != 5147 or len(set(union)) != 5147 or names_sha256(union) != FULL_CMP_SHA256:
        raise ValueError("partition recipe union mismatch")


def validate_dimacs_gzip(path: pathlib.Path, receipt: tuple[int, int, int, str]) -> None:
    expected_variables, expected_clauses, expected_bytes, expected_sha256 = receipt
    digest = hashlib.sha256()
    variables = None
    declared_clauses = None
    observed_clauses = 0
    observed_bytes = 0
    with gzip.open(path, "rb") as stream:
        for line_number, raw in enumerate(stream, 1):
            digest.update(raw)
            observed_bytes += len(raw)
            line = raw.strip()
            if not line or line.startswith(b"c"):
                continue
            if line.startswith(b"p"):
                fields = line.split()
                if variables is not None or len(fields) != 4 or fields[:2] != [b"p", b"cnf"]:
                    raise ValueError(f"invalid DIMACS header in {path} line={line_number}")
                variables, declared_clauses = map(int, fields[2:])
                if variables <= 0 or declared_clauses <= 0:
                    raise ValueError(f"nonpositive DIMACS header in {path}")
                continue
            if variables is None:
                raise ValueError(f"DIMACS clause before header in {path}")
            try:
                literals = [int(value) for value in line.split()]
            except ValueError as error:
                raise ValueError(f"invalid DIMACS clause in {path} line={line_number}") from error
            if (
                not literals
                or literals[-1] != 0
                or any(value == 0 for value in literals[:-1])
                or any(abs(value) > variables for value in literals[:-1])
            ):
                raise ValueError(f"invalid DIMACS clause in {path} line={line_number}")
            observed_clauses += 1
    if (
        variables != expected_variables
        or declared_clauses != expected_clauses
        or observed_clauses != expected_clauses
        or observed_bytes != expected_bytes
        or digest.hexdigest() != expected_sha256
    ):
        raise ValueError(f"DIMACS receipt mismatch: {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=pathlib.Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--srun-rc", required=True, type=int)
    parser.add_argument("--gate-id", required=True, choices=sorted(GATES))
    args = parser.parse_args()
    root = args.artifact_dir.resolve()
    classification = "FORMAL" if args.gate_id.startswith("formal") else "SYNTH"
    try:
        if not COMMIT_RE.fullmatch(args.expected_commit):
            raise ValueError("invalid expected commit")
        observed_files = validate_checksums(root)
        request = load_kv(root / "request.txt")
        worker = load_kv(root / "worker_meta.txt")
        gate_rc = int((root / "gate.rc").read_text(encoding="utf-8").strip())
        job_id = worker.get("slurm_job_id", "")
        node = worker.get("slurm_node", "")
        source = worker.get("source_commit", "")
        request_source = request.get("source_commit", "")
        repo_sha = request.get("repo_manifest_sha256", "")
        toolchain_sha = request.get("toolchain_manifest_sha256", "")
        request_gate = request.get("gate_id", "")
        worker_gate = worker.get("gate_id", "")
        if not job_id.isdigit() or int(job_id) <= 0:
            raise ValueError(f"invalid Slurm job ID: {job_id!r}")
        if not node or node == "unknown":
            raise ValueError(f"invalid Slurm node: {node!r}")
        if source != args.expected_commit or request_source != args.expected_commit:
            raise ValueError(f"source identity mismatch: worker={source} request={request_source}")
        if not SHA_RE.fullmatch(repo_sha) or worker.get("repo_manifest_sha256") != repo_sha:
            raise ValueError("repository manifest identity mismatch")
        if not SHA_RE.fullmatch(toolchain_sha) or worker.get("toolchain_manifest_sha256") != toolchain_sha:
            raise ValueError("toolchain manifest identity mismatch")
        if gate_rc != args.srun_rc:
            raise ValueError(f"return-code mismatch: srun={args.srun_rc} gate={gate_rc}")
        if request_gate != args.gate_id or worker_gate != args.gate_id:
            raise ValueError(
                f"gate identity mismatch: expected={args.gate_id} "
                f"request={request_gate} worker={worker_gate}"
            )
        if gate_rc == 0:
            required_artifacts = GATES[args.gate_id].get("required_artifacts", set())
            observed_artifacts = {
                name for name in observed_files if name.startswith(ARTIFACT_PREFIX)
            }
            if required_artifacts and observed_artifacts != required_artifacts:
                raise ValueError(
                    "gate-specific artifact set mismatch: "
                    f"observed={sorted(observed_artifacts)} "
                    f"expected={sorted(required_artifacts)}"
                )
            for name in required_artifacts:
                if (root / name).stat().st_size == 0:
                    raise ValueError(f"empty gate-specific artifact: {name}")
            if args.gate_id == "formal-partition-emit":
                validate_partition_bundle(root)
    except (EOFError, KeyError, OSError, TypeError, ValueError) as error:
        print(
            f"SLURM_{classification}_BLOCKED "
            f"reason=invalid_return_receipt detail={error}"
        )
        return 42

    gate_log = (root / "gate.log").read_text(encoding="utf-8")
    common = f"job_id={job_id} node={node} source_commit={source} artifact_dir={root}"
    if gate_rc == 42:
        print(f"SLURM_{classification}_BLOCKED reason=worker_gate_blocked {common}")
        return 42
    if gate_rc != 0:
        print(f"SLURM_{classification}_FAIL rc={gate_rc} {common}")
        return gate_rc
    required_markers = GATES[args.gate_id]["markers"]
    missing_markers = [
        marker for marker in required_markers if f"\n{marker}\n" not in f"\n{gate_log}"
    ]
    if missing_markers:
        print(
            f"SLURM_{classification}_BLOCKED reason=missing_gate_pass_marker "
            f"markers={','.join(missing_markers)}"
        )
        return 42
    print(GATES[args.gate_id]["pass"])
    print(common)
    print(f"gate_log_sha256={sha256(root / 'gate.log')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
