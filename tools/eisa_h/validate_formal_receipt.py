#!/usr/bin/env python3
"""Validate the split formal-obligation contract for EISA-H ZD-pair v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_manifest(root: pathlib.Path) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "formal_id": "eisa_h.sedenion_zd_pair.formal.v1",
        "rtl_implementation_id": "eisa_h.sedenion_zd_pair.rtl.v1",
        "source_rtl_sha256": sha256(root / "rtl/eisa_h_sed16_zd_pair_v1.sv"),
        "recipes": {
            "surface_sha256": sha256(
                root / "scripts/yosys/formal_zd_pair_surface_v1.ys"
            ),
            "reset_base_sha256": sha256(
                root / "scripts/yosys/formal_zd_pair_reset_base_v1.ys"
            ),
            "state_step_sha256": sha256(
                root / "scripts/yosys/formal_zd_pair_step_v1.ys"
            ),
        },
        "post_synthesis_manifest_sha256": sha256(
            root / "spec/eisa_h/sedenion_zd_pair_postsynth_v1.json"
        ),
        "tool": {"name": "yosys", "reference_version": "0.33"},
        "surface": {
            "state_normalization": ["async2sync"],
            "clock_model": "one implicit shared positive edge per SAT step",
            "clock_waveform_equivalence": "NOT_CLAIMED",
            "public_outputs": {
                "ready": 1,
                "busy": 1,
                "done": 1,
                "classification": 2,
                "error_code": 3,
                "product_is_zero": 1,
                "product_flat": 1024,
                "mac_cycles": 9,
            },
            "public_equiv_bits": 1042,
            "public_map_sha256": "a01c87792b972a115ebd57836a4eb2f1d5d7c11014ae8d4adcef88870fba5123",
            "state_relation_breakdown": {
                "lhs_latched": 1024,
                "rhs_latched": 1024,
                "accumulator": 1024,
                "product": 1024,
                "control_and_status": 26,
            },
            "state_relation_bits": 4122,
            "state_map_sha256": "36255aaf229111de447a2f6f4245c011a7847a599c7d9f98cc34ae479b11b2a7",
            "public_state_overlap_bits": 17,
            "proof_relation_bits": 5147,
            "proof_map_sha256": "57f65e8af872f8dc4c45282f536041bd644e0dd8c5f1ed052cf533bd7cf3df79",
            "closure_extras": {
                "bits": 32,
                "map_sha256": "0ca975a011e8f5aa02da6c9b283feddd1d23cb924275f2dce218d2d8421f5cbe",
                "structural_map_sha256": "e2b7b57ba90618d8d0ec407fdd2598d255de6880f4b5a428502e7c7fca99a112",
                "identity": "lhs_nonzero_count[31:16] plus rhs_nonzero_count[31:16]",
                "proof": "equiv_simple -short -seq 1",
                "status": "PROVED",
            },
            "miter_equiv_cone_cells": 5179,
            "miter_proven_support_cells": 32,
            "miter_unproven_relation_cells": 5147,
            "state_step_cmp_bits": 5147,
            "state_step_cmp_map_sha256": "855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35",
        },
        "obligations": {
            "reset_base": {
                "antecedent": "rst_n=0 at step 1; rst_n=1 at step 2; shared defined inputs",
                "consequent": "the exact 5147-bit state-plus-public relation holds at step 2",
                "undef_modeling": True,
                "evidence": {
                    "status": "CNF_EMITTED_YOSYS_UNSAT_EXTERNAL_CERTIFICATE_PENDING",
                    "cnf_variables": 3304588,
                    "cnf_clauses": 8926674,
                    "cnf_bytes": 366667787,
                    "cnf_sha256": "ba2a9b0c064855380f4b81d729574f48dee62b16cc02c99f506da33d9d8b4eeb",
                    "yosys_result": "UNSAT",
                    "proof_sha256": None,
                    "independent_replay": "NOT_RUN",
                },
            },
            "state_step": {
                "antecedent": "the exact 5147-bit state-plus-public relation holds at step t; shared defined inputs",
                "consequent": "the same exact relation holds at step t+1",
                "undef_modeling": False,
                "evidence": {
                    "status": "CNF_EMITTED_SOLVER_NOT_RUN",
                    "cnf_variables": 3052420,
                    "cnf_clauses": 8276177,
                    "cnf_bytes": 340131200,
                    "cnf_sha256": "0b5ccf1c1a025ff3fdbc5c4a0a1354d77995b2cd130d41672bceadbf28ac0a8d",
                    "cmp_bits": 5147,
                    "cmp_map_sha256": "855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35",
                    "solver": None,
                    "result": "NOT_RUN",
                    "proof_sha256": None,
                    "certificate_status": "NONE",
                },
            },
        },
        "historical_evidence": {
            "expanded_miter_reset_base": {
                "status": "CERTIFIED_UNSAT_SUPERSET",
                "relation_bits": 5179,
                "cnf_sha256": "fc1bff43ba18322ae2677c7a9b0391ce4d4eefcfb2b29d9e55fff66c3d6893cf",
                "proof_sha256": "8f457cd35957cee266442b602af656711a1563dc930d9e292c8142094221d3b9",
                "solver": "cadical-1.7.3",
                "solver_binary_sha256": "7b73df0a6d9cf3c751a1948300e5baff8e82c4d39bcd88f0c063b5f5cfb8b33e",
                "checker": "drat-trim",
                "checker_binary_sha256": "92f0aa9575ed519d66a99b8b1b3dde6ece4618ae4c202a3a4b200265dda0aa7a",
                "independent_replay": "VERIFIED_TWICE",
                "current_use": "HISTORICAL_IMPLIES_EXACT_RESET_CONCLUSION_NOT_CURRENT_CNF_CERTIFICATE",
            },
            "expanded_miter_state_step": {
                "status": "SOLVER_TIMEOUT_NOT_EXACT_P5147_GEOMETRY",
                "relation_bits": 5179,
                "cnf_sha256": "2804931a99b458db7c3cee99fec2b7829206776d7e2e2b74d4c6451876caead0",
                "solver": "cadical-1.7.3",
                "timeout_seconds": 1200,
                "result": "UNKNOWN",
                "conflicts": 3865544,
                "incomplete_proof_sha256": "6dd520a6925e985588683e8ac1f530346c43e832b1396580ca34e17d776044d5",
                "certificate_status": "NONE_PARTIAL_TRACE_NOT_REPLAYED",
            },
            "slurm_job_id": 5817,
            "slurm_node": "gpuorangefs-multi-r740-proxmox",
        },
        "reference_evidence": {
            "status": "GEOMETRY_REPAIRED_CURRENT_CERTIFICATES_PENDING",
            "reset_base_independent_replay": "NOT_RUN_CURRENT_CNF",
            "state_step_independent_replay": "NOT_RUN_CURRENT_CNF",
        },
        "claim": {
            "formal_equivalence": "NOT_CLAIMED",
            "reset_base": "YOSYS_UNSAT_EXTERNAL_CERTIFICATE_PENDING",
            "state_step": "EXACT_CNF_EMITTED_SOLVER_PENDING",
            "arbitrary_initial_state_equivalence": "NOT_CLAIMED",
            "timing": "NOT_CLAIMED",
            "silicon": "NOT_CLAIMED",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=pathlib.Path)
    parser.add_argument("proof_log", type=pathlib.Path, nargs="?")
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest_path = (
        args.manifest.resolve()
        if args.manifest
        else root / "spec/eisa_h/sedenion_zd_pair_formal_v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest != expected_manifest(root):
        raise SystemExit("formal manifest mismatch")
    if args.contract_only:
        print(
            "EISA_H_ZD_PAIR_FORMAL_CONTRACT_PASS "
            "public_equiv_bits=1042 state_relation_bits=4122 "
            "proof_relation_bits=5147 closure_extras_proved=32 "
            "reference_evidence=GEOMETRY_REPAIRED_CURRENT_CERTIFICATES_PENDING"
        )
        return 0
    if args.proof_log is None:
        parser.error("proof_log is required without --contract-only")
    raise SystemExit("full formal proof validation is blocked: state_step certificate missing")


if __name__ == "__main__":
    raise SystemExit(main())
