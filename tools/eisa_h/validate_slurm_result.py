#!/usr/bin/env python3
"""Validate a returned Slurm synthesis receipt without trusting its metadata."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re

REQUIRED_FILES = {"request.txt", "worker_meta.txt", "gate.log", "gate.rc"}
ARTIFACT_PREFIX = "formal_artifacts/"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
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


def validate_checksums(root: pathlib.Path) -> None:
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=pathlib.Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--srun-rc", required=True, type=int)
    parser.add_argument("--gate-id", required=True, choices=sorted(GATES))
    args = parser.parse_args()
    root = args.artifact_dir.resolve()
    try:
        if not COMMIT_RE.fullmatch(args.expected_commit):
            raise ValueError("invalid expected commit")
        validate_checksums(root)
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
    except (OSError, ValueError) as error:
        print(f"SLURM_SYNTH_BLOCKED reason=invalid_return_receipt detail={error}")
        return 42

    gate_log = (root / "gate.log").read_text(encoding="utf-8")
    common = f"job_id={job_id} node={node} source_commit={source} artifact_dir={root}"
    classification = "FORMAL" if args.gate_id == "formal" else "SYNTH"
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
