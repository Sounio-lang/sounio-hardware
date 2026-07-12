# EISA-H ZD Pair v1 Review Receipt

Date: 2026-07-12

## Reviewed surface

- `tools/eisa_h/zd_pair_oracle.py`
- Contract identity: `eisa_h.sedenion_zd_pair.v1`
- Bounded domain: `sed16`, ordered operands, at most two nonzero coefficients
  per operand, each exactly `-1` or `1`

## Provider review

- Provider: xAI, Grok 4.3
- Route: Sounio `bin/llm-offload -t math-review -p xai`
- Outcome: PASS
- Reviewer findings: the Cayley-Dickson sign recursion, XOR-indexed product,
  exact accumulation, zero-operand exclusion, zero-divisor classification,
  and basis-table fingerprint were judged algebraically consistent.
- Raw local receipt: `/tmp/llm-offload-5Soit4/` (ephemeral; recorded here so
  the durable outcome does not depend on that path)
- Post-hardening rerun: xAI returned `NO MATHEMATICAL CONTENT TO REVIEW`,
  classifying the final executable definition as code rather than a separate
  derivation. This is recorded without promoting it to an additional PASS.

## Post-review hardening

- Added schema identity to every execution receipt.
- Added the reversed basis witness `e2*e1 = -e3` alongside `e1*e2 = e3`.
- Bound the declared arithmetic, error-code, vector-set, and receipt-identity
  fields to the oracle validation path.
- Mutation tests address root and nested schema drift, basis-table hash tampering, sign
  tampering, duplicate case identity, operand shape, and expected-product
  tampering, plus removal of required error coverage.

## Evidence boundary

This review supports the bounded software-oracle contract. It is not evidence
of RTL, synthesis, formal equivalence, FPGA execution, ASIC execution, timing,
power, area, or silicon behavior.
