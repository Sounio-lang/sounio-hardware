#!/usr/bin/env python3
"""Validate Yosys temporal-induction evidence for EISA-H ZD-pair v1."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
from typing import Any


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_manifest(root: pathlib.Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "formal_id": "eisa_h.sedenion_zd_pair.formal.v1",
        "rtl_implementation_id": "eisa_h.sedenion_zd_pair.rtl.v1",
        "source_rtl_sha256": sha256(root / "rtl/eisa_h_sed16_zd_pair_v1.sv"),
        "recipe_sha256": sha256(root / "scripts/yosys/formal_zd_pair_v1.ys"),
        "post_synthesis_manifest_sha256": sha256(
            root / "spec/eisa_h/sedenion_zd_pair_postsynth_v1.json"
        ),
        "tool": {"name": "yosys", "reference_version": "0.33"},
        "method": {
            "state_normalization": ["async2sync", "clk2fflogic"],
            "proof": "equiv_induct",
            "undef_modeling": True,
            "maximum_induction_sequence": 4,
        },
        "reference_evidence": {
            "equiv_cells": -1,
            "proven_cells": -1,
            "unproven_cells": 0,
            "proof_log_sha256": "TO_BE_PINNED_FROM_SLURM",
        },
        "claim": {
            "formal_surface": "OBSERVABLE_SYNC_CONDITIONAL_TEMPORAL_INDUCTION_NON_DIVERGENCE",
            "reset_anchor": "SEPARATE_POST_SYNTHESIS_SIMULATION_RECEIPT",
            "arbitrary_initial_state_equivalence": "NOT_CLAIMED",
            "formal_equivalence_without_precondition": "NOT_CLAIMED",
            "timing": "NOT_CLAIMED",
            "silicon": "NOT_CLAIMED",
        },
    }


def parse_log(text: str) -> tuple[int, int, int]:
    status = re.findall(r"Found (\d+) \$equiv cells in equiv:\n  Of those cells (\d+) are proven and (\d+) are unproven\.", text)
    if len(status) != 1:
        raise ValueError(f"expected one final equivalence status, observed {len(status)}")
    cells, proven, unproven = map(int, status[0])
    if cells <= 0 or proven != cells or unproven != 0:
        raise ValueError(
            f"invalid equivalence totals: cells={cells} proven={proven} unproven={unproven}"
        )
    if text.count("Equivalence successfully proven!") != 1:
        raise ValueError("missing or duplicate success marker")
    if "Proof for induction step holds." not in text:
        raise ValueError("missing temporal induction proof marker")
    return cells, proven, unproven


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
        print("EISA_H_ZD_PAIR_FORMAL_CONTRACT_PASS")
        return 0
    if args.proof_log is None:
        parser.error("proof_log is required without --contract-only")
    log_path = args.proof_log.resolve()
    try:
        cells, proven, unproven = parse_log(log_path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise SystemExit(f"formal proof log mismatch: {error}") from error
    reference = manifest["reference_evidence"]
    observed = {
        "equiv_cells": cells,
        "proven_cells": proven,
        "unproven_cells": unproven,
        "proof_log_sha256": sha256(log_path),
    }
    if observed != reference:
        raise SystemExit(f"formal reference evidence mismatch: {observed}")
    print(
        "EISA_H_ZD_PAIR_FORMAL_VALIDATION_PASS "
        f"equiv_cells={cells} proven={proven} unproven={unproven} "
        f"proof_log_sha256={sha256(log_path)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
