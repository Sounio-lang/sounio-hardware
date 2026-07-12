# Agent Contract

This repository is the hardware evidence surface for Sounio and EISA.

## Rules

- Treat executable specifications, vectors, gates, and receipts as the source
  of truth.
- Do not claim RTL, synthesis, formal verification, timing, power, area, FPGA,
  ASIC, or silicon evidence unless the corresponding artifact and gate exist.
- Preserve ordered operands for non-associative and non-commutative algebras.
- Never replace exact zero with a tolerance test unless a new versioned
  contract explicitly defines that semantics.
- Keep software-oracle receipts distinct from simulator, formal, FPGA, and
  silicon receipts.
- Every semantic change requires adversarial vectors and deterministic replay.
- Keep commits small and do not mix contract changes with RTL optimization.

## Initial boundary

`eisa_h.sedenion_zd_pair.v1` accepts `sed16` operands containing at most two
nonzero coefficients, each exactly `-1` or `1`. Larger coefficient domains and
near-zero predicates require new contracts.
