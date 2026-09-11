#!/usr/bin/env python3
"""Cross-engine agreement between the Sounio admission engine and this oracle.

The PIREUS cycle's semantic authority is a Sounio program: tools/pireus/
continuity/admission.sio, compiled to a native executable. It reconstructs the
structure tensor of the operator a proposal names and hashes it. This oracle
reconstructs the same tensor from the phase code alone, in Python, from the
Cayley-Dickson recursion and the declared encoding -- it reads no Sounio source
and accepts no digest from the receipt it is checking.

Two independent implementations agreeing on a 4096-coefficient object is
evidence that the receipt names the operator it admitted. It is not evidence
that either implementation is correct, and it is not a measurement of anything
on hardware.

The receipts here are recorded verbatim from one execution of the engine. This
gate does not run Sounio; it re-derives every digest those receipts assert.
"""

import argparse
import hashlib
import json
import pathlib
from typing import Any

CONTRACT_ID = "eisa_h.pireus_admission_cross_engine.v1"
ATLAS_CONTRACT_ID = "eisa_h.pireus_operator_atlas.v1"
DIMENSION = 16
TENSOR_COMPONENTS = 4096
TENSOR_ENCODING = "cd16-abk-offset1-v1"


def cd_sigma(a: int, b: int, bits: int = 4) -> int:
    """Cayley-Dickson structure sign. e_a * e_b = cd_sigma(a,b) * e_{a^b}."""
    if a == 0 or b == 0:
        return 1
    if bits <= 1:
        return -1
    half = 1 << (bits - 1)
    a_hi, b_hi = a >= half, b >= half
    a_lo, b_lo = a % half, b % half
    if not a_hi and not b_hi:
        return cd_sigma(a_lo, b_lo, bits - 1)
    if not a_hi and b_hi:
        return cd_sigma(b_lo, a_lo, bits - 1)
    if a_hi and not b_hi:
        return cd_sigma(a_lo, 0, bits - 1) if b_lo == 0 else -cd_sigma(a_lo, b_lo, bits - 1)
    return -cd_sigma(0, a_lo, bits - 1) if b_lo == 0 else cd_sigma(b_lo, a_lo, bits - 1)


def bilinear(code: int, x: int, y: int) -> int:
    """B(x,y) = sum_ij x_i y_j B_ij over F2, with B_ij at bit i*4+j of the code."""
    s = 0
    for i in range(4):
        if (x >> i) & 1:
            for j in range(4):
                if (y >> j) & 1:
                    s ^= (code >> (i * 4 + j)) & 1
    return s


def sigma_phase(code: int, a: int, b: int) -> int:
    return -cd_sigma(a, b) if bilinear(code, a, b) else cd_sigma(a, b)


def tensor_digest(code: int) -> str:
    """SHA-256 of the structure tensor under cd16-abk-offset1-v1.

    Labelled basis order (a,b,k) ascending, one byte per coefficient, offset by
    one so -1,0,+1 map to 0,1,2. Sixteen 256-byte blocks, one per a, hashed in
    order -- the engine updates its SHA-256 state once per a, and a single
    4096-byte update would give the same digest only by accident of the padding
    rules, so the block structure is reproduced rather than assumed away.
    """
    h = hashlib.sha256()
    for a in range(DIMENSION):
        block = bytearray(256)
        for b in range(DIMENSION):
            s = sigma_phase(code, a, b)
            for k in range(DIMENSION):
                block[b * DIMENSION + k] = (s + 1) if (a ^ b) == k else 1
        h.update(bytes(block))
    return h.hexdigest()


def recovered_code(code: int) -> int:
    """Read the 16 bits of B back out of the sign table at basis pairs.

    sign(e_i, e_j) differs from cd_sigma(e_i, e_j) exactly when B_ij is set, so
    the map from phase code to sign table is injective and a tensor digest
    identifies one construction. Checked over the whole code space, not argued.
    """
    out = 0
    for i in range(4):
        for j in range(4):
            a, b = 1 << i, 1 << j
            if sigma_phase(code, a, b) != cd_sigma(a, b):
                out |= 1 << (i * 4 + j)
    return out


def _consistent_phase_swap(case: dict[str, Any], old: int, new: int) -> None:
    """Rewrite a recorded case to claim a different phase, keeping it self-consistent."""
    wire = case["proposal_wire"].replace(f'"phase":{old}', f'"phase":{new}', 1)
    assert wire != case["proposal_wire"]
    case["proposal_wire"] = wire
    digest = hashlib.sha256(wire.encode()).hexdigest()
    case["proposal_sha256"] = digest
    receipt = json.loads(case["engine_stdout"])
    receipt["phase_code"] = new
    receipt["proposal_sha256"] = digest
    case["engine_stdout"] = json.dumps(receipt, separators=(",", ":")) + "\n"


def parse_receipt(case: dict[str, Any]) -> dict[str, Any]:
    text = case["engine_stdout"]
    try:
        receipt = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{case['case_id']}: engine stdout is not JSON: {exc}") from exc
    if not isinstance(receipt, dict):
        raise ValueError(f"{case['case_id']}: receipt is not an object")
    return receipt


def check_case(case: dict[str, Any], context_sha256: str) -> dict[str, Any]:
    case_id = case["case_id"]
    wire = case["proposal_wire"].encode()
    try:
        proposal = json.loads(wire)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{case_id}: proposal wire is not JSON: {exc}") from exc
    receipt = parse_receipt(case)

    if case["engine_exit_code"] != 0:
        raise ValueError(f"{case_id}: recorded a non-zero exit for an admitted proposal")
    for field, want in (("schema", 1), ("authority", "Sounio"), ("decision", "ADMIT"),
                        ("tensor_encoding", TENSOR_ENCODING),
                        ("tensor_components", TENSOR_COMPONENTS)):
        if receipt.get(field) != want:
            raise ValueError(f"{case_id}: {field} is {receipt.get(field)!r}, want {want!r}")
    if receipt.get("claim_ready") is not False:
        raise ValueError(f"{case_id}: a receipt may not declare itself claim-ready")

    # The proposal is data. The recorded wire bytes -- not a re-serialisation of
    # them, whose key order is a property of the recorder -- must hash to what
    # the receipt attests, or the receipt speaks about a different document.
    if hashlib.sha256(wire).hexdigest() != case["proposal_sha256"]:
        raise ValueError(f"{case_id}: recorded proposal does not hash to its recorded digest")
    if receipt.get("proposal_sha256") != case["proposal_sha256"]:
        raise ValueError(f"{case_id}: receipt attests to a different proposal")
    # Admission is against one frozen context. A receipt recorded under another
    # snapshot is not comparable with the rest of this set.
    if receipt.get("context_sha256") != context_sha256:
        raise ValueError(f"{case_id}: receipt was issued against a different context")
    if proposal.get("context") != context_sha256:
        raise ValueError(f"{case_id}: proposal names a context other than the recorded one")

    kind = proposal["kind"]
    if kind == 1:
        if receipt.get("kind") != "lowering":
            raise ValueError(f"{case_id}: kind=1 must be admitted as a lowering")
        if "phase" in proposal:
            raise ValueError(f"{case_id}: kind=1 carries no phase")
        code = 0
    elif kind == 2:
        if receipt.get("kind") != "operator":
            raise ValueError(f"{case_id}: kind=2 must be admitted as an operator")
        code = proposal["phase"]
        if receipt.get("phase_code") != code:
            raise ValueError(f"{case_id}: receipt phase_code does not echo the proposal")
        # Well-definedness is the engine's whole obligation. A receipt that
        # arrives already carrying a novelty verdict has taken a decision that
        # belongs to the atlas, and this gate must not launder it.
        if receipt.get("novelty") != "NOT_CLASSIFIED":
            raise ValueError(f"{case_id}: operator receipt must leave novelty undischarged")
        if receipt.get("classifier") != ATLAS_CONTRACT_ID:
            raise ValueError(f"{case_id}: operator receipt must name {ATLAS_CONTRACT_ID}")
    else:
        raise ValueError(f"{case_id}: unknown kind {kind!r}")

    if not 0 <= code <= 65535:
        raise ValueError(f"{case_id}: phase code out of range")
    if recovered_code(code) != code:
        raise ValueError(f"{case_id}: phase code is not recoverable from its sign table")

    derived = tensor_digest(code)
    if derived != receipt.get("tensor_sha256"):
        raise ValueError(
            f"{case_id}: cross-engine divergence -- oracle {derived}, engine "
            f"{receipt.get('tensor_sha256')}"
        )
    return {
        "case_id": case_id,
        "kind": receipt["kind"],
        "phase_code": code,
        "tensor_sha256": derived,
        "agreement": "CROSS_ENGINE_MATCH",
    }


def verify(contract: dict[str, Any], vectors: dict[str, Any]) -> list[dict[str, Any]]:
    d = contract["declared"]
    cases = vectors["cases"]
    ids = [c["case_id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id")
    if len(cases) != d["recorded_receipts"]:
        raise ValueError(f"declared {d['recorded_receipts']} receipts, vectors carry {len(cases)}")

    provenance = vectors["provenance"]
    context_sha256 = hashlib.sha256(provenance["context_wire"].encode()).hexdigest()
    if context_sha256 != provenance["context_sha256"]:
        raise ValueError("recorded context does not hash to its recorded digest")
    results = [check_case(c, context_sha256) for c in cases]

    lowerings = [r for r in results if r["kind"] == "lowering"]
    operators = [r for r in results if r["kind"] == "operator"]
    if len(operators) != d["operator_receipts"]:
        raise ValueError(f"declared {d['operator_receipts']} operator receipts, got {len(operators)}")
    if not lowerings:
        raise ValueError("no kind=1 receipt: the base of the comparison is missing")

    # Phase 0 is the Cayley-Dickson constant. The twist extends the admitted
    # algebra rather than replacing it, so the kind=1 tensor and the phase-0
    # operator tensor must be the same 4096 bytes.
    base = tensor_digest(0)
    if base != d["cayley_dickson_tensor_sha256"]:
        raise ValueError(f"Cayley-Dickson tensor digest drift: {base}")
    for r in lowerings:
        if r["tensor_sha256"] != base:
            raise ValueError(f"{r['case_id']}: kind=1 tensor is not the Cayley-Dickson tensor")
    zero = [r for r in operators if r["phase_code"] == 0]
    if not zero:
        raise ValueError("no phase-0 operator receipt: the identity case is untested")
    for r in zero:
        if r["tensor_sha256"] != base:
            raise ValueError(f"{r['case_id']}: phase 0 did not recover Cayley-Dickson")

    # Distinct constructions, distinct digests. A collision would mean a receipt
    # does not identify the operator it admitted.
    by_digest: dict[str, int] = {}
    for r in operators:
        prior = by_digest.get(r["tensor_sha256"])
        if prior is not None and prior != r["phase_code"]:
            raise ValueError(f"phase {prior} and {r['phase_code']} share a tensor digest")
        by_digest[r["tensor_sha256"]] = r["phase_code"]
    if len(by_digest) != d["distinct_operator_tensors"]:
        raise ValueError(
            f"declared {d['distinct_operator_tensors']} distinct operator tensors, got {len(by_digest)}"
        )
    return results


def exhaustive_injectivity() -> int:
    """Every one of the 65536 phase codes is recoverable from its sign table."""
    for code in range(1 << 16):
        if recovered_code(code) != code:
            raise ValueError(f"phase code {code} is not recoverable")
    return 1 << 16


def load_and_run(
    schema_path: pathlib.Path,
    contract_path: pathlib.Path,
    vectors_path: pathlib.Path,
    receipts_path: pathlib.Path | None,
) -> list[dict[str, Any]]:
    schema = json.loads(schema_path.read_text())
    contract = json.loads(contract_path.read_text())
    vectors = json.loads(vectors_path.read_text())
    if contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("contract_id mismatch")
    if vectors.get("contract_id") != CONTRACT_ID:
        raise ValueError("vectors contract_id mismatch")
    for key in schema.get("required", []):
        if key not in contract:
            raise ValueError(f"contract missing {key!r}")
    cb = contract["claim_boundary"]
    if cb.get("establishes_engine_correctness") is not False:
        raise ValueError("claim_boundary must refuse to establish engine correctness")
    if cb.get("establishes_performance") is not False:
        raise ValueError("claim_boundary must refuse to establish performance")
    if contract["provenance"].get("executed_against_admission_sio") is not True:
        raise ValueError("provenance must state that the receipts came from the engine")
    if vectors["provenance"].get("engine_source_sha256") != \
            contract["provenance"].get("engine_source_sha256"):
        raise ValueError("contract and vectors disagree about which engine was run")

    results = verify(contract, vectors)
    ident = {
        "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "vectors_sha256": hashlib.sha256(vectors_path.read_bytes()).hexdigest(),
    }
    receipts = [{**r, **ident} for r in results]
    if receipts_path is not None:
        receipts_path.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in receipts)
        )
    return receipts


def mutation_selftest(
    schema_path: pathlib.Path, contract_path: pathlib.Path, vectors_path: pathlib.Path
) -> int:
    import copy
    import tempfile

    contract = json.loads(contract_path.read_text())
    vectors = json.loads(vectors_path.read_text())

    def operator_case(v: dict[str, Any], phase: int) -> dict[str, Any]:
        for c in v["cases"]:
            p = json.loads(c["proposal_wire"])
            if p["kind"] == 2 and p.get("phase") == phase:
                return c
        raise AssertionError(f"no operator case with phase {phase}")

    def retext(case: dict[str, Any], old: str, new: str, field: str = "engine_stdout") -> None:
        assert old in case[field], old
        case[field] = case[field].replace(old, new, 1)

    contract_mutations = [
        lambda c: c["declared"].update({"recorded_receipts": 9}),
        lambda c: c["declared"].update({"operator_receipts": 8}),
        lambda c: c["declared"].update({"distinct_operator_tensors": 8}),
        lambda c: c["declared"].update({"cayley_dickson_tensor_sha256": "0" * 64}),
        lambda c: c["claim_boundary"].update({"establishes_engine_correctness": True}),
        lambda c: c["provenance"].update({"executed_against_admission_sio": False}),
        lambda c: c["provenance"].update({"engine_source_sha256": "0" * 64}),
    ]
    vector_mutations = [
        # A digest nobody re-derives is a number that agrees with itself.
        lambda v: retext(operator_case(v, 1128),
                         "60cffb22", "60cffb23"),
        # An operator that arrives pre-classified.
        lambda v: retext(operator_case(v, 198),
                         '"novelty":"NOT_CLASSIFIED"', '"novelty":"NOVEL"'),
        # The phase the receipt echoes no longer names the tensor it carries.
        lambda v: retext(operator_case(v, 74), '"phase":74', '"phase":75', "proposal_wire"),
        # Repoint a receipt at a different operator *consistently*: the wire,
        # its digest and the echoed phase_code all say 75. Every binding check
        # passes and only the re-derived tensor disagrees, which is the one
        # obligation this contract exists for.
        lambda v: _consistent_phase_swap(operator_case(v, 198), 198, 75),
        # A receipt attesting to a document other than the one recorded.
        lambda v: retext(operator_case(v, 8), '"kind":"operator"', '"kind":"lowering"'),
        lambda v: v["cases"].append(copy.deepcopy(v["cases"][0])),
        lambda v: v["provenance"].update({"engine_source_sha256": "0" * 64}),
        lambda v: v["provenance"].update({"context_wire": v["provenance"]["context_wire"].replace("55", "63", 1)}),
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    parser.add_argument("--contract", type=pathlib.Path, required=True)
    parser.add_argument("--vectors", type=pathlib.Path, required=True)
    parser.add_argument("--receipts", type=pathlib.Path)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--exhaustive", action="store_true")
    args = parser.parse_args()
    if args.exhaustive:
        print(f"PHASE_CODE_INJECTIVITY_VERIFIED codes={exhaustive_injectivity()}")
        return 0
    if args.selftest:
        caught = mutation_selftest(args.schema, args.contract, args.vectors)
        load_and_run(args.schema, args.contract, args.vectors, args.receipts)
        print(f"MUTATION_SELFTEST_PASS caught={caught}")
        return 0
    load_and_run(args.schema, args.contract, args.vectors, args.receipts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
