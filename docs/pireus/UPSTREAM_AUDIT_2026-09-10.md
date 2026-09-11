# PIREUS Upstream Audit, 2026-09-10

Date: 2026-09-10

Status: **OBSERVATIONS RECORDED, NOTHING PROVEN HERE**.

## Why this file exists in this repository

This repository is preparing a measurement contract that PIREUS would consume as
an external oracle. Two static audits of `Sounio-lang/sounio` were run before
writing it, and both returned findings that change what that contract should be.
Recording them here first keeps the contract from inheriting premises the audits
removed.

These are observations about an upstream repository. Nothing here is a claim of
this repository, and nothing upstream is modified by recording it. Both audits
were read-only and static: no gate, benchmark, or proof was executed. Where a
finding could not be decided from the files, it is marked as a gap rather than
resolved.

## 1. The measurement stratum is not portable

The earlier boundary document assumed the material-parity stratum could migrate.
The coupling audit shows it cannot, and the reason is not the compiler.

The real gate set is 76 `scripts/ci/pireus_*`, not the 11 that
`scripts/ci/pireus_*_gate.sh` matches. Of those 76:

| Coupling | Count |
| --- | --- |
| Invoke `bin/souc` | 35 |
| Depend on the Loom Guardian native runtime | 62 |
| Pin `stdlib/hardware/pireus/*.sio` by hash | 45 |
| Depend on commit history (`git show <commit>:<path>`) | 45 |
| Genuinely self-contained | 2 |

The dominant coupling is the Loom Guardian, not `souc`. Gates named
"material parity" do not call the compiler, but each execution is authorised by
a policy frame passed to `sounio-loom-language-authority-runtime`, with
`stdlib/coordination/loom_language_authority.sio` pinned by hash. Without the
Guardian they fail closed.

Files that could migrate without inverting the dependency: **24 of roughly
5,500**, about 0.4 percent. Exactly one gate runs today against no Sounio
artifact at all.

The operative consequence: moving the 17 C++/CUDA/Futhark harnesses without the
gates that authorise them would deliver code stripped of the mechanism that
gives it evidentiary value. The harnesses are inputs, not the substance.

**What this repository should build instead** is a native contract in the form
`eisa_h.sedenion_zd_pair.v1` already uses -- schema-checked JSON receipts,
adversarial vectors, mutation rejection, deterministic replay -- with those 24
files as versioned input vectors. That is a rewrite of the authorisation
mechanism, not a port of it.

A separate observation, outside the hardware question: `tools/pireus/continuity/`
is not PIREUS hardware. Its `runtime/` subtree is LLM serving infrastructure and
`validation/` is largely infrastructure ticket receipts. It is a distinct
subsystem and its repository placement is a separate decision.

## 2. The M4 `NO_GAIN` result is largely an artefact of its own design

Upstream records milestone M4 as `PASS_CANARY_NO_GAIN`. The audit finds the
pipeline conclusion sound and the promotion conclusion uninformative.

Measured across three campaigns: 34 native gain decisions, 34 `NO_GAIN`, 0
eligible, 136 candidate-node-control comparisons. The largest median gain ever
measured is **+0.772 percent**, which is 15.4 percent of the 5 percent promotion
threshold. No comparison reached 1 percent.

The decisive finding is that every admitted proposal carries the same
`tensor_sha256`. Admission reconstructs the 4,096 coefficients and refuses any
plan whose tensor differs from the canonical Cayley-Dickson one. The admissible
grammar is therefore, by construction, a semantically identical scheduling space
-- lane permutation, AoS/SoA, direct load versus shuffle, unroll. It contains no
algorithmic freedom.

Total measured dynamic range over 33 sampled plans is +/-0.94 percent against a
5 percent threshold. A promotion criterion an order of magnitude above the entire
achievable variance is not reachable by design. Upstream contains no minimum
detectable effect calculation, no power analysis, and no justification of why 5
percent is the right number for this grammar. That is the central methodological
gap.

Three findings compound it:

- **Mode collapse.** In the eight real-canary proposals, `lane_stride`, `layout`
  and `unroll` are frozen across all eight; three of five knobs never varied,
  and four points of 2,560 were explored. One later candidate is byte-identical
  to the control, same `ptx_sha256`: the model re-proposed the control.
- **Noise floor.** Null candidates -- PTX byte-identical to a control --
  measured median "gains" up to +0.4868 percent, with a median 95 percent
  interval width of 0.93 percentage points. Ranking between candidates at the
  observed effect sizes is not resolvable above that.
- **Undocumented deviation.** The canonical plan requires a fixed control that is
  the best existing lowering. The implementation builds controls from the
  proposal template defaults. The only occurrence of that requirement anywhere
  upstream is the plan sentence itself.

Instrumentation is adequate for a 5 percent threshold and insufficient for the
0.1 to 0.9 percent effects that actually exist.

The audit explicitly does not find fraud or post-hoc adjustment. Method and
threshold are frozen before measurement, and the plan states that a correct
cycle may conclude without gain and that criteria must not be adjusted to
fabricate success. That discipline is real and verifiable in the files. The
problem is calibration, not integrity.

External review of the statistical design consists of the string `CLEAR` in two
reviewer files. That is not a review.

## 3. M5 has mathematics but no integration

Admission refuses any proposal whose kind is not `1` (lowering). There is no
schema, parser, or transport for the 4,096 proposed coefficients an integer
bilinear operator would need; no equivalence classifier, since admission today
reconstructs a tensor only to reject divergence from the canonical constant; and
bit-exact material parity is inapplicable to a novel operator by definition, with
no substitute acceptance criterion specified.

A substantial separate body of operator-genesis work does exist upstream, with
executable stdlib and a green qualification job. The audit found no cross
reference between it and the continuity cycle. The mathematics may be in place;
the integration is not. Whether that disconnection is intentional is not stated
anywhere upstream, and the audit does not resolve it.

## Boundary of claim

No performance, novelty, promotion, or correctness claim is made or transferred
by this document. It records what two static audits observed, including where
they could not decide. Any obligation upstream -- V13 and V14 formal parity
among them -- remains exactly as open as it was before this file existed.

## Addendum: the atlas is independently reproduced, and M5's classifier now exists

The audit reported that M5 has mathematics upstream but no integration, and that
one of the six missing pieces is an equivalence classifier: admission today
reconstructs a tensor only to reject divergence from the canonical constant,
where M5 needs the opposite -- accept a novel tensor and locate it.

That piece is now built and verified, as `eisa_h.pireus_operator_atlas.v1`.

Every count the upstream contract declares was reproduced from arithmetic over
`F2^4`, by an implementation that reads no upstream receipt and trusts no
upstream number:

| Declared upstream | Reproduced |
| --- | --- |
| 65,536 bilinear matrices in 1,024 gauge classes of 64 | yes |
| alternating subspace of dimension 6 | yes |
| `Q_B(x) = x^T B x` is the complete class invariant, ten bits | yes |
| bilinear-plus-coboundary span of dimension 21 | yes |
| `|GL(4,2)| = 20,160`, 40,320 candidate actions | yes |
| 168 admitted without operand exchange, 168 with, 336 total | yes |
| the admitted affine action partitions 1,024 codes into 32 classes | yes |
| the diagonal v1 grammar reaches exactly four of them | yes |

The upstream numbers are correct. That is a finding in their favour, and it was
worth establishing independently rather than assuming.

The operative consequence for M5 is the last row. The v1 lowering grammar
reaches four affine classes; the declared equivalence has thirty-two.
**Twenty-eight affine classes are unreached by anything PIREUS has proposed so
far.** That is where an operator search would have room the lowering grammar
does not, and it is the concrete sense in which M4's `NO_GAIN` is a statement
about the search space rather than about the model.

Two disciplines are preserved by construction. The classifier takes a
*construction code*, not a tensor: the tensor is derived, so the upstream rule
that no tensor or hash is accepted from a proposer survives unchanged. And
locating a construction in the atlas establishes its equivalence class and
nothing else -- the contract refuses to establish scientific novelty,
performance or material realisability, and the gate prints
`novelty=NOT_ESTABLISHED` on every run.

This does not integrate M5. It supplies one of its six missing pieces, verified.
