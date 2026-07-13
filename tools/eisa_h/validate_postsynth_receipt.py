#!/usr/bin/env python3
"""Validate bounded post-synthesis simulation parity for EISA-H ZD-pair v1."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any


EXPECTED_SIMULATION_RECEIPT = (
    "EISA_H_ZD_PAIR_RTL_PASS rtl_cases=15 contract_cases=9 adversarial_cases=6 "
    "basis_sign_combinations=1024 interface_cases=1 mac_cycles=256 "
    "latency_cycles=257 handshake=VERIFIED\n"
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
            "observed_transactions": 1039,
            "basis_sign_combinations": 1024,
            "semantic_cases": 9,
            "adversarial_cases": 6,
            "interface_reset_cases": 1,
            "mac_cycles": 256,
            "latency_cycles": 257,
        },
        "reference_artifacts": {
            "netlist_verilog_sha256": "TO_BE_PINNED_FROM_SLURM",
            "simulation_log_sha256": "TO_BE_PINNED_FROM_SLURM",
        },
        "claim": {
            "execution_surface": "post_synthesis_simulation",
            "equivalence": "BOUNDED_EXHAUSTIVE_V1_SIMULATION_PARITY",
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
    if len(sys.argv) not in (4, 5):
        raise SystemExit(
            "usage: validate_postsynth_receipt.py <root> <netlist.v> <simulation.log> [manifest]"
        )
    root = pathlib.Path(sys.argv[1]).resolve()
    netlist_path = pathlib.Path(sys.argv[2]).resolve()
    simulation_path = pathlib.Path(sys.argv[3]).resolve()
    manifest_path = (
        pathlib.Path(sys.argv[4]).resolve()
        if len(sys.argv) == 5
        else root / "spec/eisa_h/sedenion_zd_pair_postsynth_v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != expected_manifest(root):
        raise SystemExit("post-synthesis parity manifest mismatch")
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
