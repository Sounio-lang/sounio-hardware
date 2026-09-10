#!/usr/bin/env python3
"""Admissibility oracle for PIREUS material-parity receipts.

The oracle decides whether a receipt is admissible evidence of the measurement
it reports. It does not re-run the measurement, and accepting a receipt asserts
nothing about whether the measured result is correct or advantageous.
"""

import argparse
import copy
import hashlib
import json
import pathlib
import tempfile
from typing import Any

CONTRACT_ID = "eisa_h.pireus_material_parity.v1"

REQUIRED_CASE_IDS = {
    "canonical-accepted-receipt",
    "observed-mismatch-negative-control",
    "producer-claims-semantic-authority",
    "vacuous-sign-mutation-control",
    "vacuous-selector-mutation-control",
    "pass-with-unresolved-mismatch",
    "cell-count-not-conserved",
    "reassociated-evaluation-order",
    "flush-to-zero-enabled",
    "claim-ready-promoted",
    "gain-field-in-parity-receipt",
    "duplicate-field",
    "missing-required-field",
    "malformed-integer-value",
}

INT_FIELDS = (
    "dimension",
    "partner_cells",
    "partner_failures",
    "negative_cells",
    "positive_cells",
    "vector_matching_lanes",
    "vector_mismatching_lanes",
    "vector_first_mismatch",
    "sign_mutation_mismatching_lanes",
    "selector_mutation_mismatching_lanes",
)
BOOL_FIELDS = (
    "flush_to_zero",
    "denormals_are_zero",
    "ascending_i",
    "reassociated",
    "claim_ready",
    "generic_cost_claim",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_json_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "const" in schema and instance != schema["const"]:
        raise ValueError(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ValueError(f"{path}: {instance!r} not in enum")
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(instance, dict):
            raise ValueError(f"{path}: expected object")
        for key in schema.get("required", []):
            if key not in instance:
                raise ValueError(f"{path}: missing required key {key!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    raise ValueError(f"{path}: unexpected key {key!r}")
        for key, sub in props.items():
            if key in instance:
                validate_json_schema(instance[key], sub, f"{path}.{key}")
    elif expected == "array":
        if not isinstance(instance, list):
            raise ValueError(f"{path}: expected array")
        if schema.get("uniqueItems") and len(instance) != len(
            {canonical_bytes(item) for item in instance}
        ):
            raise ValueError(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                validate_json_schema(item, item_schema, f"{path}[{index}]")
    elif expected == "string" and not isinstance(instance, str):
        raise ValueError(f"{path}: expected string")


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("contract_id mismatch")
    authority = contract["authority"]
    if authority["producer_role"] == authority["semantic_authority_role"]:
        raise ValueError("producer and semantic authority roles must differ")
    required = contract["required_fields"]
    if len(required) != len(set(required)):
        raise ValueError("required_fields contains duplicates")
    for field in ("result", "producer_role", "semantic_authority_role"):
        if field not in required:
            raise ValueError(f"required_fields must include {field!r}")
    for code in (
        "PRODUCER_CLAIMS_AUTHORITY",
        "VACUOUS_MUTATION_CONTROL",
        "GAIN_CLAIM_IN_PARITY_RECEIPT",
    ):
        if code not in contract["error_codes"]:
            raise ValueError(f"error_codes must include {code!r}")
    if contract["claim_boundary"].get("establishes_gain") is not False:
        raise ValueError("claim_boundary must refuse gain establishment")


def parse_receipt(lines: list[str]) -> tuple[dict[str, str], str | None]:
    fields: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            return fields, "MALFORMED_VALUE"
        key, _, value = line.partition("=")
        if not key:
            return fields, "MALFORMED_VALUE"
        if key in fields:
            return fields, "DUPLICATE_FIELD"
        fields[key] = value
    return fields, None


def classify(fields: dict[str, str], contract: dict[str, Any]) -> tuple[str, str | None]:
    """Return (classification, error_code). Order of checks is part of the contract."""
    for key in fields:
        for banned in contract["forbidden_field_substrings"]:
            if banned in key:
                return "REJECTED_RECEIPT", "GAIN_CLAIM_IN_PARITY_RECEIPT"

    for field in contract["required_fields"]:
        if field not in fields:
            return "REJECTED_RECEIPT", "MISSING_REQUIRED_FIELD"

    numbers: dict[str, int] = {}
    for field in INT_FIELDS:
        raw = fields[field]
        try:
            numbers[field] = int(raw)
        except ValueError:
            return "REJECTED_RECEIPT", "MALFORMED_VALUE"
    flags: dict[str, bool] = {}
    for field in BOOL_FIELDS:
        raw = fields[field]
        if raw not in ("true", "false"):
            return "REJECTED_RECEIPT", "MALFORMED_VALUE"
        flags[field] = raw == "true"
    if fields["result"] not in ("PASS", "FAIL"):
        return "REJECTED_RECEIPT", "MALFORMED_VALUE"

    authority = contract["authority"]
    if (
        fields["producer_role"] != authority["producer_role"]
        or fields["semantic_authority_role"] != authority["semantic_authority_role"]
        or fields["semantic_authority_language"] != authority["semantic_authority_language"]
    ):
        return "REJECTED_RECEIPT", "PRODUCER_CLAIMS_AUTHORITY"

    if (
        numbers["sign_mutation_mismatching_lanes"] <= 0
        or numbers["selector_mutation_mismatching_lanes"] <= 0
    ):
        return "REJECTED_RECEIPT", "VACUOUS_MUTATION_CONTROL"

    cells = numbers["dimension"] * numbers["dimension"]
    if (
        numbers["positive_cells"] + numbers["negative_cells"] != cells
        or numbers["partner_cells"] + numbers["partner_failures"] != cells
    ):
        return "REJECTED_RECEIPT", "CELL_COUNT_INCONSISTENT"

    if not flags["ascending_i"] or flags["reassociated"]:
        return "REJECTED_RECEIPT", "EVALUATION_ORDER_MODIFIED"

    if (
        fields["rounding_mode"] != "FE_TONEAREST"
        or flags["flush_to_zero"]
        or flags["denormals_are_zero"]
    ):
        return "REJECTED_RECEIPT", "NUMERIC_ENVIRONMENT_MODIFIED"

    if flags["claim_ready"] or flags["generic_cost_claim"]:
        return "REJECTED_RECEIPT", "UNSUPPORTED_CLAIM_PROMOTION"

    clean = (
        numbers["vector_mismatching_lanes"] == 0
        and numbers["vector_first_mismatch"] == -1
        and numbers["partner_failures"] == 0
    )
    if fields["result"] == "PASS":
        if not clean:
            return "REJECTED_RECEIPT", "PARITY_INCONSISTENT_WITH_RESULT"
        return "ACCEPTED_MATERIAL_PARITY", None
    if clean:
        return "REJECTED_RECEIPT", "PARITY_INCONSISTENT_WITH_RESULT"
    return "OBSERVED_MISMATCH", None


def evaluate(case: dict[str, Any], contract: dict[str, Any], ident: dict[str, str]) -> dict[str, Any]:
    fields, parse_error = parse_receipt(case["receipt_lines"])
    if parse_error is not None:
        classification, error_code = "REJECTED_RECEIPT", parse_error
    else:
        classification, error_code = classify(fields, contract)
    return {
        "case_id": case["case_id"],
        "contract_id": CONTRACT_ID,
        "classification": classification,
        "error_code": error_code,
        "field_count": len(fields),
        **ident,
    }


def validate_vectors(vectors: dict[str, Any], contract: dict[str, Any]) -> None:
    if vectors.get("contract_id") != CONTRACT_ID:
        raise ValueError("vectors contract_id mismatch")
    ids = [case["case_id"] for case in vectors["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case_id in vectors")
    missing = REQUIRED_CASE_IDS - set(ids)
    if missing:
        raise ValueError(f"vectors missing required cases: {sorted(missing)}")
    seen_classifications = set()
    for case in vectors["cases"]:
        expect = case["expect"]
        if expect["classification"] not in contract["classifications"]:
            raise ValueError(f"{case['case_id']}: unknown classification")
        code = expect["error_code"]
        if code is not None and code not in contract["error_codes"]:
            raise ValueError(f"{case['case_id']}: unknown error_code {code!r}")
        seen_classifications.add(expect["classification"])
    if set(contract["classifications"]) - seen_classifications:
        raise ValueError("vectors must exercise every classification")


def load_and_run(
    schema_path: pathlib.Path,
    contract_path: pathlib.Path,
    vectors_path: pathlib.Path,
    receipts_path: pathlib.Path | None,
) -> list[dict[str, Any]]:
    schema = json.loads(schema_path.read_text())
    contract = json.loads(contract_path.read_text())
    vectors = json.loads(vectors_path.read_text())
    validate_json_schema(contract, schema)
    validate_contract(contract)
    validate_vectors(vectors, contract)
    ident = {
        "schema_sha256": file_sha256(schema_path),
        "contract_sha256": file_sha256(contract_path),
        "vectors_sha256": file_sha256(vectors_path),
    }
    receipts = []
    for case in vectors["cases"]:
        result = evaluate(case, contract, ident)
        expect = case["expect"]
        if (
            result["classification"] != expect["classification"]
            or result["error_code"] != expect["error_code"]
        ):
            raise ValueError(
                f"{case['case_id']}: expected {expect['classification']}/{expect['error_code']}, "
                f"got {result['classification']}/{result['error_code']}"
            )
        receipts.append(result)
    if receipts_path is not None:
        receipts_path.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in receipts)
        )
    return receipts


def mutation_selftest(
    schema_path: pathlib.Path, contract_path: pathlib.Path, vectors_path: pathlib.Path
) -> int:
    contract = json.loads(contract_path.read_text())
    vectors = json.loads(vectors_path.read_text())

    def mutate_contract(fn) -> dict[str, Any]:
        mutated = copy.deepcopy(contract)
        fn(mutated)
        return mutated

    def mutate_vectors(fn) -> dict[str, Any]:
        mutated = copy.deepcopy(vectors)
        fn(mutated)
        return mutated

    def case(mutated_vectors: dict[str, Any], case_id: str) -> dict[str, Any]:
        for entry in mutated_vectors["cases"]:
            if entry["case_id"] == case_id:
                return entry
        raise ValueError(f"case {case_id} absent")

    contract_mutations = [
        lambda c: c.update({"contract_id": "eisa_h.pireus_material_parity.v2"}),
        lambda c: c["authority"].update({"producer_role": "SEMANTIC_AUTHORITY"}),
        lambda c: c["error_codes"].remove("VACUOUS_MUTATION_CONTROL"),
        lambda c: c["error_codes"].remove("GAIN_CLAIM_IN_PARITY_RECEIPT"),
        lambda c: c["claim_boundary"].update({"establishes_gain": True}),
        lambda c: c["required_fields"].remove("result"),
        lambda c: c["forbidden_field_substrings"].remove("gain"),
    ]
    vector_mutations = [
        lambda v: case(v, "canonical-accepted-receipt")["expect"].update(
            {"classification": "REJECTED_RECEIPT"}
        ),
        lambda v: case(v, "vacuous-sign-mutation-control")["expect"].update({"error_code": None}),
        lambda v: v["cases"].remove(case(v, "gain-field-in-parity-receipt")),
        lambda v: v["cases"].append(copy.deepcopy(case(v, "canonical-accepted-receipt"))),
    ]

    caught = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        for index, mutation in enumerate(contract_mutations):
            path = tmp_path / f"contract-{index}.json"
            path.write_text(json.dumps(mutate_contract(mutation)))
            try:
                load_and_run(schema_path, path, vectors_path, None)
            except (ValueError, KeyError):
                caught += 1
            else:
                raise SystemExit(f"contract mutation {index} was not rejected")
        for index, mutation in enumerate(vector_mutations):
            path = tmp_path / f"vectors-{index}.json"
            path.write_text(json.dumps(mutate_vectors(mutation)))
            try:
                load_and_run(schema_path, contract_path, path, None)
            except (ValueError, KeyError):
                caught += 1
            else:
                raise SystemExit(f"vector mutation {index} was not rejected")
    return caught


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--contract", type=pathlib.Path)
    parser.add_argument("--vectors", type=pathlib.Path)
    parser.add_argument("--receipts", type=pathlib.Path)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
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
