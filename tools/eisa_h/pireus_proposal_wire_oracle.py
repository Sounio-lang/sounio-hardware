#!/usr/bin/env python3
"""Wire-format oracle for a PIREUS continuity proposal document.

`tools/pireus/continuity/admission.sio` parses proposals with a hand-written
bounded parser. Its accepted language is narrow and entirely implicit in the
code: nothing states it, so nothing can check a proposal before the engine
refuses it, and nothing pins the language against drift.

This oracle states it, executably. The v1 half is a transcription of the
parser's behaviour; the v2 half is the minimal extension a kind=2 operator
proposal needs, together with the exact edit set that extension implies.

WHAT THIS IS NOT. The v1 language here was derived by reading the Sounio
source, not by executing it: this environment cannot build `bin/souc` (gen2
self-compilation measured ~26 GiB maximum RSS). So the v1 rules are a claim
about admission.sio that a compiler owner must confirm, not a measurement of
it. Every rule below names the line it came from so that confirmation is a
reading task rather than an investigation. A disagreement between this file
and admission.sio is a defect in this file until proven otherwise -- the
engine is the authority, this is the description.
"""

import argparse
import hashlib
import json
import pathlib

CONTRACT_ID = "eisa_h.pireus_proposal_wire.v1"

# admission.sio:14-30, key_name(). Order is the value-array index.
V1_KEYS = (
    "schema", "target", "dimension", "precision", "order", "fma",
    "capabilities", "lane_width", "facts_state", "kind", "lane_stride",
    "lane_offset", "load", "layout", "unroll", "context",
)
# The single key a kind=2 proposal adds. Index 16 is free: the Document
# already declares `values: [i64; 18]` (admission.sio:9).
V2_ADDED_KEY = "phase"

CONTEXT_KEY_INDEX = 15          # admission.sio:78, `if key == 15`
CONTEXT_HEX_LEN = 64            # admission.sio:83, `while j < 64`
MAX_DOCUMENT_BYTES = 4096       # admission.sio:170, `cn > 4096 || pn > 4096`
MAX_VALUE_DIGITS = 9            # admission.sio:97, `if p - first >= 9`

# admission.sio:176. Fields 0..5 and 9..15; 6,7,8 are context-only and a
# proposal may not override them.
V1_PROPOSAL_SEEN_MASK = 65087
V2_PROPOSAL_SEEN_MASK = V1_PROPOSAL_SEEN_MASK | (1 << 16)

WHITESPACE = {0x20, 0x09, 0x0A, 0x0D}   # admission.sio:32


def parse(text: str, keys: tuple) -> tuple:
    """Reimplementation of admission.sio's parser over `keys`.

    Returns (values, seen, context, valid). Written to mirror the original's
    control flow rather than to be idiomatic Python, because the point is
    correspondence, not elegance.
    """
    fail = ({}, 0, None, False)
    n = len(text)
    if n <= 0 or n > MAX_DOCUMENT_BYTES:
        return fail
    if any(ord(c) > 0x7F for c in text):
        # str_len(s) != n for any multi-byte input; the engine's strings are
        # byte-indexed.
        return fail

    limit = len(keys)
    values, seen, context = {}, 0, None
    p = 0

    def skip(q):
        while q < n and ord(text[q]) in WHITESPACE:
            q += 1
        return q

    p = skip(p)
    if p >= n or text[p] != "{":
        return fail
    p += 1

    count = 0
    while count < limit:
        p = skip(p)
        if p >= n or text[p] != '"':
            return fail
        p += 1
        start = p
        while p < n and text[p] != '"':
            c = ord(text[p])
            # admission.sio:52 -- lowercase and underscore only.
            if not ((97 <= c <= 122) or c == 95):
                return fail
            p += 1
        if p >= n:
            return fail
        name = text[start:p]
        key = keys.index(name) if name in keys else -1
        if key < 0:
            return fail
        if seen & (1 << key):        # admission.sio:71 -- no duplicate keys
            return fail
        seen |= 1 << key
        p = skip(p + 1)
        if p >= n or text[p] != ":":
            return fail
        p = skip(p + 1)
        if p >= n:
            return fail

        if key == CONTEXT_KEY_INDEX:
            if text[p] != '"':
                return fail
            p += 1
            digits = []
            for _ in range(CONTEXT_HEX_LEN):
                if p >= n:
                    return fail
                c = ord(text[p])
                # admission.sio:86 -- lowercase hex only.
                if not ((48 <= c <= 57) or (97 <= c <= 102)):
                    return fail
                digits.append(text[p])
                p += 1
            if p >= n or text[p] != '"':
                return fail
            p += 1
            context = "".join(digits)
        else:
            first = p
            value = 0
            while p < n and "0" <= text[p] <= "9":
                if p - first >= MAX_VALUE_DIGITS:
                    return fail
                value = value * 10 + (ord(text[p]) - 48)
                p += 1
            if first == p:                              # no digits
                return fail
            if p - first > 1 and text[first] == "0":    # leading zero
                return fail
            values[keys[key]] = value

        count += 1
        p = skip(p)
        if p >= n:
            return fail
        if text[p] == "}":
            # Trailing content after the object is refused.
            if skip(p + 1) != n:
                return fail
            return (values, seen, context, True)
        if text[p] != ",":
            return fail
        p += 1

    # Falling out of the loop means the document did not close after the
    # last key the parser can hold. A document with one key too many fails
    # here, not on an unknown key -- which is why extending the language
    # means raising this bound, not only adding a name.
    return fail


def admissible(text: str, expect_kind: int) -> tuple:
    keys = V1_KEYS if expect_kind == 1 else V1_KEYS + (V2_ADDED_KEY,)
    mask = V1_PROPOSAL_SEEN_MASK if expect_kind == 1 else V2_PROPOSAL_SEEN_MASK
    values, seen, context, valid = parse(text, keys)
    reasons = []
    if not valid:
        return False, ["PROPOSAL_FORMAT"]
    if seen != mask:
        reasons.append(f"SEEN_MASK:{seen}!={mask}")
    if context is None:
        reasons.append("NO_CONTEXT")
    if values.get("kind") != expect_kind:
        reasons.append("KIND")
    if expect_kind == 2:
        phase = values.get("phase")
        if phase is None or not 0 <= phase < (1 << 16):
            reasons.append("PHASE_RANGE")
    return (not reasons), reasons


def load_and_run(schema_path, contract_path, vectors_path, receipts_path):
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

    d = contract["declared"]
    if tuple(d["v1_keys"]) != V1_KEYS:
        raise ValueError("v1 key order drift")
    if d["v2_added_key"] != V2_ADDED_KEY:
        raise ValueError("v2 added key drift")
    if d["v1_proposal_seen_mask"] != V1_PROPOSAL_SEEN_MASK:
        raise ValueError("v1 seen mask drift")
    if d["v2_proposal_seen_mask"] != V2_PROPOSAL_SEEN_MASK:
        raise ValueError("v2 seen mask drift")
    if d["max_document_bytes"] != MAX_DOCUMENT_BYTES:
        raise ValueError("document bound drift")
    if d["max_value_digits"] != MAX_VALUE_DIGITS:
        raise ValueError("value digit bound drift")

    # The provenance disclaimer is load-bearing: this description was read
    # from Sounio source, never executed against it.
    if contract["provenance"]["derived_by"] != "source_reading":
        raise ValueError("provenance must state that v1 was read, not executed")
    if contract["provenance"]["executed_against_admission_sio"] is not False:
        raise ValueError("provenance must not claim execution against admission.sio")

    ident = {
        "schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "vectors_sha256": hashlib.sha256(vectors_path.read_bytes()).hexdigest(),
    }
    ids = [c["case_id"] for c in vectors["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id")

    receipts, seen_outcomes, seen_kinds = [], set(), set()
    for case in vectors["cases"]:
        accepted, reasons = admissible(case["document"], case["kind"])
        if accepted != case["expect_accepted"]:
            raise ValueError(
                f"{case['case_id']}: expected accepted={case['expect_accepted']}, "
                f"got {accepted} reasons={reasons}")
        want = case.get("expect_reason_prefix")
        if want is not None and not any(r.startswith(want) for r in reasons):
            raise ValueError(f"{case['case_id']}: expected reason {want!r}, got {reasons}")
        seen_outcomes.add(accepted)
        seen_kinds.add(case["kind"])
        receipts.append({"case_id": case["case_id"], "kind": case["kind"],
                         "accepted": accepted, "reasons": sorted(reasons), **ident})
    if seen_outcomes != {True, False}:
        raise ValueError("vectors must exercise both outcomes")
    if seen_kinds != {1, 2}:
        raise ValueError("vectors must exercise both kind=1 and kind=2")
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
        lambda c: c["declared"].update({"v1_proposal_seen_mask": 65535}),
        lambda c: c["declared"].update({"v2_proposal_seen_mask": 65087}),
        lambda c: c["declared"].update({"max_document_bytes": 8192}),
        lambda c: c["declared"].update({"max_value_digits": 18}),
        lambda c: c["declared"].update({"v2_added_key": "phase_code"}),
        lambda c: c["declared"]["v1_keys"].reverse(),
        lambda c: c["provenance"].update({"executed_against_admission_sio": True}),
        lambda c: c["provenance"].update({"derived_by": "measurement"}),
    ]
    vector_mutations = [
        lambda v: v["cases"][0].update({"expect_accepted": False}),
        lambda v: v["cases"][0].update({"kind": 2}),
        lambda v: v["cases"].append(copy.deepcopy(v["cases"][0])),
    ]
    caught = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for n, fn in enumerate(contract_mutations):
            m = copy.deepcopy(contract); fn(m)
            path = root / f"c{n}.json"; path.write_text(json.dumps(m))
            try:
                load_and_run(schema_path, path, vectors_path, None)
            except (ValueError, KeyError):
                caught += 1
            else:
                raise SystemExit(f"contract mutation {n} was not rejected")
        for n, fn in enumerate(vector_mutations):
            m = copy.deepcopy(vectors); fn(m)
            path = root / f"v{n}.json"; path.write_text(json.dumps(m))
            try:
                load_and_run(schema_path, contract_path, path, None)
            except (ValueError, KeyError):
                caught += 1
            else:
                raise SystemExit(f"vector mutation {n} was not rejected")
    return caught


def main():
    ap = argparse.ArgumentParser(description=CONTRACT_ID)
    ap.add_argument("--schema", type=pathlib.Path, required=True)
    ap.add_argument("--contract", type=pathlib.Path, required=True)
    ap.add_argument("--vectors", type=pathlib.Path, required=True)
    ap.add_argument("--receipts", type=pathlib.Path)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        caught = mutation_selftest(args.schema, args.contract, args.vectors)
        load_and_run(args.schema, args.contract, args.vectors, args.receipts)
        print(f"MUTATION_SELFTEST_PASS caught={caught}")
        return 0
    load_and_run(args.schema, args.contract, args.vectors, args.receipts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
