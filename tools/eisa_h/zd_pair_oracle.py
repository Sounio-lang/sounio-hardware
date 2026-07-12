#!/usr/bin/env python3
"""Executable oracle for eisa_h.sedenion_zd_pair.v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re
import tempfile
from typing import Any

DIMENSION = 16
COEFFICIENT_LIMIT = 1_518_500_249
CONTRACT_ID = "eisa_h.sedenion_zd_pair.v1"
V1_BASIS_TABLE_SHA256 = "e2b59d42ab7d44ead7f085e9e9b34df2ba1667445b0c89eff79cd8d921faa19d"
REQUIRED_CASE_IDS = {
    "canonical-zero-divisor-pair",
    "basis-orientation-e1-e2",
    "basis-orientation-e2-e1",
    "same-support-sign-tamper",
    "zero-left-operand",
    "unsupported-coefficient-two",
    "overflow-risk-forged-coefficient",
    "zero-left-overflow-right",
    "too-many-nonzero-coefficients",
    "invalid-operand-shape",
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


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


def basis_table_bytes() -> bytes:
    return bytes(1 if cd_sigma(i, j) == 1 else 255 for i in range(DIMENSION) for j in range(DIMENSION))


def basis_table_sha256() -> str:
    return sha256_bytes(basis_table_bytes())


def validate_json_schema(instance: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "const" in schema and instance != schema["const"]:
        raise ValueError(f"schema const mismatch at {path}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ValueError(f"schema enum mismatch at {path}")
    kind = schema.get("type")
    type_ok = {
        "object": isinstance(instance, dict),
        "array": isinstance(instance, list),
        "string": isinstance(instance, str),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
        "boolean": isinstance(instance, bool),
        "null": instance is None,
    }
    if kind in type_ok and not type_ok[kind]:
        raise ValueError(f"schema type mismatch at {path}: expected {kind}")
    if kind == "string" and "pattern" in schema and re.fullmatch(schema["pattern"], instance) is None:
        raise ValueError(f"schema pattern mismatch at {path}")
    if kind == "array":
        if schema.get("uniqueItems") and len({canonical_bytes(item) for item in instance}) != len(instance):
            raise ValueError(f"schema uniqueItems mismatch at {path}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(instance):
                validate_json_schema(item, item_schema, f"{path}[{index}]")
    if kind == "object":
        required = schema.get("required", [])
        missing = [key for key in required if key not in instance]
        if missing:
            raise ValueError(f"schema required mismatch at {path}: {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(properties)
            if extra:
                raise ValueError(f"schema additionalProperties mismatch at {path}: {sorted(extra)}")
        for key, value in instance.items():
            if key in properties:
                validate_json_schema(value, properties[key], f"{path}.{key}")


def validate_schema(schema: dict[str, Any], contract: dict[str, Any]) -> None:
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("invalid schema dialect")
    if not str(schema.get("$id", "")).endswith("/sedenion_zd_pair_v1.schema.json"):
        raise ValueError("invalid schema identity")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("schema must close the contract object")
    required, properties = schema.get("required"), schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        raise ValueError("schema structure is incomplete")
    if not set(required).issubset(contract) or not set(contract).issubset(properties):
        raise ValueError("schema and contract keys disagree")
    validate_json_schema(contract, schema)


def validate_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != 1 or contract.get("contract_id") != CONTRACT_ID:
        raise ValueError("invalid contract identity")
    fmt = contract.get("format", {})
    if fmt != {
        "algebra": "cayley-dickson-sedenion",
        "dimension": 16,
        "basis_order": "e0..e15",
        "ordered_operands": True,
    }:
        raise ValueError("invalid format declaration")
    table = contract.get("basis_table", {})
    if table.get("rule") != "recursive-cayley-dickson-v1" or table.get("encoding") != "row-major-int8-signs":
        raise ValueError("invalid basis table declaration")
    if basis_table_sha256() != V1_BASIS_TABLE_SHA256:
        raise ValueError("oracle basis table drifted from the v1 anchor")
    if table.get("sha256") != V1_BASIS_TABLE_SHA256:
        raise ValueError("basis table hash mismatch")
    domain = contract.get("operand_domain", {})
    if domain.get("coefficient_type") != "signed-integer":
        raise ValueError("invalid coefficient type")
    if domain.get("allowed_nonzero_values") != [-1, 1]:
        raise ValueError("invalid coefficient domain")
    if domain.get("maximum_nonzero_coefficients_per_operand") != 2:
        raise ValueError("invalid support bound")
    if domain.get("overflow_risk_abs_coefficient_threshold") != COEFFICIENT_LIMIT:
        raise ValueError("invalid overflow-risk threshold")
    if contract.get("arithmetic") != {
        "accumulator": "exact-signed-i64",
        "zero_predicate": "all-16-product-coefficients-exactly-zero",
        "near_zero_semantics": "outside-v1",
        "basis_product": "e_i * e_j = sign(i,j) * e_(i xor j)",
    }:
        raise ValueError("invalid arithmetic declaration")
    classifications = ["EXACT_ZD_PAIR", "NONZERO_PRODUCT", "INVALID_ZERO_OPERAND", "ARITHMETIC_ERROR"]
    if contract.get("classifications") != classifications:
        raise ValueError("classification set mismatch")
    required_errors = [
        "INVALID_OPERAND_SHAPE",
        "UNSUPPORTED_COEFFICIENT_DOMAIN",
        "TOO_MANY_NONZERO_COEFFICIENTS",
        "OVERFLOW_RISK",
    ]
    if contract.get("error_codes") != required_errors:
        raise ValueError("error-code set mismatch")
    required_identities = [
        "schema_sha256",
        "contract_sha256",
        "vectors_sha256",
        "basis_table_sha256",
        "input_sha256",
    ]
    receipt = contract.get("receipt", {})
    if receipt.get("execution_surface") != "software_oracle" or receipt.get("hardware_cycles") is not None:
        raise ValueError("invalid receipt surface declaration")
    if receipt.get("required_identity_fields") != required_identities:
        raise ValueError("receipt identity set mismatch")
    if contract.get("future_rtl_target") != {
        "status": "not-implemented",
        "candidate_architecture": "iterative-256-basis-product-mac",
        "candidate_mac_cycles": 256,
        "claim": "design-target-only",
    }:
        raise ValueError("invalid future RTL claim boundary")


def operand_error(lhs: Any, rhs: Any) -> str | None:
    if not isinstance(lhs, list) or not isinstance(rhs, list) or len(lhs) != DIMENSION or len(rhs) != DIMENSION:
        return "INVALID_OPERAND_SHAPE"
    if any(isinstance(x, bool) or not isinstance(x, int) for x in lhs + rhs):
        return "INVALID_OPERAND_SHAPE"
    if any(abs(x) > COEFFICIENT_LIMIT for x in lhs + rhs):
        return "OVERFLOW_RISK"
    if sum(x != 0 for x in lhs) > 2 or sum(x != 0 for x in rhs) > 2:
        return "TOO_MANY_NONZERO_COEFFICIENTS"
    if any(x not in (-1, 0, 1) for x in lhs + rhs):
        return "UNSUPPORTED_COEFFICIENT_DOMAIN"
    if not any(lhs) or not any(rhs):
        return "ZERO_OPERAND"
    return None


def multiply(lhs: list[int], rhs: list[int]) -> list[int]:
    product = [0] * DIMENSION
    for i, left in enumerate(lhs):
        if left == 0:
            continue
        for j, right in enumerate(rhs):
            if right != 0:
                product[i ^ j] += cd_sigma(i, j) * left * right
    if any(value < -(1 << 63) or value > (1 << 63) - 1 for value in product):
        raise OverflowError("signed i64 accumulator overflow")
    return product


def evaluate(case: dict[str, Any], schema_sha: str, contract_sha: str, vectors_sha: str) -> dict[str, Any]:
    lhs, rhs = case.get("lhs"), case.get("rhs")
    error = operand_error(lhs, rhs)
    product: list[int] | None = None
    if error == "ZERO_OPERAND":
        classification, error_code = "INVALID_ZERO_OPERAND", None
    elif error is not None:
        classification, error_code = "ARITHMETIC_ERROR", error
    else:
        product = multiply(lhs, rhs)
        classification = "EXACT_ZD_PAIR" if not any(product) else "NONZERO_PRODUCT"
        error_code = None
    first_nonzero = next((index for index, value in enumerate(product or []) if value), None)
    return {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "case_id": case.get("case_id"),
        "format": "sed16",
        "ordered_operands": True,
        "schema_sha256": schema_sha,
        "contract_sha256": contract_sha,
        "vectors_sha256": vectors_sha,
        "basis_table_sha256": basis_table_sha256(),
        "input_sha256": sha256_bytes(canonical_bytes({"lhs": lhs, "rhs": rhs})),
        "classification": classification,
        "error_code": error_code,
        "lhs_nonzero": isinstance(lhs, list) and any(lhs),
        "rhs_nonzero": isinstance(rhs, list) and any(rhs),
        "product_is_zero": product is not None and not any(product),
        "overflow": error_code == "OVERFLOW_RISK",
        "first_nonzero_component": first_nonzero,
        "product": product,
        "execution_surface": "software_oracle",
        "hardware_cycles": None,
    }


def validate_vectors(
    vectors: dict[str, Any], schema_sha: str, contract_sha: str, vectors_sha: str
) -> list[dict[str, Any]]:
    if (
        vectors.get("vector_set_id") != "eisa_h.sedenion_zd_pair.v1.canonical"
        or vectors.get("contract_id") != CONTRACT_ID
        or not isinstance(vectors.get("cases"), list)
    ):
        raise ValueError("invalid vector set identity")
    case_ids = [case.get("case_id") for case in vectors["cases"]]
    if any(not isinstance(case_id, str) or not case_id for case_id in case_ids) or len(case_ids) != len(set(case_ids)):
        raise ValueError("case IDs must be unique nonempty strings")
    if set(case_ids) != REQUIRED_CASE_IDS or len(case_ids) != len(REQUIRED_CASE_IDS):
        raise ValueError("required vector coverage mismatch")
    receipts = []
    for case in vectors["cases"]:
        receipt = evaluate(case, schema_sha, contract_sha, vectors_sha)
        expected = case.get("expect")
        actual = {key: receipt[key] for key in ("classification", "error_code", "product")}
        if expected != actual:
            raise ValueError(f"expectation mismatch for {case['case_id']}: expected={expected!r} actual={actual!r}")
        receipts.append(receipt)
    return receipts


def load_and_run(
    schema_path: pathlib.Path, contract_path: pathlib.Path, vectors_path: pathlib.Path
) -> list[dict[str, Any]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))
    validate_schema(schema, contract)
    validate_contract(contract)
    return validate_vectors(
        vectors, file_sha256(schema_path), file_sha256(contract_path), file_sha256(vectors_path)
    )


def mutation_selftest(schema_path: pathlib.Path, contract_path: pathlib.Path, vectors_path: pathlib.Path) -> int:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    vectors = json.loads(vectors_path.read_text(encoding="utf-8"))
    mutations = []

    bad_schema = copy.deepcopy(schema)
    bad_schema["properties"].pop("future_rtl_target")
    mutations.append((bad_schema, contract, vectors))

    bad_nested_schema = copy.deepcopy(schema)
    bad_nested_schema["properties"]["receipt"]["type"] = "integer"
    mutations.append((bad_nested_schema, contract, vectors))

    bad_hash = copy.deepcopy(contract)
    bad_hash["basis_table"]["sha256"] = "0" * 64
    mutations.append((schema, bad_hash, vectors))

    bad_sign = copy.deepcopy(vectors)
    bad_sign["cases"][0]["rhs"][15] = 1
    mutations.append((schema, contract, bad_sign))

    duplicate = copy.deepcopy(vectors)
    duplicate["cases"][1]["case_id"] = duplicate["cases"][0]["case_id"]
    mutations.append((schema, contract, duplicate))

    bad_shape = copy.deepcopy(vectors)
    bad_shape["cases"][1]["lhs"] = bad_shape["cases"][1]["lhs"] + [0]
    mutations.append((schema, contract, bad_shape))

    bad_product = copy.deepcopy(vectors)
    tamper_case = next(case for case in bad_product["cases"] if case["case_id"] == "same-support-sign-tamper")
    tamper_case["expect"]["product"][5] = 0
    mutations.append((schema, contract, bad_product))

    missing_coverage = copy.deepcopy(vectors)
    missing_coverage["cases"] = [
        case for case in missing_coverage["cases"] if case["case_id"] != "overflow-risk-forged-coefficient"
    ]
    mutations.append((schema, contract, missing_coverage))

    caught = 0
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        for index, (mutated_schema, mutated_contract, mutated_vectors) in enumerate(mutations):
            schema_file = root / f"schema-{index}.json"
            contract_file, vectors_file = root / f"contract-{index}.json", root / f"vectors-{index}.json"
            schema_file.write_bytes(canonical_bytes(mutated_schema))
            contract_file.write_bytes(canonical_bytes(mutated_contract))
            vectors_file.write_bytes(canonical_bytes(mutated_vectors))
            try:
                load_and_run(schema_file, contract_file, vectors_file)
            except (ValueError, OverflowError, json.JSONDecodeError):
                caught += 1
    if caught != len(mutations):
        raise RuntimeError(f"mutation selftest caught {caught}/{len(mutations)}")
    return caught


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=pathlib.Path)
    parser.add_argument("--contract", type=pathlib.Path)
    parser.add_argument("--vectors", type=pathlib.Path)
    parser.add_argument("--receipts", type=pathlib.Path)
    parser.add_argument("--print-table-hash", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.print_table_hash:
        print(basis_table_sha256())
        return 0
    if not args.schema or not args.contract or not args.vectors:
        parser.error("--schema, --contract, and --vectors are required")
    receipts = load_and_run(args.schema, args.contract, args.vectors)
    if args.selftest:
        caught = mutation_selftest(args.schema, args.contract, args.vectors)
        print(f"MUTATION_SELFTEST_PASS caught={caught}")
    output = b"".join(canonical_bytes(receipt) for receipt in receipts)
    if args.receipts:
        args.receipts.write_bytes(output)
    else:
        print(output.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
