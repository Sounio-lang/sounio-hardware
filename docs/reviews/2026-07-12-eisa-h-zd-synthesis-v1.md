# EISA-H ZD Pair Generic Synthesis v1 Review Receipt

Date: 2026-07-12

## Surface

- Packed-bus RTL: `rtl/eisa_h_sed16_zd_pair_v1.sv`
- Basis binding: `tools/eisa_h/check_basis_rom.py`
- Yosys recipe: `scripts/yosys/synth_zd_pair_v1.ys`
- Manifest: `spec/eisa_h/sedenion_zd_pair_synth_v1.json`
- Gate: `scripts/gate_zd_pair_synth.sh`
- Slurm launcher: `scripts/slurm/run_zd_pair_synth.sh`
- Return validator: `tools/eisa_h/validate_slurm_result.py`

## Result

Yosys 0.33 lowers the design to a deterministic generic-cell netlist with
38,133 cells, 4,122 sequential cells, no memories, no behavioral processes,
no unknown cell/net constants, and zero `check` problems. Two same-tool,
same-host runs produce byte-identical statistics and netlist JSON artifacts.

The ABI is a pair of signed 1,024-bit inputs and one signed 1,024-bit output,
each containing sixteen signed two's-complement 64-bit lanes. Lane zero occupies
bits 63:0 and lane `i` occupies `(64*i)+:64`. Reset is asynchronous active-low;
transactions are accepted on a rising edge when `ready` is asserted.

## Adversarial review

The review found no P0 and six proof gaps: incomplete ABI metadata, unpinned
tool identity, missing local RTL-gate dependency, an inline unversioned Yosys
recipe, overbroad determinism wording, and regressions mislabeled as
infrastructure blockers. The repaired surface pins Ubuntu 24.04/Yosys 0.33,
versions and hashes the recipe, executes the RTL gate first, narrows the replay
claim, and distinguishes tool absence/timeout from synthesis failure.

## Provider review

xAI/Grok 4.3 returned `NO MATHEMATICAL CONTENT TO REVIEW` for the ROM/hash
checker. This is recorded as an attempted mandatory review, not promoted to
PASS. The v1 software-oracle review remains the substantive algebra review.

Gemini 3.1 Pro independently reviewed the synthesis and dispatch diff. It
initially returned `READY_WITH_FIXES`, identifying a `grep -c`/`set -e`
failure path and brittle text-based JSON mutations. Both were repaired with an
explicit no-match path and structured JSON mutation; the focused re-review
returned `READY` and marked both findings closed.

The other attempted orthogonal lenses did not produce valid reviews: MiniMax
and Z.AI timed out, while Kimi was blocked by depleted provider credit after a
permission-rejected first attempt. These outcomes are provider degradation,
not consensus and not additional passes.

An independent clean-context launcher review found eight dispatch-proof gaps:
commit TOCTOU, output collisions, incomplete shared-library closure, exhaustive
GitHub execution, missing launcher fixtures, uncaptured `srun` stderr, ambiguous
worker `rc=42`, and weak job/node validation. The repaired launcher captures one
source SHA, creates output directories atomically, bundles and verifies the
Linux x86_64 glibc dependency closure, pins the node's absolute ELF loader by
hash, retains and hashes stderr, validates returned files
and identities, and classifies worker `rc=42` as `BLOCKED`. GitHub CI now runs
only bounded contract checks; exhaustive RTL and double synthesis are Slurm
workloads.

## Claim boundary

The reference receipt proves generic synthesis and same-tool/same-host replay.
A promoted Slurm receipt additionally requires a numeric job ID, worker node,
exact source commit, repository/toolchain manifest identities, and returned-log
checksums. Neither proves post-synthesis functional equivalence, technology
mapping, timing, power, physical area, FPGA behavior, ASIC behavior, or silicon
behavior.

## First cluster execution

Slurm job `5764` ran source `1fcf806bee6610747059c1b624bb630c465e9a29`
on `gpuorangefs-multi-r740-proxmox` and returned gate RC `0`. The gate log hash
was `5391db6dc122ae078d80dac80d2a75165d038727ac8e6f8f01bca11284a010b6`;
the empty scheduler-stderr hash was
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
It reproduced 38,133 cells, 4,122 sequential cells, deterministic replay, and
four rejected mutations. Submission exposed one launcher-only defect: the
artifact parent had to exist. The launcher and fixture were then hardened to
create and test nested output parents before the final-source rerun.
