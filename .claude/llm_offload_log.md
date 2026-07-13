# LLM Offload Log

## 2026-07-12 - EISA-H ordered sedenion ZD-pair v1

- Target: `tools/eisa_h/zd_pair_oracle.py`
- Task: `math-review`
- Provider: xAI/Grok 4.3
- Outcome: PASS
- Finding: no algebraic error was found in the recursive Cayley-Dickson sign
  rule, XOR-indexed multiplication, exact-zero classification, or table
  fingerprint.
- Post-review hardening: pinned the v1 table hash independently, added ordered
  basis witnesses, recursive schema validation, mandatory vector coverage, and
  adversarial error-precedence cases.
- Evidence boundary: software-oracle contract only; no RTL or hardware claim.
- Raw local result: `/tmp/llm-offload-5Soit4/` (ephemeral).

## 2026-07-12 - Post-hardening rerun

- Target: final `tools/eisa_h/zd_pair_oracle.py`
- Task: `math-review`
- Provider: xAI/Grok 4.3
- Outcome: NO MATHEMATICAL CONTENT TO REVIEW
- Classification: the reviewer treated the final file as an executable
  definition anchored by SHA-256 rather than a separate derivation. The prior
  PASS remains the substantive algebra review; this rerun is not represented
  as a second PASS.
- Raw local result: `/tmp/llm-offload-WYHEHE/` (ephemeral).

## 2026-07-12 - EISA-H ZD-pair RTL v1

- Target: `rtl/eisa_h_sed16_zd_pair_v1.sv`
- Task: `math-review`
- Provider: xAI/Grok 4.3
- Outcome: NO MATHEMATICAL CONTENT TO REVIEW
- Classification: the provider found no separate derivation to review in the
  executable RTL. This is recorded as an attempted mandatory review, not PASS.
- Orthogonal technical review: internal adversarial agent found seven
  implementation-proof gaps; all were addressed before commit and re-audited.
- Evidence boundary: RTL simulation only. No synthesis, formal, FPGA, ASIC,
  timing, power, area, or silicon claim.
- Raw local result: `/tmp/llm-offload-gpnQJn/` (ephemeral).

## 2026-07-12 - EISA-H ZD-pair generic synthesis v1

- Target: `tools/eisa_h/check_basis_rom.py`
- Task: `math-review`
- Provider: xAI/Grok 4.3
- Outcome: NO MATHEMATICAL CONTENT TO REVIEW
- Classification: the provider treated the ROM/hash binding as executable
  verification rather than a separate derivation. This is recorded, not PASS.
- Orthogonal technical review: internal adversarial review examined ABI,
  toolchain identity, pass recipe, gate composition, determinism wording, and
  failure classification; all findings were repaired before commit.
- Evidence boundary: generic synthesis only; no post-synthesis equivalence,
  technology mapping, timing, power, physical area, FPGA, ASIC, or silicon.
- Raw local result: `/tmp/llm-offload-um7hOq/` (ephemeral).

## 2026-07-12 - EISA-H synthesis and Slurm dispatch review

- Target: synthesis commit range `07d1319..09737f6` plus the Slurm dispatch
  delta
- Task: adversarial code and evidence review
- Provider: Gemini 3.1 Pro
- Initial outcome: `READY_WITH_FIXES`
- Findings: `grep -c` could terminate the gate under `set -e`, and manifest
  mutation used brittle textual substitution.
- Resolution: repaired both findings; focused Gemini re-review returned
  `READY` with both findings closed and all five bounded claims supported.
- Degraded lenses: MiniMax `TIMEOUT`; Z.AI `TIMEOUT`; Kimi `BLOCKED` by depleted
  provider credit after an initial permission rejection. None is counted as a
  review pass or consensus.
- Independent launcher review: `NOT_READY` before repair, with eight dispatch
  findings covering SHA identity, collision safety, toolchain closure, CI
  routing, fixture coverage, stderr retention, blocked classification, and
  scheduler metadata validation. All were addressed before Slurm execution.
- Raw local results: `/tmp/sounio-review-gemini.log` and
  `/tmp/sounio-rereview-gemini.log` (ephemeral).

## 2026-07-13 - EISA-H post-synthesis simulation parity v1

- Target: `spec/eisa_h/sedenion_zd_pair_postsynth_v1.json`
- Task: `math-review`
- Provider: xAI/Grok 4.3
- Outcome: `NO MATHEMATICAL CONTENT TO REVIEW`
- Classification: the provider found no independent derivation in the
  executable receipt contract. This is recorded as an attempted mandatory
  review, not a pass.
- Independent technical review: initial verdict `NOT_READY`; it rejected the
  overbroad `BOUNDED_EXHAUSTIVE_V1` claim and identified inaccurate transaction
  accounting, unenforced simulator identity, overbroad mutation wording, and
  missing lightweight validator coverage. The contract was narrowed to signed
  basis exhaustiveness plus fixed v1 cases and all findings were addressed
  before the promotion run.
- Raw local result: `/tmp/llm-offload-F0cRyV/` (ephemeral).

## 2026-07-13 - EISA-H split formal obligations v1

- Targets: split Yosys surface/reset/step recipes, formal gates, Slurm artifact
  persistence, `spec/eisa_h/sedenion_zd_pair_formal_v1.json`, and
  `docs/reviews/2026-07-13-eisa-h-zd-formal-split-v1.md`.
- Mandatory math review: xAI/Grok 4.3 initially found that the gate could emit
  a pass marker before independent certificate replay. The gate was repaired
  to remain `BLOCKED` until the state-step certificate is pinned. A later
  math-review rerun returned `NO MATHEMATICAL CONTENT TO REVIEW`; it is recorded
  as an attempted review, not a second pass.
- Adversarial technical review: an internal review identified the fundamental
  mismatch between an output-only reset base and the full state invariant used
  by the step. The base was rebuilt over the complete 5,147-bit relation. It
  also requested mapping-identity hashes, strict DIMACS validation, stable
  timeout classification, and persisted Slurm artifacts; those repairs were
  implemented before commit. The final focused re-review returned `READY`
  after exact artifact-manifest coverage and 17 launcher-contract cases passed.
- External receipt review: xAI/Grok 4.3 found the final receipt internally
  consistent with the `async2sync` plus `sat -seq` methodology and confirmed
  the exact boundary: reset base certified, state step not certified, full
  equivalence not claimed.
- Required external-facing fan-out: DeepSeek returned `Insufficient Balance`;
  Gemini returned OpenRouter HTTP 402 insufficient credits. Neither is counted
  as a review pass.
- Evidence: reset-base CNF `fc1bff43...d6893cf` is independently certified by
  binary DRAT `8f457cd3...21d3b9`, replayed successfully on compute and login.
  State-step CNF `2804931a...caead0` timed out after 1,200 seconds and remains
  blocked.
- Raw local results: `/tmp/llm-offload-CdglbS/`,
  `/tmp/llm-offload-5xT9IB/`, `/tmp/llm-offload-m4EJke/`, and
  `/tmp/llm-offload-EP14cm/` (ephemeral).

## 2026-07-13 - EISA-H exact-relation miter geometry repair

- Targets: closure-support selection and structural proof, reset/state miter
  geometry guards, exact-relation CNF identities, schema-v3 receipt, and
  corrected external review prose.
- Internal adversarial review found that Yosys 0.33 expanded the documented
  5,147-cell target into a 5,179-cell miter dependency cone. The additional 32
  cells are the high halves of `lhs_nonzero_count` and `rhs_nonzero_count`.
  Solver scouting was stopped before using the old CNF.
- Repair: all 32 support cells are explicitly selected and proved before miter
  construction; their pre-proof and post-proof structural maps are pinned.
  Both miters now require 5,179 total `$equiv` cells decomposed into 32 proven
  support cells plus 5,147 unproven relation cells. The state trigger exposes
  exactly 5,147 pinned `cmp_*` outputs.
- Mandatory xAI math-review returned `NO MATHEMATICAL CONTENT TO REVIEW` after
  confirming the set-cardinality arithmetic. The subsequent xAI adversarial
  review correctly required independent replay for the new reset CNF and
  stronger support-cell evidence. The receipt retains certificate status as
  pending, and the gate now pins the 32-cell structural `A == B` map plus both
  miter decompositions. Its validator-staleness finding was also repaired.
- External-facing fan-out: xAI found the final receipt internally consistent
  and confirmed the exact 5,179-dependency/5,147-relation distinction.
  DeepSeek returned `Insufficient Balance`; Gemini returned OpenRouter HTTP
  402 insufficient credits. Neither provider failure is counted as a pass.
- Current exact CNFs: reset
  `ba2a9b0c064855380f4b81d729574f48dee62b16cc02c99f506da33d9d8b4eeb`
  was subsequently certified by CaDiCaL `rc=20` and binary DRAT
  `3694d958613a441d7426b367f46e88d285180cb32263116ac43dd2939b30a2d8`.
  `drat-trim` returned `rc=0` and `s VERIFIED` on Slurm job 5821 and again in
  the workspace. State step
  `0b5ccf1c1a025ff3fdbc5c4a0a1354d77995b2cd130d41672bceadbf28ac0a8d`
  is emitted with solver not yet run. Full equivalence remains unclaimed.
- Raw local results: `/tmp/llm-offload-raXVx3/`,
  `/tmp/llm-offload-7ZuEmH/`, `/tmp/llm-offload-u0HC1J/`, and
  `/tmp/llm-offload-AOQtBt/` (ephemeral). The final xAI receipt review
  acknowledged the reset certificate and kept state-step promotion pending;
  DeepSeek and Gemini repeated the same balance/credit failures.
