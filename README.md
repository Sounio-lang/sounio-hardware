# Sounio Hardware

Reference hardware contracts and, eventually, implementations for Sounio and
EISA semantics.

The repository begins with executable contracts rather than decorative RTL.
The first contract specifies exact ordered-pair zero-divisor detection for the
16-dimensional Cayley-Dickson algebra (`sed16`). Its software oracle, vectors,
and receipts define what a later RTL implementation must reproduce.

Run the current gate with:

```sh
bash scripts/gate_zd_pair_contract.sh
bash scripts/gate_zd_pair_rtl.sh
```

## Claim boundary

The software contract proves that ten required cases are deterministic and
that eight specified mutation classes are rejected. The RTL gate simulates nine
fixed-width cases, six adversarial boundaries, and all 1,024 signed basis
combinations on an iterative 256-MAC core; malformed
operand shape remains an interface-layer rejection. No synthesis, formal
equivalence, timing, power, area, FPGA, ASIC, or silicon result is claimed.

## Ownership

- `Sounio-lang/sounio` owns language-level semantics and cross-repository
  compiler integration.
- This repository owns hardware-facing contracts, RTL, testbenches, synthesis,
  formal verification, and hardware receipts.

Apache-2.0 licensed. See [LICENSE](LICENSE).
