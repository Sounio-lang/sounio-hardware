#!/usr/bin/env python3
"""Validate the bounded RTL integration manifest against repository artifacts."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: validate_rtl_manifest.py <repository-root> [manifest]")
    root = pathlib.Path(sys.argv[1]).resolve()
    manifest_path = (
        pathlib.Path(sys.argv[2]).resolve()
        if len(sys.argv) == 3
        else root / "spec/eisa_h/sedenion_zd_pair_rtl_v1.json"
    )
    contract_path = root / "spec/eisa_h/sedenion_zd_pair_v1.json"
    rtl_path = root / "rtl/eisa_h_sed16_zd_pair_v1.sv"
    testbench_path = root / "tb/eisa_h/tb_sed16_zd_pair_v1.sv"
    vectors_path = root / "vectors/eisa_h/sedenion_zd_pair_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": 1,
        "implementation_id": "eisa_h.sedenion_zd_pair.rtl.v1",
        "semantic_contract_id": "eisa_h.sedenion_zd_pair.v1",
        "semantic_contract_sha256": sha256(contract_path),
        "module": "eisa_h_sed16_zd_pair_v1",
        "interface": "packed-16x64-coefficient-buses",
        "datapath": {
            "architecture": "iterative-single-mac",
            "basis_products": 256,
            "mac_cycles": 256,
            "finalize_cycles": 1,
            "accumulators": 16,
            "accumulator_width_bits": 64,
        },
        "coverage": {
            "semantic_contract_cases": 10,
            "rtl_representable_cases": 9,
            "adversarial_boundary_cases": 6,
            "basis_sign_combinations": 1024,
            "completed_transactions": 1039,
            "aborted_by_reset_transactions": 1,
            "accepted_transactions": 1040,
            "handshake": "verified-in-simulation",
            "interface_rejected_cases": ["invalid-operand-shape"],
        },
        "artifacts": {
            "rtl_sha256": sha256(rtl_path),
            "testbench_sha256": sha256(testbench_path),
            "semantic_vectors_sha256": sha256(vectors_path),
        },
        "expected_simulation_receipt": (
            "EISA_H_ZD_PAIR_SIM_PASS completed_transactions=1039 "
            "aborted_by_reset_transactions=1 accepted_transactions=1040 fixed_v1_cases=15 "
            "contract_cases=9 adversarial_cases=6 signed_basis_combinations=1024 "
            "interface_reset_cases=1 mac_cycles=256 latency_cycles=257 handshake=VERIFIED"
        ),
        "claim": {
            "execution_surface": "rtl_simulation",
            "synthesis": "NOT_CLAIMED",
            "formal_equivalence": "NOT_CLAIMED",
            "timing": "NOT_CLAIMED",
            "power": "NOT_CLAIMED",
            "area": "NOT_CLAIMED",
            "silicon": "NOT_CLAIMED",
        },
    }
    if manifest != expected:
        raise SystemExit("RTL manifest does not match the v1 integration contract")
    print(
        "RTL_MANIFEST_PASS "
        f"manifest_sha256={sha256(manifest_path)} "
        f"semantic_contract_sha256={sha256(contract_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
