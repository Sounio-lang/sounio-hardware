#!/usr/bin/env python3
"""Admissibility oracle for a PIREUS kind=2 operator-genesis proposal.

The kind=1 continuity path admits a *lowering* of a fixed operator, and its
acceptance criterion is bit-exact parity against cd_sigma: a reference exists,
so any divergence is an error. A kind=2 proposal names a new operator. No
reference exists, so parity against one is not merely unavailable -- it is the
wrong question. This oracle supplies what replaces it.

A kind=2 proposal is admitted only if all of the following hold, each
recomputed here from the phase code alone. Nothing is accepted on the
proposer's word; the proposal names a 16-bit phase code and declares what it
believes it built, and every declaration is a claim this oracle tries to
falsify.

  1. WELL-DEFINED   the 4096 structure coefficients reconstruct from the phase
                    code and agree with the lane-map reconstruction.
  2. NOVEL          the construction's affine class is not one the v1 grammar
                    already reaches. Decidable, not editorial.
  3. CHARACTERISED  every declared algebraic invariant -- associativity,
                    alternativity, flexibility, commutation, unitality --
                    matches exhaustive recomputation.
  4. BOUNDED        the proposal claims no performance, and carries the same
                    open obligations a kind=1 admission carries.

Admission establishes that the operator is well-defined, new, and honestly
described. It establishes nothing about utility, materialisability, or
floating-point behaviour. Those remain measured elsewhere or not at all.
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from pireus_operator_atlas_oracle import (  # noqa: E402
    DIMENSION,
    TAU,
    bilinear,
    build_atlas,
    classify,
    quadratic_code,
)

CONTRACT_ID = "eisa_h.pireus_operator_admission.v1"

# A receipt that carries any of these is describing something this contract
# does not measure. Checked before any field is read.
FORBIDDEN_FIELD_SUBSTRINGS = (
    "gain",
    "speedup",
    "promotion",
    "median_ppm",
    "eligible",
    "faster",
    "throughput",
)

REQUIRED_FIELDS = (
    "schema",
    "authority",
    "decision",
    "kind",
    "phase_code",
    "quadratic_code",
    "affine_class",
    "novel_relative_to_v1_grammar",
    "tensor_components",
    "tensor_encoding",
    "tensor_reconstruction_failures",
    "lane_stride",
    "lane_offset",
    "associator_defects",
    "commutator_defects",
    "anticommutator_failures",
    "basis_left_alternative_failures",
    "basis_right_alternative_failures",
    "basis_flexible_failures",
    "square_negatives",
    "unit_index",
    "fp_parity",
    "claim_ready",
    "formal_v13_v14",
)

INT_FIELDS = (
    "schema",
    "kind",
    "phase_code",
    "quadratic_code",
    "affine_class",
    "tensor_components",
    "tensor_reconstruction_failures",
    "lane_stride",
    "lane_offset",
    "associator_defects",
    "commutator_defects",
    "anticommutator_failures",
    "basis_left_alternative_failures",
    "basis_right_alternative_failures",
    "basis_flexible_failures",
    "square_negatives",
    "unit_index",
)

BOOL_FIELDS = ("novel_relative_to_v1_grammar", "claim_ready")


def sigma(code: int, i: int, j: int) -> int:
    """Structure coefficient of the twisted product: e_i * e_j = sigma * e_(i^j).

    Phase code 0 recovers the Cayley-Dickson sedenion product exactly.
    """
    return -1 if (TAU[i][j] ^ bilinear(code, i, j)) else 1


def structure_invariants(code: int) -> dict[str, int]:
    """Exhaustive structural characterisation of the operator named by `code`.

    Every count below is a full enumeration, not a sample. An operator that
    misdescribes itself dies on one of these.

    All of these are restricted to the basis. That restriction is load-bearing
    and is why three of them carry a `basis_` prefix: a Cayley-Dickson algebra
    satisfies the alternative and flexible laws on basis elements at every
    rung, including rungs where the algebra as a whole satisfies neither. A
    zero here is evidence that the twist did not break a basis identity. It is
    not a proof that the operator is alternative or flexible.

    `associator_defects`, `commutator_defects` and `square_negatives` keep the
    names the upstream operator-genesis receipts already use for the same
    quantities, so the two sides can be compared without a translation table.
    """
    associator = 0
    for i in range(DIMENSION):
        for j in range(DIMENSION):
            sij = sigma(code, i, j)
            for k in range(DIMENSION):
                left = sij * sigma(code, i ^ j, k)
                right = sigma(code, j, k) * sigma(code, i, j ^ k)
                if left != right:
                    associator += 1

    commutator = 0
    anticommutator_failures = 0
    for i in range(DIMENSION):
        for j in range(DIMENSION):
            if sigma(code, i, j) != sigma(code, j, i):
                commutator += 1
            # Off the diagonal and away from the unit, a Cayley-Dickson basis
            # anticommutes. A twist may break that; breaking it is allowed but
            # must be declared.
            if i != j and i != 0 and j != 0:
                if sigma(code, i, j) != -sigma(code, j, i):
                    anticommutator_failures += 1

    left_alt = 0
    right_alt = 0
    flexible = 0
    for i in range(DIMENSION):
        for j in range(DIMENSION):
            if sigma(code, i, i) * sigma(code, 0, j) != sigma(code, i, j) * sigma(code, i, i ^ j):
                left_alt += 1
            if sigma(code, i, j) * sigma(code, i ^ j, j) != sigma(code, j, j) * sigma(code, i, 0):
                right_alt += 1
            if sigma(code, i, j) * sigma(code, i ^ j, i) != sigma(code, j, i) * sigma(code, i, j ^ i):
                flexible += 1

    square_negatives = sum(1 for x in range(DIMENSION) if sigma(code, x, x) == -1)

    unit = -1
    for u in range(DIMENSION):
        if all(sigma(code, u, j) == 1 and sigma(code, j, u) == 1 for j in range(DIMENSION)):
            # A unit must also be neutral on the grading, which forces u == 0.
            if u == 0:
                unit = u
            break

    return {
        "associator_defects": associator,
        "commutator_defects": commutator,
        "anticommutator_failures": anticommutator_failures,
        "basis_left_alternative_failures": left_alt,
        "basis_right_alternative_failures": right_alt,
        "basis_flexible_failures": flexible,
        "square_negatives": square_negatives,
        "unit_index": unit,
    }


def tensor_reconstruction_failures(code: int, stride: int, offset: int) -> int:
    """Rebuild every coefficient through the lane map and compare to sigma.

    This is the kind=1 TENSOR check with cd_sigma replaced by the twisted
    product. It is the reason the phase code, and not a tensor or a hash, is
    the only thing accepted from the proposer.
    """
    failures = 0
    for a in range(DIMENSION):
        for b in range(DIMENSION):
            for k in range(DIMENSION):
                reconstructed = 0
                for lane in range(DIMENSION):
                    out = (lane * stride + offset) % DIMENSION
                    if out == k and (out ^ b) == a:
                        reconstructed += sigma(code, a, b)
                expected = sigma(code, a, b) if (a ^ b) == k else 0
                if reconstructed != expected:
                    failures += 1
    return failures


def _scan_forbidden(node, path: str, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = key.lower()
            for bad in FORBIDDEN_FIELD_SUBSTRINGS:
                if bad in lowered:
                    out.append(f"{path}{key}")
                    break
            _scan_forbidden(value, f"{path}{key}.", out)
    elif isinstance(node, list):
        for n, value in enumerate(node):
            _scan_forbidden(value, f"{path}{n}.", out)


def evaluate(receipt) -> tuple[bool, list[str]]:
    """Decide admissibility. The order of checks is part of the contract:
    a receipt that both claims a gain and misstates its algebra is rejected
    for the gain, because the claim boundary is the outer obligation."""
    reasons: list[str] = []

    if not isinstance(receipt, dict):
        return False, ["NOT_AN_OBJECT"]

    forbidden: list[str] = []
    _scan_forbidden(receipt, "", forbidden)
    if forbidden:
        return False, [f"FORBIDDEN_FIELD:{name}" for name in sorted(forbidden)]

    missing = [f for f in REQUIRED_FIELDS if f not in receipt]
    if missing:
        return False, [f"MISSING_FIELD:{f}" for f in missing]

    values: dict[str, int] = {}
    for field in INT_FIELDS:
        raw = receipt[field]
        if isinstance(raw, bool) or not isinstance(raw, int):
            reasons.append(f"NOT_AN_INTEGER:{field}")
        else:
            values[field] = raw
    for field in BOOL_FIELDS:
        if not isinstance(receipt[field], bool):
            reasons.append(f"NOT_A_BOOLEAN:{field}")
    if reasons:
        return False, reasons

    if receipt["schema"] != 1:
        reasons.append("SCHEMA")
    if receipt["authority"] != "Sounio":
        reasons.append("AUTHORITY_NOT_SOUNIO")
    if receipt["decision"] not in ("ADMIT", "REFUSE"):
        reasons.append("DECISION")
    if receipt["kind"] != 2:
        reasons.append("KIND_NOT_OPERATOR_GENESIS")
    if reasons:
        return False, reasons

    code = values["phase_code"]
    if not 0 <= code < (1 << 16):
        return False, ["PHASE_CODE_RANGE"]

    stride = values["lane_stride"]
    offset = values["lane_offset"]
    if stride < 1 or stride > 15 or stride % 2 != 1:
        reasons.append("LANE_STRIDE")
    if not 0 <= offset <= 15:
        reasons.append("LANE_OFFSET")
    if reasons:
        return False, reasons

    # -- 1. WELL-DEFINED -------------------------------------------------
    if receipt["tensor_components"] != DIMENSION * DIMENSION * DIMENSION:
        reasons.append("TENSOR_COMPONENTS")
    if receipt["tensor_encoding"] != "cd16-abk-offset1-v1":
        reasons.append("TENSOR_ENCODING")
    actual_failures = tensor_reconstruction_failures(code, stride, offset)
    if receipt["tensor_reconstruction_failures"] != actual_failures:
        reasons.append(
            "TENSOR_FAILURE_COUNT_MISDECLARED:"
            f"declared={receipt['tensor_reconstruction_failures']} actual={actual_failures}"
        )
    if actual_failures != 0 and receipt["decision"] == "ADMIT":
        reasons.append("ADMITTED_WITH_TENSOR_FAILURES")

    # -- 2. NOVEL --------------------------------------------------------
    atlas = build_atlas()
    placement = classify(code, atlas)
    if receipt["quadratic_code"] != placement["quadratic_code"]:
        reasons.append(
            "QUADRATIC_CODE_MISDECLARED:"
            f"declared={receipt['quadratic_code']} actual={placement['quadratic_code']}"
        )
    if receipt["affine_class"] != placement["affine_class"]:
        reasons.append(
            "AFFINE_CLASS_MISDECLARED:"
            f"declared={receipt['affine_class']} actual={placement['affine_class']}"
        )
    actual_novel = placement["novel_relative_to_v1_grammar"]
    if receipt["novel_relative_to_v1_grammar"] != actual_novel:
        reasons.append("NOVELTY_MISDECLARED")
    if receipt["decision"] == "ADMIT" and not actual_novel:
        reasons.append("ADMITTED_WITHOUT_NOVELTY")

    # -- 3. CHARACTERISED ------------------------------------------------
    invariants = structure_invariants(code)
    for name, actual in invariants.items():
        if receipt[name] != actual:
            reasons.append(f"INVARIANT_MISDECLARED:{name} declared={receipt[name]} actual={actual}")

    # -- 4. BOUNDED ------------------------------------------------------
    if receipt["fp_parity"] != "UNMEASURED":
        reasons.append("FP_PARITY_NOT_UNMEASURED")
    if receipt["claim_ready"] is not False:
        reasons.append("CLAIM_READY_MUST_BE_FALSE")
    if receipt["formal_v13_v14"] != "OPEN":
        reasons.append("FORMAL_OBLIGATIONS_NOT_OPEN")

    return (not reasons), reasons


def canonical_receipt(code: int, stride: int = 1, offset: int = 0) -> dict:
    """The receipt a correct engine would emit for `code`. Fixture generator."""
    atlas = build_atlas()
    placement = classify(code, atlas)
    receipt = {
        "schema": 1,
        "authority": "Sounio",
        "decision": "ADMIT" if placement["novel_relative_to_v1_grammar"] else "REFUSE",
        "kind": 2,
        "phase_code": code,
        "quadratic_code": placement["quadratic_code"],
        "affine_class": placement["affine_class"],
        "novel_relative_to_v1_grammar": placement["novel_relative_to_v1_grammar"],
        "tensor_components": DIMENSION**3,
        "tensor_encoding": "cd16-abk-offset1-v1",
        "tensor_reconstruction_failures": tensor_reconstruction_failures(code, stride, offset),
        "lane_stride": stride,
        "lane_offset": offset,
        "fp_parity": "UNMEASURED",
        "claim_ready": False,
        "formal_v13_v14": "OPEN",
    }
    receipt.update(structure_invariants(code))
    return receipt


# ---------------------------------------------------------------------------
# Contract harness
# ---------------------------------------------------------------------------


def load_and_run(
    schema_path: pathlib.Path,
    contract_path: pathlib.Path,
    vectors_path: pathlib.Path,
    receipts_path: "pathlib.Path | None",
) -> list:
    import hashlib

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
    if boundary.get("establishes_material_parity") is not False:
        raise ValueError("claim_boundary must refuse to establish material parity")

    declared = contract["declared"]
    if tuple(declared["forbidden_field_substrings"]) != FORBIDDEN_FIELD_SUBSTRINGS:
        raise ValueError("declared forbidden substrings drift")
    if tuple(declared["required_fields"]) != REQUIRED_FIELDS:
        raise ValueError("declared required fields drift")

    # The contract names the operator the upstream genesis run selected. Every
    # one of these is recomputed here from the phase code alone; none is read
    # from an upstream receipt. A drift means one of the two sides is wrong.
    ref = contract["reference_operator"]
    code = ref["phase_code"]
    atlas = build_atlas()
    placement = classify(code, atlas)
    invariants = structure_invariants(code)
    expected = {
        "quadratic_code": placement["quadratic_code"],
        "affine_class": placement["affine_class"],
        **invariants,
    }
    for field, want in expected.items():
        if ref[field] != want:
            raise ValueError(
                f"reference_operator.{field} declared {ref[field]!r}, recomputed {want!r}"
            )
    if not placement["novel_relative_to_v1_grammar"]:
        raise ValueError("reference_operator must be novel relative to the v1 grammar")

    ident = {
        "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "vectors_sha256": hashlib.sha256(vectors_path.read_bytes()).hexdigest(),
    }

    ids = [c["case_id"] for c in vectors["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id")

    receipts = []
    seen = set()
    for case in vectors["cases"]:
        accepted, reasons = evaluate(case["receipt"])
        if accepted != case["expect_accepted"]:
            raise ValueError(
                f"{case['case_id']}: expected accepted={case['expect_accepted']}, "
                f"got {accepted} reasons={reasons}"
            )
        want_reason = case.get("expect_reason_prefix")
        if want_reason is not None:
            if not any(r.startswith(want_reason) for r in reasons):
                raise ValueError(
                    f"{case['case_id']}: expected a reason starting {want_reason!r}, got {reasons}"
                )
        seen.add(accepted)
        receipts.append(
            {
                "case_id": case["case_id"],
                "accepted": accepted,
                "reasons": sorted(reasons),
                **ident,
            }
        )
    if seen != {True, False}:
        raise ValueError("vectors must exercise both an accepted and a rejected receipt")
    if receipts_path is not None:
        receipts_path.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in receipts)
        )
    return receipts


def mutation_selftest(
    schema_path: pathlib.Path, contract_path: pathlib.Path, vectors_path: pathlib.Path
) -> int:
    """Every mutation below must be caught. A contract whose own corruption
    still passes is decoration, not a gate."""
    import copy
    import tempfile

    contract = json.loads(contract_path.read_text())
    vectors = json.loads(vectors_path.read_text())

    contract_mutations = [
        lambda c: c["reference_operator"].update({"phase_code": 0}),
        lambda c: c["reference_operator"].update({"quadratic_code": 199}),
        lambda c: c["reference_operator"].update({"affine_class": 25}),
        lambda c: c["reference_operator"].update({"commutator_defects": 210}),
        lambda c: c["reference_operator"].update({"associator_defects": 1847}),
        lambda c: c["reference_operator"].update({"square_negatives": 15}),
        lambda c: c["reference_operator"].update({"anticommutator_failures": 0}),
        lambda c: c["claim_boundary"].update({"establishes_utility": True}),
        lambda c: c["claim_boundary"].update({"establishes_material_parity": True}),
        lambda c: c["declared"].update({"forbidden_field_substrings": ["gain"]}),
        lambda c: c["declared"]["required_fields"].remove("claim_ready"),
    ]
    vector_mutations = [
        lambda v: v["cases"][0].update({"expect_accepted": False}),
        lambda v: v["cases"][0]["receipt"].update({"commutator_defects": 91}),
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


def main() -> int:
    parser = argparse.ArgumentParser(description=CONTRACT_ID)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--contract", type=pathlib.Path)
    parser.add_argument("--vectors", type=pathlib.Path)
    parser.add_argument("--receipts", type=pathlib.Path)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--emit", type=int, metavar="PHASE_CODE",
                        help="emit the canonical receipt for a phase code")
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()

    if args.emit is not None:
        print(json.dumps(canonical_receipt(args.emit, args.stride, args.offset), indent=2))
        return 0

    if not (args.schema and args.contract and args.vectors):
        parser.error("--schema, --contract and --vectors are required")

    if args.selftest:
        caught = mutation_selftest(args.schema, args.contract, args.vectors)
        load_and_run(args.schema, args.contract, args.vectors, args.receipts)
        print(f"MUTATION_SELFTEST_PASS caught={caught}")
        return 0

    load_and_run(args.schema, args.contract, args.vectors, args.receipts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
