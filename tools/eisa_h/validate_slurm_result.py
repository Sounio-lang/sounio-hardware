#!/usr/bin/env python3
"""Validate a returned Slurm synthesis receipt without trusting its metadata."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import re

REQUIRED_FILES = {"request.txt", "worker_meta.txt", "gate.log", "gate.rc"}
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


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
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None:
            raise ValueError(f"malformed checksum line: {line!r}")
        expected, name = match.groups()
        if name in observed_files or name not in REQUIRED_FILES:
            raise ValueError(f"unexpected or duplicate checksum target: {name}")
        path = root / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"checksum mismatch: {name}")
        observed_files.add(name)
    if observed_files != REQUIRED_FILES:
        raise ValueError(f"checksum coverage mismatch: {sorted(observed_files)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_dir", type=pathlib.Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--srun-rc", required=True, type=int)
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
    except (OSError, ValueError) as error:
        print(f"SLURM_SYNTH_BLOCKED reason=invalid_return_receipt detail={error}")
        return 42

    gate_log = (root / "gate.log").read_text(encoding="utf-8")
    common = f"job_id={job_id} node={node} source_commit={source} artifact_dir={root}"
    if gate_rc == 42:
        print(f"SLURM_SYNTH_BLOCKED reason=worker_gate_blocked {common}")
        return 42
    if gate_rc != 0:
        print(f"SLURM_SYNTH_FAIL rc={gate_rc} {common}")
        return gate_rc
    required_markers = (
        "EISA_H_ZD_PAIR_SYNTH_GATE_PASS",
        "EISA_H_ZD_PAIR_POSTSYNTH_GATE_PASS",
    )
    missing_markers = [
        marker for marker in required_markers if f"\n{marker}\n" not in f"\n{gate_log}"
    ]
    if missing_markers:
        print(
            "SLURM_SYNTH_BLOCKED reason=missing_gate_pass_marker "
            f"markers={','.join(missing_markers)}"
        )
        return 42
    print("EISA_H_ZD_PAIR_SLURM_PASS")
    print(common)
    print(f"gate_log_sha256={sha256(root / 'gate.log')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
