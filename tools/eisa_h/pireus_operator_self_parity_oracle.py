#!/usr/bin/env python3
"""Admissibility oracle for a PIREUS kind=2 operator self-parity receipt.

Unlike the other three PIREUS contracts in this repository, the receipts this
oracle judges come from a program that actually ran. The probe materialises one
operator twice -- once recomputing each structure coefficient from the phase
code, once reading a packed sign table through a lane permutation -- and
compares the two bit for bit.

What this establishes is narrow and worth stating twice: that two
materialisations of the same operator are the same function. It does not
establish that the operator is useful, that it is fast, or that it is
materialisable on any hardware other than the one that ran it. A receipt that
reaches for any of those is refused before any other field is read.

The three mutation controls are the load-bearing part. A self-parity probe with
inert controls proves nothing at all: two paths that are secretly the same code
agree trivially. So the receipt must show that corrupting the sign table, and
desynchronising the store lane map from the load lane map, each break parity.
The third control -- lowering cd_sigma instead of the twisted product -- must
break parity exactly when the twist is non-trivial, which is what proves the
probe measured the proposed operator rather than silently falling back to the
Cayley-Dickson base it extends.
"""

import argparse
import hashlib
import json
import pathlib

CONTRACT_ID = "eisa_h.pireus_operator_self_parity.v1"
DIMENSION = 16

FORBIDDEN_FIELD_SUBSTRINGS = (
    "gain", "speedup", "promotion", "median_ppm", "eligible",
    "faster", "throughput", "elapsed", "nanosecond", "cycles_per",
)

REQUIRED_FIELDS = (
    "schema", "producer_role", "semantic_authority_language", "kind",
    "phase_code", "lane_stride", "lane_offset", "dimension", "precision",
    "trials", "reference_derivation", "lowered_derivation",
    "shared_accumulation_order", "reassociated", "fma_contracted",
    "rounding_mode", "flush_to_zero", "denormals_are_zero",
    "mismatching_lanes", "first_mismatch", "sign_mutation_mismatching_lanes",
    "lane_mutation_mismatching_lanes", "twist_drop_mutation_mismatching_lanes",
    "twist_is_trivial", "establishes", "claim_ready", "fp_utility", "result",
)

INT_FIELDS = (
    "schema", "kind", "phase_code", "lane_stride", "lane_offset", "dimension",
    "precision", "trials", "mismatching_lanes", "first_mismatch",
    "sign_mutation_mismatching_lanes", "lane_mutation_mismatching_lanes",
    "twist_drop_mutation_mismatching_lanes",
)

BOOL_FIELDS = ("reassociated", "fma_contracted", "flush_to_zero",
               "denormals_are_zero", "twist_is_trivial", "claim_ready")


def _scan_forbidden(node, path, out):
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = key.lower()
            if any(bad in lowered for bad in FORBIDDEN_FIELD_SUBSTRINGS):
                out.append(f"{path}{key}")
            _scan_forbidden(value, f"{path}{key}.", out)
    elif isinstance(node, list):
        for n, value in enumerate(node):
            _scan_forbidden(value, f"{path}{n}.", out)


def evaluate(receipt):
    """Decide admissibility. The check order is part of the contract: the claim
    boundary is the outer obligation and is enforced before anything is read."""
    reasons = []
    if not isinstance(receipt, dict):
        return False, ["NOT_AN_OBJECT"]

    forbidden = []
    _scan_forbidden(receipt, "", forbidden)
    if forbidden:
        return False, [f"FORBIDDEN_FIELD:{n}" for n in sorted(forbidden)]

    missing = [f for f in REQUIRED_FIELDS if f not in receipt]
    if missing:
        return False, [f"MISSING_FIELD:{f}" for f in missing]

    for field in INT_FIELDS:
        raw = receipt[field]
        if isinstance(raw, bool) or not isinstance(raw, int):
            reasons.append(f"NOT_AN_INTEGER:{field}")
    for field in BOOL_FIELDS:
        if not isinstance(receipt[field], bool):
            reasons.append(f"NOT_A_BOOLEAN:{field}")
    if reasons:
        return False, reasons

    # -- provenance ------------------------------------------------------
    if receipt["schema"] != 1:
        reasons.append("SCHEMA")
    if receipt["producer_role"] != "OPERATOR_SELF_PARITY":
        reasons.append("PRODUCER_ROLE")
    if receipt["semantic_authority_language"] != "Sounio":
        reasons.append("AUTHORITY_NOT_SOUNIO")
    if receipt["kind"] != 2:
        reasons.append("KIND_NOT_OPERATOR_GENESIS")
    if receipt["dimension"] != DIMENSION or receipt["precision"] != 64:
        reasons.append("SHAPE")
    if not 0 <= receipt["phase_code"] < (1 << 16):
        reasons.append("PHASE_CODE_RANGE")

    stride, offset = receipt["lane_stride"], receipt["lane_offset"]
    if stride < 1 or stride > 15 or stride % 2 == 0:
        reasons.append("LANE_STRIDE")
    if not 0 <= offset <= 15:
        reasons.append("LANE_OFFSET")

    # -- the two paths must be comparable --------------------------------
    if receipt["reference_derivation"] == receipt["lowered_derivation"]:
        reasons.append("DERIVATIONS_NOT_INDEPENDENT")
    if receipt["reference_derivation"] != "recomputed_per_term":
        reasons.append("REFERENCE_DERIVATION")
    if receipt["lowered_derivation"] != "packed_sign_table_via_lane_map":
        reasons.append("LOWERED_DERIVATION")
    if receipt["shared_accumulation_order"] != "ascending_right_operand":
        reasons.append("ACCUMULATION_ORDER")

    # -- numeric environment ---------------------------------------------
    if receipt["rounding_mode"] != "FE_TONEAREST":
        reasons.append("ROUNDING_MODE")
    for flag in ("reassociated", "fma_contracted", "flush_to_zero", "denormals_are_zero"):
        if receipt[flag] is not False:
            reasons.append(f"NUMERIC_ENVIRONMENT:{flag}")
    if receipt["trials"] < 1:
        reasons.append("NO_TRIALS")

    # -- controls must fire ----------------------------------------------
    # A self-parity probe whose mutations are inert proves nothing: two paths
    # that are secretly the same code agree trivially.
    if receipt["sign_mutation_mismatching_lanes"] <= 0:
        reasons.append("SIGN_CONTROL_INERT")
    if receipt["lane_mutation_mismatching_lanes"] <= 0:
        reasons.append("LANE_CONTROL_INERT")

    trivial = receipt["phase_code"] == 0
    if receipt["twist_is_trivial"] != trivial:
        reasons.append("TWIST_TRIVIALITY_MISDECLARED")
    twist = receipt["twist_drop_mutation_mismatching_lanes"]
    if trivial and twist != 0:
        reasons.append("TWIST_CONTROL_FIRED_ON_THE_BASE")
    if not trivial and twist <= 0:
        # This is the control that proves the probe measured the proposed
        # operator instead of falling back to the algebra it extends.
        reasons.append("TWIST_CONTROL_INERT_ON_A_TWISTED_OPERATOR")

    # -- parity consistency ----------------------------------------------
    mismatching = receipt["mismatching_lanes"]
    if not 0 <= mismatching <= DIMENSION:
        reasons.append("MISMATCH_COUNT_RANGE")
    first = receipt["first_mismatch"]
    if mismatching == 0 and first != -1:
        reasons.append("FIRST_MISMATCH_WITHOUT_MISMATCH")
    if mismatching > 0 and not 0 <= first < DIMENSION:
        reasons.append("MISMATCH_WITHOUT_FIRST_MISMATCH")
    if receipt["result"] not in ("PASS", "FAIL"):
        reasons.append("RESULT")
    if receipt["result"] == "PASS" and mismatching != 0:
        reasons.append("PASS_WITH_MISMATCHING_LANES")

    # -- claim boundary ---------------------------------------------------
    if receipt["establishes"] != "two_materialisations_agree":
        reasons.append("OVERSTATED_ESTABLISHES")
    if receipt["claim_ready"] is not False:
        reasons.append("CLAIM_READY_MUST_BE_FALSE")
    if receipt["fp_utility"] != "NOT_ESTABLISHED":
        reasons.append("UTILITY_NOT_DISCLAIMED")

    return (not reasons), reasons


def load_and_run(schema_path, contract_path, vectors_path, receipts_path,
                 measured_path=None):
    schema = json.loads(schema_path.read_text())
    contract = json.loads(contract_path.read_text())
    vectors = json.loads(vectors_path.read_text())
    if contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("contract_id mismatch")
    for key in schema.get("required", []):
        if key not in contract:
            raise ValueError(f"contract missing {key!r}")
    if vectors.get("contract_id") != CONTRACT_ID:
        raise ValueError("vectors contract_id mismatch")

    boundary = contract["claim_boundary"]
    if boundary.get("establishes_utility") is not False:
        raise ValueError("claim_boundary must refuse to establish utility")
    if boundary.get("establishes_scientific_novelty") is not False:
        raise ValueError("claim_boundary must refuse to establish scientific novelty")
    if tuple(contract["declared"]["forbidden_field_substrings"]) != FORBIDDEN_FIELD_SUBSTRINGS:
        raise ValueError("declared forbidden substrings drift")
    if tuple(contract["declared"]["required_fields"]) != REQUIRED_FIELDS:
        raise ValueError("declared required fields drift")
    if contract["declared"]["reference_phase_code"] != 1128:
        raise ValueError("reference phase code drift")

    ident = {
        "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "vectors_sha256": hashlib.sha256(vectors_path.read_bytes()).hexdigest(),
    }

    cases = list(vectors["cases"])
    # Receipts produced by the probe that actually ran, when the gate supplies
    # them. A contract that only ever judges fixtures has never been executed.
    if measured_path is not None:
        for n, line in enumerate(measured_path.read_text().splitlines()):
            if not line.strip():
                continue
            cases.append({
                "case_id": f"measured_{n}",
                "note": "emitted by the probe during this gate run",
                "expect_accepted": True,
                "receipt": json.loads(line),
            })

    ids = [c["case_id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id")

    receipts, seen = [], set()
    for case in cases:
        accepted, reasons = evaluate(case["receipt"])
        if accepted != case["expect_accepted"]:
            raise ValueError(
                f"{case['case_id']}: expected accepted={case['expect_accepted']}, "
                f"got {accepted} reasons={reasons}")
        want = case.get("expect_reason_prefix")
        if want is not None and not any(r.startswith(want) for r in reasons):
            raise ValueError(f"{case['case_id']}: expected reason {want!r}, got {reasons}")
        seen.add(accepted)
        receipts.append({"case_id": case["case_id"], "accepted": accepted,
                         "reasons": sorted(reasons), **ident})
    if seen != {True, False}:
        raise ValueError("vectors must exercise both an accepted and a rejected receipt")
    if receipts_path is not None:
        receipts_path.write_text("".join(
            json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in receipts))
    return receipts


def mutation_selftest(schema_path, contract_path, vectors_path):
    import copy
    import tempfile

    contract = json.loads(contract_path.read_text())
    vectors = json.loads(vectors_path.read_text())
    contract_mutations = [
        lambda c: c["claim_boundary"].update({"establishes_utility": True}),
        lambda c: c["claim_boundary"].update({"establishes_scientific_novelty": True}),
        lambda c: c["declared"].update({"reference_phase_code": 0}),
        lambda c: c["declared"].update({"forbidden_field_substrings": ["gain"]}),
        lambda c: c["declared"]["required_fields"].remove("claim_ready"),
    ]
    vector_mutations = [
        lambda v: v["cases"][0].update({"expect_accepted": False}),
        lambda v: v["cases"][0]["receipt"].update({"mismatching_lanes": 3}),
        lambda v: v["cases"][0]["receipt"].update({"sign_mutation_mismatching_lanes": 0}),
        lambda v: v["cases"][0]["receipt"].update({"lane_mutation_mismatching_lanes": 0}),
        lambda v: v["cases"][0]["receipt"].update({"claim_ready": True}),
        lambda v: v["cases"].append(copy.deepcopy(v["cases"][0])),
    ]
    caught = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for n, fn in enumerate(contract_mutations):
            mutated = copy.deepcopy(contract)
            fn(mutated)
            path = root / f"c{n}.json"
            path.write_text(json.dumps(mutated))
            try:
                load_and_run(schema_path, path, vectors_path, None)
            except (ValueError, KeyError):
                caught += 1
            else:
                raise SystemExit(f"contract mutation {n} was not rejected")
        for n, fn in enumerate(vector_mutations):
            mutated = copy.deepcopy(vectors)
            fn(mutated)
            path = root / f"v{n}.json"
            path.write_text(json.dumps(mutated))
            try:
                load_and_run(schema_path, contract_path, path, None)
            except (ValueError, KeyError):
                caught += 1
            else:
                raise SystemExit(f"vector mutation {n} was not rejected")
    return caught


def main():
    parser = argparse.ArgumentParser(description=CONTRACT_ID)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    parser.add_argument("--contract", type=pathlib.Path, required=True)
    parser.add_argument("--vectors", type=pathlib.Path, required=True)
    parser.add_argument("--receipts", type=pathlib.Path)
    parser.add_argument("--measured", type=pathlib.Path,
                        help="JSONL of receipts emitted by the probe in this run")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        caught = mutation_selftest(args.schema, args.contract, args.vectors)
        load_and_run(args.schema, args.contract, args.vectors, args.receipts, args.measured)
        print(f"MUTATION_SELFTEST_PASS caught={caught}")
        return 0
    load_and_run(args.schema, args.contract, args.vectors, args.receipts, args.measured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
