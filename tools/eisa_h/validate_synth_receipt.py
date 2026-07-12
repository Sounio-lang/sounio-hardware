#!/usr/bin/env python3
"""Validate deterministic generic-synthesis evidence for EISA-H ZD-pair v1."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_manifest(root: pathlib.Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "synthesis_id": "eisa_h.sedenion_zd_pair.synth.v1",
        "rtl_implementation_id": "eisa_h.sedenion_zd_pair.rtl.v1",
        "top_module": "eisa_h_sed16_zd_pair_v1",
        "source_rtl_sha256": sha256(root / "rtl/eisa_h_sed16_zd_pair_v1.sv"),
        "recipe": {
            "path": "scripts/yosys/synth_zd_pair_v1.ys",
            "sha256": sha256(root / "scripts/yosys/synth_zd_pair_v1.ys"),
        },
        "abi": {
            "coefficient_encoding": "signed-twos-complement-i64",
            "coefficient_width_bits": 64,
            "coefficient_count": 16,
            "lane_order": "lane-i-is-bits-(64*i)+:64",
            "lane_zero_position": "bits-63:0",
            "intra_lane_bit_order": "lsb0",
            "packed_bus_signed": True,
            "clock_edge": "rising",
            "reset": "asynchronous-active-low",
            "start_acceptance": "rising-edge-when-ready",
        },
        "tool": {"name": "yosys", "reference_version": "0.33", "target": "generic-cell-netlist"},
        "expected_ports": {
            "clk": ["input", 1],
            "rst_n": ["input", 1],
            "start": ["input", 1],
            "lhs_flat": ["input", 1024],
            "rhs_flat": ["input", 1024],
            "ready": ["output", 1],
            "busy": ["output", 1],
            "done": ["output", 1],
            "classification": ["output", 2],
            "error_code": ["output", 3],
            "product_is_zero": ["output", 1],
            "product_flat": ["output", 1024],
            "mac_cycles": ["output", 9],
        },
        "reference_statistics": {
            "num_cells": 38133,
            "num_processes": 0,
            "num_memories": 0,
            "sequential_cells": 4122,
        },
        "reference_artifacts": {
            "stat_sha256": "8bbe66c3328a7284bee1ef87ccc69d4fcc936f9114beafe98e818ca32a5af095",
            "netlist_sha256": "43cda27f4bf2ec93cae841d3e26a375079a35a914cc107ef32b1fc7ca542e316",
        },
        "claim": {
            "execution_surface": "generic_synthesis",
            "technology_mapping": "NOT_CLAIMED",
            "post_synthesis_equivalence": "NOT_CLAIMED",
            "timing": "NOT_CLAIMED",
            "power": "NOT_CLAIMED",
            "area": "GENERIC_CELL_COUNT_ONLY",
            "determinism": "SAME_TOOL_SAME_HOST_REPLAY_ONLY",
            "fpga": "NOT_CLAIMED",
            "asic": "NOT_CLAIMED",
            "silicon": "NOT_CLAIMED",
        },
    }


def main() -> int:
    if len(sys.argv) not in (4, 5):
        raise SystemExit("usage: validate_synth_receipt.py <root> <stat.json> <netlist.json> [manifest]")
    root = pathlib.Path(sys.argv[1]).resolve()
    stat_path = pathlib.Path(sys.argv[2]).resolve()
    netlist_path = pathlib.Path(sys.argv[3]).resolve()
    manifest_path = (
        pathlib.Path(sys.argv[4]).resolve()
        if len(sys.argv) == 5
        else root / "spec/eisa_h/sedenion_zd_pair_synth_v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != expected_manifest(root):
        raise SystemExit("synthesis manifest mismatch")
    if sha256(stat_path) != manifest["reference_artifacts"]["stat_sha256"]:
        raise SystemExit("synthesis statistics artifact hash mismatch")
    if sha256(netlist_path) != manifest["reference_artifacts"]["netlist_sha256"]:
        raise SystemExit("synthesized netlist artifact hash mismatch")

    statistics = json.loads(stat_path.read_text(encoding="utf-8"))
    expected_creator_prefix = f"Yosys {manifest['tool']['reference_version']} "
    if not statistics.get("creator", "").startswith(expected_creator_prefix):
        raise SystemExit(f"unexpected Yosys statistics creator: {statistics.get('creator')}")
    module_stats = statistics["modules"]["\\eisa_h_sed16_zd_pair_v1"]
    reference = manifest["reference_statistics"]
    sequential = sum(
        count for kind, count in module_stats["num_cells_by_type"].items() if "DFF" in kind
    )
    observed = {
        "num_cells": module_stats["num_cells"],
        "num_processes": module_stats["num_processes"],
        "num_memories": module_stats["num_memories"],
        "sequential_cells": sequential,
    }
    if observed != reference:
        raise SystemExit(f"synthesis statistics mismatch: {observed}")

    netlist = json.loads(netlist_path.read_text(encoding="utf-8"))
    if not netlist.get("creator", "").startswith(expected_creator_prefix):
        raise SystemExit(f"unexpected Yosys netlist creator: {netlist.get('creator')}")
    module = netlist["modules"]["eisa_h_sed16_zd_pair_v1"]
    ports = {name: [details["direction"], len(details["bits"])] for name, details in module["ports"].items()}
    if ports != manifest["expected_ports"]:
        raise SystemExit(f"synthesized port contract mismatch: {ports}")
    signed_ports = {name for name, details in module["ports"].items() if details.get("signed") == 1}
    if signed_ports != {"lhs_flat", "rhs_flat", "product_flat"}:
        raise SystemExit(f"synthesized signed-port contract mismatch: {sorted(signed_ports)}")
    sequential_types = {kind for kind in module_stats["num_cells_by_type"] if "DFF" in kind}
    if any("_PN" not in kind for kind in sequential_types):
        raise SystemExit(f"unexpected clock/reset polarity in sequential cells: {sorted(sequential_types)}")
    unknown_constants = []
    for cell_name, cell in module["cells"].items():
        for port_name, bits in cell.get("connections", {}).items():
            if any(bit in ("x", "z") for bit in bits if isinstance(bit, str)):
                unknown_constants.append(f"{cell_name}.{port_name}")
    if unknown_constants:
        raise SystemExit(f"unknown constants in synthesized cells: {unknown_constants[:5]}")
    for net_name, net in module.get("netnames", {}).items():
        if any(bit in ("x", "z") for bit in net.get("bits", []) if isinstance(bit, str)):
            raise SystemExit(f"unknown constant in synthesized net: {net_name}")

    print(
        "EISA_H_ZD_PAIR_SYNTH_VALIDATION_PASS "
        f"cells={observed['num_cells']} sequential={sequential} processes=0 memories=0 "
        f"stat_sha256={sha256(stat_path)} netlist_sha256={sha256(netlist_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
