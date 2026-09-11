#!/usr/bin/env python3
"""Reference model and classifier for the PIREUS bilinear-phase operator atlas.

Independently reconstructs the atlas from arithmetic over F2^4 -- it reads no
upstream receipt and trusts no upstream count -- then classifies an operator
construction. Classification is what an operator admission path needs and does
not have: locating a proposed construction in the atlas rather than refusing
every divergence from the canonical tensor.

Establishing a class says nothing about performance, materialisability, or
scientific novelty. Those are separate obligations.
"""

import argparse
import hashlib
import json
import pathlib
from typing import Any

CONTRACT_ID = "eisa_h.pireus_operator_atlas.v1"
DIMENSION = 16


def cd_sigma(a: int, b: int, bits: int = 4) -> int:
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


TAU = [[0 if cd_sigma(i, j) == 1 else 1 for j in range(DIMENSION)] for i in range(DIMENSION)]


def idx(i: int, j: int) -> int:
    return i * DIMENSION + j


def bit(code: int, i: int, j: int) -> int:
    return (code >> (i * 4 + j)) & 1


def bilinear(code: int, x: int, y: int) -> int:
    s = 0
    for i in range(4):
        if (x >> i) & 1:
            for j in range(4):
                if (y >> j) & 1:
                    s ^= bit(code, i, j)
    return s


def quadratic_code(code: int) -> int:
    """The complete gauge-class invariant: 4 diagonal bits and 6 symmetrised pairs."""
    q = 0
    pos = 0
    for i in range(4):
        q |= bit(code, i, i) << pos
        pos += 1
    for i in range(4):
        for j in range(i + 1, 4):
            q |= (bit(code, i, j) ^ bit(code, j, i)) << pos
            pos += 1
    return q


def diagonal(code: int) -> tuple[int, ...]:
    return tuple(bilinear(code, x, x) for x in range(DIMENSION))


def is_alternating(code: int) -> bool:
    for i in range(4):
        if bit(code, i, i):
            return False
        for j in range(i + 1, 4):
            if bit(code, i, j) != bit(code, j, i):
                return False
    return True


def apply_matrix(m: int, v: int) -> int:
    out = 0
    for i in range(4):
        row = (m >> (i * 4)) & 0xF
        out |= (bin(row & v).count("1") & 1) << i
    return out


def invertible(m: int) -> bool:
    return len({apply_matrix(m, v) for v in range(DIMENSION)}) == DIMENSION


def _vec(fn) -> int:
    v = 0
    for i in range(DIMENSION):
        for j in range(DIMENSION):
            if fn(i, j):
                v |= 1 << idx(i, j)
    return v


def span_basis() -> list[int]:
    gens = []
    for p in range(4):
        for q in range(4):
            gens.append(_vec(lambda i, j, p=p, q=q: ((i >> p) & 1) & ((j >> q) & 1)))
    for z in range(1, DIMENSION):
        gens.append(
            _vec(lambda i, j, z=z: (i == z) ^ (j == z) ^ ((i ^ j) == z))
        )
    basis: list[int] = []
    for v in gens:
        for b in basis:
            v = min(v, v ^ b)
        if v:
            basis.append(v)
            basis.sort(reverse=True)
    return basis


BASIS = span_basis()


def in_span(v: int) -> bool:
    for b in BASIS:
        v = min(v, v ^ b)
    return v == 0


def admitted_actions() -> tuple[list[tuple[tuple[int, ...], tuple[int, ...]]], int, int]:
    plain = 0
    exchange = 0
    maps = []
    for m in range(1 << 16):
        if not invertible(m):
            continue
        img = tuple(apply_matrix(m, x) for x in range(DIMENSION))
        d = 0
        e = 0
        for i in range(DIMENSION):
            gi = img[i]
            for j in range(DIMENSION):
                gj = img[j]
                if TAU[gi][gj] ^ TAU[i][j]:
                    d |= 1 << idx(i, j)
                if TAU[gj][gi] ^ TAU[i][j]:
                    e |= 1 << idx(i, j)
        for vec, is_exchange in ((d, False), (e, True)):
            if in_span(vec):
                if is_exchange:
                    exchange += 1
                else:
                    plain += 1
                maps.append((img, tuple((vec >> idx(x, x)) & 1 for x in range(DIMENSION))))
    return maps, plain, exchange


_ATLAS_CACHE: dict[str, Any] | None = None


def build_atlas() -> dict[str, Any]:
    """Reconstruct the atlas. Memoised: the reconstruction depends only on the
    algebra, never on the contract, so a mutated contract must not rebuild it."""
    global _ATLAS_CACHE
    if _ATLAS_CACHE is not None:
        return _ATLAS_CACHE
    _ATLAS_CACHE = _build_atlas_uncached()
    return _ATLAS_CACHE


def _build_atlas_uncached() -> dict[str, Any]:
    reps: dict[tuple[int, ...], int] = {}
    for code in range(1 << 16):
        key = diagonal(code)
        if key not in reps or code < reps[key]:
            reps[key] = code
    keys = sorted(reps)
    index = {k: n for n, k in enumerate(keys)}
    parent = list(range(len(keys)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    maps, plain, exchange = admitted_actions()
    for img, corr in maps:
        for key in keys:
            moved = tuple(key[img[x]] ^ corr[x] for x in range(DIMENSION))
            ra, rb = find(index[key]), find(index[moved])
            if ra != rb:
                parent[ra] = rb
    roots = sorted({find(i) for i in range(len(keys))},
                   key=lambda r: min(quadratic_code(reps[keys[i]])
                                     for i in range(len(keys)) if find(i) == r))
    number = {r: n for n, r in enumerate(roots)}
    affine_of = {k: number[find(index[k])] for k in keys}
    diagonal_codes = [sum(((k >> t) & 1) << (t * 4 + t) for t in range(4)) for k in range(16)]
    v1_classes = sorted({affine_of[diagonal(c)] for c in diagonal_codes})
    return {
        "class_reps": reps,
        "affine_of": affine_of,
        "gauge_classes": len(keys),
        "affine_classes": len(roots),
        "admitted_plain": plain,
        "admitted_exchange": exchange,
        "v1_classes": v1_classes,
    }


def classify(code: int, atlas: dict[str, Any]) -> dict[str, Any]:
    if not 0 <= code < (1 << 16):
        raise ValueError("operator construction code out of range")
    key = diagonal(code)
    affine = atlas["affine_of"][key]
    return {
        "construction_code": code,
        "quadratic_code": quadratic_code(code),
        "affine_class": affine,
        "novel_relative_to_v1_grammar": affine not in atlas["v1_classes"],
    }


def verify(contract: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    atlas = build_atlas()
    d = contract["declared"]
    failures = []

    def expect(label: str, got: Any, want: Any) -> None:
        if got != want:
            failures.append(f"{label}: got {got!r}, declared {want!r}")

    buckets: dict[int, int] = {}
    for code in range(1 << 16):
        buckets[quadratic_code(code)] = buckets.get(quadratic_code(code), 0) + 1
    expect("gauge_classes", len(buckets), d["gauge_classes"])
    expect("gauge_class_size", sorted(set(buckets.values())), [d["gauge_class_size"]])
    expect("bilinear_matrices", sum(buckets.values()), d["bilinear_matrices"])
    expect(
        "alternating_subspace_dimension",
        len([c for c in range(1 << 16) if is_alternating(c)]).bit_length() - 1,
        d["alternating_subspace_dimension"],
    )
    expect("span_dimension", len(BASIS), d["span_dimension"])
    expect("general_linear_group_order", sum(1 for m in range(1 << 16) if invertible(m)),
           d["general_linear_group_order"])
    expect("admitted_without_operand_exchange", atlas["admitted_plain"],
           d["admitted_without_operand_exchange"])
    expect("admitted_with_operand_exchange", atlas["admitted_exchange"],
           d["admitted_with_operand_exchange"])
    expect("affine_classes", atlas["affine_classes"], d["affine_classes"])
    expect("v1_grammar_classes", atlas["v1_classes"], d["v1_grammar_classes"])
    return atlas, failures


def atlas_digest(atlas: dict[str, Any]) -> str:
    rows = sorted(
        (quadratic_code(code), atlas["affine_of"][key])
        for key, code in atlas["class_reps"].items()
    )
    payload = "".join(f"{q:04d}:{a:02d}\n" for q, a in rows).encode()
    return hashlib.sha256(payload).hexdigest()


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
    for key in schema.get("required", []):
        if key not in contract:
            raise ValueError(f"contract missing {key!r}")
    if contract["claim_boundary"].get("establishes_novelty") is not False:
        raise ValueError("claim_boundary must refuse to establish scientific novelty")
    if vectors.get("contract_id") != CONTRACT_ID:
        raise ValueError("vectors contract_id mismatch")

    atlas, failures = verify(contract)
    if failures:
        raise ValueError("atlas verification failed: " + "; ".join(failures))
    digest = atlas_digest(atlas)
    if digest != contract["declared"]["atlas_sha256"]:
        raise ValueError(f"atlas digest drift: {digest}")

    ident = {
        "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "vectors_sha256": hashlib.sha256(vectors_path.read_bytes()).hexdigest(),
        "atlas_sha256": digest,
    }
    receipts = []
    ids = [c["case_id"] for c in vectors["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id")
    seen_novel = set()
    for case in vectors["cases"]:
        result = classify(case["construction_code"], atlas)
        for field, want in case["expect"].items():
            if result[field] != want:
                raise ValueError(
                    f"{case['case_id']}: {field} expected {want!r}, got {result[field]!r}"
                )
        seen_novel.add(result["novel_relative_to_v1_grammar"])
        receipts.append({"case_id": case["case_id"], **result, **ident})
    if seen_novel != {True, False}:
        raise ValueError("vectors must exercise both novel and non-novel classifications")
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
    contract_mutations = [
        lambda c: c["declared"].update({"affine_classes": 31}),
        lambda c: c["declared"].update({"gauge_classes": 1023}),
        lambda c: c["declared"].update({"admitted_with_operand_exchange": 167}),
        lambda c: c["declared"].update({"v1_grammar_classes": [0, 3, 14]}),
        lambda c: c["declared"].update({"atlas_sha256": "0" * 64}),
        lambda c: c["declared"].update({"span_dimension": 20}),
        lambda c: c["claim_boundary"].update({"establishes_novelty": True}),
    ]
    vector_mutations = [
        lambda v: v["cases"][0]["expect"].update({"affine_class": 99}),
        lambda v: v["cases"][0]["expect"].update({"novel_relative_to_v1_grammar": True}),
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=pathlib.Path, required=True)
    parser.add_argument("--contract", type=pathlib.Path, required=True)
    parser.add_argument("--vectors", type=pathlib.Path, required=True)
    parser.add_argument("--receipts", type=pathlib.Path)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--print-atlas-digest", action="store_true")
    args = parser.parse_args()
    if args.print_atlas_digest:
        print(atlas_digest(build_atlas()))
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
