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
bash scripts/slurm/run_zd_pair_synth.sh
```

## Claim boundary

The software contract proves that ten required cases are deterministic and
that eight specified mutation classes are rejected. The RTL gate simulates nine
fixed-width cases, six adversarial boundaries, and all 1,024 signed basis
combinations on an iterative 256-MAC core; malformed
operand shape remains an interface-layer rejection. That simulation receipt
does not claim synthesis or any physical result.

The synthesis gate runs through Slurm and includes the exhaustive RTL gate
before proving deterministic replay with Yosys 0.33 on the same tool and host.
It produces a fully lowered generic netlist with no remaining behavioral
processes. Its cell count is not a physical area claim; technology mapping,
post-synthesis equivalence, timing, power, FPGA, ASIC, and silicon evidence
remain separate milestones.

The direct `scripts/gate_zd_pair_synth.sh` entrypoint is the worker-side gate.
Use the Slurm launcher from the interactive workspace; its returned job ID,
node, logs, source commit, and artifact hashes are part of the evidence.
The bundled Yosys/Icarus toolchain is explicitly limited to Linux x86_64 with
glibc. Its files and the node's absolute ELF loader are checksum-verified
before execution, so a heterogeneous loader ABI is classified as blocked.

## Ownership

- `Sounio-lang/sounio` owns language-level semantics and cross-repository
  compiler integration.
- This repository owns hardware-facing contracts, RTL, testbenches, synthesis,
  formal verification, and hardware receipts.

Apache-2.0 licensed. See [LICENSE](LICENSE).
