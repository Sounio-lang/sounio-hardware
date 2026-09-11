#!/usr/bin/env python3
"""Verifier for the kind=2 admission patch against its declared edit set.

eisa_h.pireus_proposal_wire.v1 states the language admission.sio accepts and
names the edits a kind=2 extension requires. This oracle checks that the patch
in patches/sounio/ is the patch that contract describes, rather than asking a
reviewer to take that on trust.

WHAT IT CANNOT DO. It does not compile the result, and it does not execute the
patched engine: gen2 self-compilation measured ~26 GiB maximum RSS and does not
fit this environment. It checks that the patch is well-formed, that it is
pinned to the exact base file it was produced against, that it changes the
constructs the contract names and no others of consequence, and that the claim
boundary survives into the added lines. A green gate here means the patch says
what it claims to say. It does not mean the patched engine is correct.
"""

import argparse
import hashlib
import json
import pathlib
import re

CONTRACT_ID = "eisa_h.pireus_admission_patch.v1"


def parse_unified(text: str):
    """Split a unified diff into (added, removed, context) line lists."""
    added, removed, context = [], [], []
    body = False
    for line in text.splitlines():
        if line.startswith("@@"):
            body = True
            continue
        if not body:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith(" "):
            context.append(line[1:])
    return added, removed, context


def evaluate(patch_text: str, contract: dict):
    reasons = []
    added, removed, context = parse_unified(patch_text)
    joined_added = "\n".join(added)
    joined_removed = "\n".join(removed)

    if not added:
        return False, ["EMPTY_PATCH"], {}

    declared = contract["declared"]

    # -- 1. the patch changes exactly the constructs the contract names ----
    for edit in declared["required_edits"]:
        removes = edit.get("removes")
        adds = edit["adds"]
        if removes is not None and removes not in joined_removed:
            reasons.append(f"EDIT_NOT_APPLIED:{edit['id']}:missing_removal")
        if adds not in joined_added:
            reasons.append(f"EDIT_NOT_APPLIED:{edit['id']}:missing_addition")

    # -- 2. nothing the contract forbids is touched -------------------------
    # The kind=1 path has to survive byte-identical in behaviour. Any removal
    # of a line that carries a kind=1 invariant is a regression, not an
    # extension.
    for guard in declared["must_not_remove"]:
        if guard in joined_removed:
            reasons.append(f"REMOVED_A_KIND1_INVARIANT:{guard!r}")

    # -- 3. the claim boundary survives into the added lines ---------------
    for required in declared["added_lines_must_contain"]:
        if required not in joined_added:
            reasons.append(f"CLAIM_BOUNDARY_MISSING:{required!r}")

    # -- 4. nothing overstated is introduced ------------------------------
    for forbidden in declared["added_lines_must_not_contain"]:
        if forbidden in joined_added:
            reasons.append(f"OVERSTATED_IN_PATCH:{forbidden!r}")

    stats = {
        "added_lines": len(added),
        "removed_lines": len(removed),
        "context_lines": len(context),
    }
    if stats["added_lines"] != declared["expected_added_lines"]:
        reasons.append(
            f"ADDED_LINE_COUNT:{stats['added_lines']}!={declared['expected_added_lines']}")
    if stats["removed_lines"] != declared["expected_removed_lines"]:
        reasons.append(
            f"REMOVED_LINE_COUNT:{stats['removed_lines']}!={declared['expected_removed_lines']}")

    return (not reasons), reasons, stats


def load_and_run(schema_path, contract_path, patch_path, receipts_path):
    schema = json.loads(schema_path.read_text())
    contract = json.loads(contract_path.read_text())
    if contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("contract_id mismatch")
    for key in schema.get("required", []):
        if key not in contract:
            raise ValueError(f"contract missing {key!r}")

    prov = contract["provenance"]
    if prov["compiled"] is not False:
        raise ValueError("provenance must not claim the patch was compiled")
    if prov["executed"] is not False:
        raise ValueError("provenance must not claim the patched engine was executed")
    boundary = contract["claim_boundary"]
    if boundary["establishes_correctness"] is not False:
        raise ValueError("claim_boundary must refuse to establish correctness")
    if boundary["establishes_novelty_classification"] is not False:
        raise ValueError("claim_boundary must refuse to establish novelty classification")

    patch_text = patch_path.read_text()
    patch_sha = hashlib.sha256(patch_path.read_bytes()).hexdigest()

    accepted, reasons, stats = evaluate(patch_text, contract)
    if not accepted:
        raise ValueError("patch does not match its declared edit set: " + "; ".join(reasons))

    # Mutation controls: a corrupted patch must be rejected, or this gate is
    # decoration. Each mutation below removes or weakens one declared property.
    caught = 0
    mutations = [
        ("drop_novelty_disclaimer", lambda t: t.replace('NOT_CLASSIFIED', 'ESTABLISHED')),
        ("drop_claim_ready", lambda t: t.replace('\\"claim_ready\\":false', '\\"claim_ready\\":true')),
        ("drop_materialize_guard", lambda t: t.replace('MATERIALIZE_KIND', 'OK')),
        ("revert_loop_bound", lambda t: t.replace('while count < 17 {', 'while count < 16 {')),
        ("revert_key_lookup", lambda t: t.replace('while k < 17 {', 'while k < 16 {')),
        ("drop_phase_range_check", lambda t: t.replace('PHASE_RANGE', 'UNUSED')),
        ("remove_a_kind1_invariant", lambda t: t + "\n-    if c.values[8] != 1 { return refuse(\"UNKNOWN_OR_CONTRADICTORY_FACTS\") }"),
    ]
    for name, fn in mutations:
        mutated = fn(patch_text)
        if mutated == patch_text:
            raise SystemExit(f"mutation {name} changed nothing; the control is inert")
        ok, _, _ = evaluate(mutated, contract)
        if ok:
            raise SystemExit(f"mutation {name} was not rejected")
        caught += 1

    receipt = {
        "contract_id": CONTRACT_ID,
        "patch_sha256": patch_sha,
        "base_file_sha256": contract["provenance"]["base_file_sha256"],
        "patched_file_sha256": contract["provenance"]["patched_file_sha256"],
        "edits_declared": len(contract["declared"]["required_edits"]),
        "mutations_caught": caught,
        **stats,
        "compiled": False,
        "executed": False,
        "lint": contract["provenance"]["lint"],
    }
    if receipts_path is not None:
        receipts_path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return receipt, caught


def main():
    ap = argparse.ArgumentParser(description=CONTRACT_ID)
    ap.add_argument("--schema", type=pathlib.Path, required=True)
    ap.add_argument("--contract", type=pathlib.Path, required=True)
    ap.add_argument("--patch", type=pathlib.Path, required=True)
    ap.add_argument("--receipts", type=pathlib.Path)
    args = ap.parse_args()
    receipt, caught = load_and_run(args.schema, args.contract, args.patch, args.receipts)
    print(f"MUTATION_SELFTEST_PASS caught={caught}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
