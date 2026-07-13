# EISA-H ZD Pair Post-Synthesis Simulation Parity v1

Date: 2026-07-13

## Surface

- Source RTL: `rtl/eisa_h_sed16_zd_pair_v1.sv`
- Common testbench: `tb/eisa_h/tb_sed16_zd_pair_v1.sv`
- Generated netlist: deterministic Yosys 0.33 Verilog
- Contract: `spec/eisa_h/sedenion_zd_pair_postsynth_v1.json`
- Validator: `tools/eisa_h/validate_postsynth_receipt.py`
- Worker gate: `scripts/gate_zd_pair_synth.sh`

## Exact claim

The gate replays the common testbench against the generated post-synthesis
Verilog netlist. It covers all 1,024 ordered signed one-basis-by-one-basis
products, fifteen fixed v1 cases, and one accepted transaction aborted by
reset. The receipt distinguishes 1,039 completed transactions from 1,040
accepted transactions.

The claim is
`SIGNED_BASIS_EXHAUSTIVE_PLUS_FIXED_V1_CASES_SIMULATION_PARITY`. It is not
exhaustive over the complete v1 operand domain: v1 has 512 nonzero operands and
262,144 ordered nonzero operand pairs. It is also not formal equivalence,
technology mapping, timing, power, FPGA, ASIC, or silicon evidence.

## Discovery runs

Job `5767` reached the first post-synthesis simulation but timed out at the
ten-minute allocation boundary. Job `5773` used a thirty-minute allocation and
was cancelled as obsolete at 16:25: its first simulation was still running, so
an identical deterministic replay could no longer fit in the remaining time.
Both jobs compiled the generated netlist successfully and recovered candidate
netlist hash
`c0ed60eb8fdc895a74b5307cab260205e166f1025c73adb5c0e9aaf6229d2f5c`.

The production gate therefore uses focused 25-minute limits for each simulation
and a one-hour Slurm allocation. This cost is part of the evidence surface, not
hidden CI latency.

Job `5785` completed the primary post-synthesis simulation, proving the expected
transaction accounting, but exposed an Icarus operational line containing the
absolute worker path and `$finish` timestamp. The gate now requires and removes
exactly one structurally matched Icarus finish line before hashing the scientific
receipt; unexpected or additional chatter fails the gate. Raw-log hashes remain
in the final receipt for custody.

## Review

xAI/Grok 4.3 returned `NO MATHEMATICAL CONTENT TO REVIEW` for the executable
manifest; this is an attempted mandatory review, not a pass. Independent
clean-context review rejected the initial `BOUNDED_EXHAUSTIVE_V1` wording,
corrected transaction accounting, required Icarus 12.0 enforcement, narrowed
the mutation claim to receipt identity, and added the validator to lightweight
CI. Those findings were incorporated before promotion.
