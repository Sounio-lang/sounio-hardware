#!/usr/bin/env python3
"""Validate bounded post-synthesis simulation parity for EISA-H ZD-pair v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any


EXPECTED_SIMULATION_RECEIPT = (
    "EISA_H_ZD_PAIR_SIM_PASS completed_transactions=1039 "
    "aborted_by_reset_transactions=1 accepted_transactions=1040 fixed_v1_cases=15 "
    "contract_cases=9 adversarial_cases=6 signed_basis_combinations=1024 "
    "interface_reset_cases=1 mac_cycles=256 latency_cycles=257 handshake=VERIFIED\n"
)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_manifest(root: pathlib.Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "parity_id": "eisa_h.sedenion_zd_pair.postsynth.v1",
        "synthesis_id": "eisa_h.sedenion_zd_pair.synth.v1",
        "rtl_implementation_id": "eisa_h.sedenion_zd_pair.rtl.v1",
        "top_module": "eisa_h_sed16_zd_pair_v1",
        "source_rtl_sha256": sha256(root / "rtl/eisa_h_sed16_zd_pair_v1.sv"),
        "testbench_sha256": sha256(root / "tb/eisa_h/tb_sed16_zd_pair_v1.sv"),
        "recipe_sha256": sha256(root / "scripts/yosys/synth_zd_pair_v1.ys"),
        "synthesis_manifest_sha256": sha256(
            root / "spec/eisa_h/sedenion_zd_pair_synth_v1.json"
        ),
        "simulator": {"name": "iverilog", "reference_version": "12.0"},
        "coverage": {
            "completed_transactions": 1039,
            "aborted_by_reset_transactions": 1,
            "accepted_transactions": 1040,
            "signed_basis_combinations": 1024,
            "semantic_cases": 9,
            "adversarial_cases": 6,
            "interface_reset_cases": 1,
            "mac_cycles": 256,
            "latency_cycles": 257,
        },
        "reference_artifacts": {
            "netlist_verilog_sha256": "c0ed60eb8fdc895a74b5307cab260205e166f1025c73adb5c0e9aaf6229d2f5c",
            "simulation_log_sha256": "5336edb784e4fa938bead43707700994c3b8c572af20ed28befba8e3a4609b1d",
        },
        "claim": {
            "execution_surface": "post_synthesis_simulation",
            "equivalence": "SIGNED_BASIS_EXHAUSTIVE_PLUS_FIXED_V1_CASES_SIMULATION_PARITY",
            "formal_equivalence": "NOT_CLAIMED",
            "technology_mapping": "NOT_CLAIMED",
            "timing": "NOT_CLAIMED",
            "power": "NOT_CLAIMED",
            "fpga": "NOT_CLAIMED",
            "asic": "NOT_CLAIMED",
            "silicon": "NOT_CLAIMED",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=pathlib.Path)
    parser.add_argument("netlist", type=pathlib.Path, nargs="?")
    parser.add_argument("simulation_log", type=pathlib.Path, nargs="?")
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--simulator-version", required=True)
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest
        else root / "spec/eisa_h/sedenion_zd_pair_postsynth_v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != expected_manifest(root):
        raise SystemExit("post-synthesis parity manifest mismatch")
    if args.simulator_version != manifest["simulator"]["reference_version"]:
        raise SystemExit(
            f"post-synthesis simulator version mismatch: {args.simulator_version}"
        )
    if args.contract_only:
        print("EISA_H_ZD_PAIR_POSTSYNTH_CONTRACT_PASS")
        return 0
    if args.netlist is None or args.simulation_log is None:
        parser.error("netlist and simulation_log are required without --contract-only")
    netlist_path = args.netlist.resolve()
    simulation_path = args.simulation_log.resolve()
    artifacts = manifest["reference_artifacts"]
    if sha256(netlist_path) != artifacts["netlist_verilog_sha256"]:
        raise SystemExit("post-synthesis Verilog netlist hash mismatch")
    if sha256(simulation_path) != artifacts["simulation_log_sha256"]:
        raise SystemExit("post-synthesis simulation log hash mismatch")
    if simulation_path.read_text(encoding="utf-8") != EXPECTED_SIMULATION_RECEIPT:
        raise SystemExit("post-synthesis simulation receipt mismatch")
    print(
        "EISA_H_ZD_PAIR_POSTSYNTH_VALIDATION_PASS "
        f"netlist_verilog_sha256={sha256(netlist_path)} "
        f"simulation_log_sha256={sha256(simulation_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
