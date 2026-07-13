# EISA-H ZD Pair Exact-Relation Formal Receipt

Date: 2026-07-13

Status: **PARTIAL, GEOMETRY REPAIRED**. The exact 5,147-bit reset-base CNF
is UNSAT in Yosys and awaits independent certificate replay. The exact
state-step CNF has been emitted but has not yet been solved. Full formal
equivalence is not claimed.

## Proof surface

The source RTL and synthesized design are compared under a synchronous Yosys
model: `async2sync` removes the asynchronous-reset cell semantics, and each
`sat -seq` step represents one shared positive-edge transition. Top-level clock
waveform equivalence, timing, and silicon behavior are outside this claim.

The executable selection gate identifies:

- 1,042 public comparison bits;
- 4,122 state-relation bits;
- 5,147 bits in their union, accounting for 17 overlapping bits.

The maps remain pinned as:

```text
public a01c87792b972a115ebd57836a4eb2f1d5d7c11014ae8d4adcef88870fba5123
state  36255aaf229111de447a2f6f4245c011a7847a599c7d9f98cc34ae479b11b2a7
proof  57f65e8af872f8dc4c45282f536041bd644e0dd8c5f1ed052cf533bd7cf3df79
```

## Closure-cutpoint repair

Yosys 0.33 `equiv_miter` expands the selected cone. In the original recipe it
added 32 unselected `$equiv` cutpoints: bits `[31:16]` of
`lhs_nonzero_count` and `rhs_nonzero_count`. Consequently, the historical
state-step trigger represented 5,179 comparisons rather than the documented
5,147-bit relation.

The repaired miter therefore contains 5,179 `$equiv` cells: 5,147 unproven
target-relation cells plus 32 proven support cells. **5,179 is dependency-cone
geometry, not relation width.**

The repair selects those 32 cells explicitly, pins their pre-proof map as
`0ca975a011e8f5aa02da6c9b283feddd1d23cb924275f2dce218d2d8421f5cbe`,
and discharges all of them with `equiv_simple -short -seq 1` before building
the miter. After that proof, each support cell has structurally identical `A`
and `B`; the normalized structural map is
`e2b7b57ba90618d8d0ec407fdd2598d255de6880f4b5a428502e7c7fca99a112`.
Proven support cells are omitted from the trigger. The repaired miter therefore
exposes exactly 5,147 `cmp_*` outputs, whose sorted-name map is
`855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35`.

This distinction is executable: the surface gate requires 32 extras found and
32 proved, while the state-step gate requires exactly 5,147 comparators with
the pinned map.

## Current exact reset base

This obligation constrains `rst_n=0` at step 1 and `rst_n=1` at step 2, with
shared defined inputs, then proves the exact 5,147-bit relation at step 2.

```text
CNF SHA256  ba2a9b0c064855380f4b81d729574f48dee62b16cc02c99f506da33d9d8b4eeb
CNF bytes   366667787
CNF header  p cnf 3304588 8926674
Yosys SAT   UNSAT (SUCCESS)
certificate PENDING_INDEPENDENT_REPLAY
```

The current CNF must receive a new solver proof and independent replay before
it is promoted as the canonical reset certificate.

## Current exact state step

This obligation assumes all 5,147 exact comparison bits at step `t` and asks
whether the same relation holds at step `t+1` for shared defined inputs.

```text
CNF SHA256  0b5ccf1c1a025ff3fdbc5c4a0a1354d77995b2cd130d41672bceadbf28ac0a8d
CNF bytes   340131200
CNF header  p cnf 3052420 8276177
cmp bits    5147
cmp map     855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35
solver      NOT_RUN
certificate NONE
```

## Historical expanded-miter evidence

The previous reset CNF
`fc1bff43ba18322ae2677c7a9b0391ce4d4eefcfb2b29d9e55fff66c3d6893cf`
proved a 5,179-comparison superset UNSAT. Its binary DRAT
`8f457cd35957cee266442b602af656711a1563dc930d9e292c8142094221d3b9`
was independently verified twice. It remains valid historical evidence and
implies the 5,147-bit reset conclusion, but it is not the certificate for the
new exact-relation CNF.

The previous state-step CNF
`2804931a99b458db7c3cee99fec2b7829206776d7e2e2b74d4c6451876caead0`
encoded the expanded 5,179-comparison antecedent and consequent. It timed out
after 1,200 seconds with `UNKNOWN`; its incomplete 7.1 GiB trace was never a
certificate. It must not be described as an exact `P5147 -> P5147` attempt.

Historical Slurm job `5817` ran on
`gpuorangefs-multi-r740-proxmox`. The accounting daemon was unavailable, but
the preserved logs record the exact solver statistics and cancellation after
artifact capture.

## Claim boundary

Established by executable local gates: the 32 automatic cutpoints are proved,
the repaired trigger is exactly the pinned 5,147-bit relation, and both exact
CNFs are deterministically emitted.

Not yet independently certified: the current exact reset CNF and the exact
state-step CNF. Consequently, temporal source-to-synthesized equivalence,
arbitrary-initial-state equivalence, timing equivalence, and silicon
equivalence remain unclaimed.

The next run must certify the current reset CNF first, then scout and solve the
current state-step CNF. Promotion requires solver `rc=20`, a completed proof
hash, and `drat-trim` returning both `rc=0` and exactly `s VERIFIED` for each
exact CNF.
