# EISA-H ZD Pair RTL v1 Review Receipt

Date: 2026-07-12

## Surface

- RTL: `rtl/eisa_h_sed16_zd_pair_v1.sv`
- Testbench: `tb/eisa_h/tb_sed16_zd_pair_v1.sv`
- Manifest: `spec/eisa_h/sedenion_zd_pair_rtl_v1.json`
- Gate: `scripts/gate_zd_pair_rtl.sh`

## Adversarial review

The initial review found no P0 and seven proof gaps: a self-referential basis
oracle, incomplete handshake evidence, a self-declared cycle count, incomplete
overflow boundaries, incomplete signedness coverage, artifact hashes absent
from the manifest, and a single narrow mutation.

The repaired surface uses a static 256-bit golden sign table, tests all 1,024
signed basis combinations, counts busy and latency from clock transitions,
exercises reset and start-during-busy behavior, covers positive and negative
threshold boundaries and precedence, binds RTL/testbench/vector hashes in the
manifest, replays deterministically, and rejects six mutation classes.

## Provider review

xAI/Grok 4.3 returned `NO MATHEMATICAL CONTENT TO REVIEW` for the RTL. This is
recorded as an attempted mandatory review, not promoted to PASS. The prior
software-oracle review remains the algebra review for the semantic contract.

## Claim boundary

The receipt supports Icarus Verilog RTL simulation for the bounded v1 domain.
It is not synthesis, formal equivalence, timing, power, area, FPGA, ASIC, or
silicon evidence.
