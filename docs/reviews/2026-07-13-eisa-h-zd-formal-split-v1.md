# EISA-H ZD Pair Split Formal Receipt

Date: 2026-07-13

Status: **PARTIAL**. The reset-base obligation is certified UNSAT. The
state-step obligation timed out without a replayable certificate. Full formal
equivalence is not claimed.

## Proof surface

The source RTL and synthesized design are compared under a synchronous Yosys
model: `async2sync` removes the asynchronous-reset cell semantics, and each
`sat -seq` step represents one shared positive-edge transition. Top-level clock
waveform equivalence, timing, and silicon behavior are outside this claim.

The executable selection gate identifies:

- 1,042 public comparison bits: `ready`, `busy`, `done`, `classification`,
  `error_code`, `product_is_zero`, `product_flat`, and `mac_cycles`;
- 4,122 state-relation bits: 1,024 each for `lhs_latched`, `rhs_latched`,
  `accumulator`, and `product`, plus 26 control/status bits;
- 5,147 bits in the union, accounting for 17 bits shared by the public and
  state sets.

Counts alone are not authority. The sorted compared-pair maps are pinned as:

```text
public a01c87792b972a115ebd57836a4eb2f1d5d7c11014ae8d4adcef88870fba5123
state  36255aaf229111de447a2f6f4245c011a7847a599c7d9f98cc34ae479b11b2a7
union  57f65e8af872f8dc4c45282f536041bd644e0dd8c5f1ed052cf533bd7cf3df79
```

## Reset base: certified

This obligation constrains `rst_n=0` at step 1 and `rst_n=1` at step 2,
with shared defined inputs, then proves the complete 5,147-bit relation at
step 2. The earlier 1,042-output-only base is explicitly excluded because it
does not establish the invariant used by the closure step.

```text
CNF SHA256  fc1bff43ba18322ae2677c7a9b0391ce4d4eefcfb2b29d9e55fff66c3d6893cf
CNF bytes   367065611
CNF header  p cnf 3308204 8936338
solver      CaDiCaL 1.7.3
result      UNSATISFIABLE (rc=20, 6.70s, 1191.59 MiB max RSS)
DRAT bytes  53768280
DRAT SHA256 8f457cd35957cee266442b602af656711a1563dc930d9e292c8142094221d3b9
```

`drat-trim` returned `rc=0` and `s VERIFIED` on the compute node, then did so
again after the proof was copied to the login node. The checker reported a
541,706/8,936,338-clause core, one retained lemma out of 2,977,906, and zero
RAT lemmas.

## State step: timeout

This obligation assumes the complete relation at step `t` and asks whether
the same relation must hold at step `t+1` for shared defined inputs.

```text
CNF SHA256  2804931a99b458db7c3cee99fec2b7829206776d7e2e2b74d4c6451876caead0
CNF bytes   340148864
CNF header  p cnf 3052484 8276561
solver      CaDiCaL 1.7.3
limit       1200s
result      UNKNOWN (3,865,544 conflicts, 1562.51 MiB max RSS)
```

The solver produced a 7.1 GiB partial DRAT trace with SHA
`6dd520a6925e985588683e8ac1f530346c43e832b1396580ca34e17d776044d5`.
It was not replayed and is not a certificate because the solver returned
`UNKNOWN`.

## Slurm receipt

Job `5817` ran on `gpuorangefs-multi-r740-proxmox`, partition `all`, with 8
CPUs and 64 GiB. It started at `2026-07-13T04:40:16Z` and was intentionally
cancelled after preserving the completed base proof at
`2026-07-13T05:03:07Z`. The accounting daemon was unavailable; `scontrol`
reported runtime `00:22:51` and final state `CANCELLED`.

Tool identities:

```text
CaDiCaL  7b73df0a6d9cf3c751a1948300e5baff8e82c4d39bcd88f0c063b5f5cfb8b33e
drat-trim 92f0aa9575ed519d66a99b8b1b3dde6ece4618ae4c202a3a4b200265dda0aa7a
```

## Claim boundary

Certified: the 5,147-bit relation holds after the specified reset sequence for
the exact reset-base CNF above.

Not certified: preservation of that relation for an arbitrary next step.
Consequently, temporal source-to-synthesized equivalence, arbitrary-initial-
state equivalence, timing equivalence, and silicon equivalence remain
unclaimed.

The next bounded run should use at least a two-hour allocation, 16 GiB of RAM,
100 GiB of node-local storage, binary DRAT, and a proof-producing solver
portfolio. Promotion requires `drat-trim` to return both `rc=0` and
`s VERIFIED` for the exact state-step CNF.
