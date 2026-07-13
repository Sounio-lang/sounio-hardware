# EISA-H ZD Pair State-Step Partition Design

Date: 2026-07-13

Status: **CONTROL CERTIFIED, THREE PARTITIONS PENDING**.

The monolithic exact state-step CNF timed out under two 600-second CaDiCaL
strategies. This design divides only its next-step consequent while retaining
the full 5,147-bit antecedent in every sub-obligation.

For the four pairwise-disjoint comparator sets `X`, prove independently:

```text
T and P5147(t) and not P_X(t+1) is UNSAT
```

Their counts are 2,048 latches, 1,024 accumulator bits, 2,048 product and
alias bits, and 27 control bits. The exact union contains 5,147 unique names
and hashes to the original comparator map
`855df0a4439e4840a21dac7843f8d07ca974026cf67e742561cd38e883f7ef35`.

The generated temporal drivers pin `-set-at 1 trigger 0`, which assumes the
complete relation at frame 1. Per-comparator `$assert` cells are added only for
the selected consequent, and the drivers pin `-prove-skip 1`, making them proof
targets only at frame 2. Initial state and shared inputs are arbitrary but
defined. No reachability, valid-domain, or signed-basis restriction is
introduced.

The generator consumes the current Yosys comparator map and rejects wrong
cardinality, duplicates, overlap, incomplete union, or hash drift. The surface
gate executes every structural recipe, pins each recipe and temporal-driver
hash, and mutation-checks every temporal flag. A certificate bundle is
acceptable only when it binds the full comparator map, partition map, recipe,
temporal driver, CNF, solver binary, proof, checker binary, and an independent
replay.

The decomposition does not establish state-step closure by itself. Aggregate
promotion remains blocked until every partition has a replayed UNSAT
certificate, or the monolithic exact CNF obtains one directly.

The 27-bit control partition is the first certified sub-obligation. CaDiCaL
1.7.3 returned UNSAT for CNF `f035d87612a0be2c198674d6edc8a52640b1d916d3d13a171136646e6fefd839`
in Slurm job 5825 and produced a 152,493,236-byte binary DRAT proof. `drat-trim`
verified it in that run and independently replayed the same CNF, proof, and
checker identities on a different node in job 5826. Job 5827 then reemitted
the CNF through the committed partition-emission gate at source
`cd340b0843f0ced9fbb7886f0c8ac1c2a35ce45c`; the decompressed output was bit
identical. The aggregate status is therefore exactly one of four certified,
not state-step closure.

The monolithic exact CNF remained UNKNOWN after a 7,200-second `--unsat` run
in job 5823. Its 4,278,340,897-byte partial DRAT stream was not retained and
was not checked, so it carries no certificate claim. This result motivates the
partitioned path but does not count as evidence for or against equivalence.

The durable emission path runs through
`scripts/slurm/run_zd_pair_formal_partition_emit.sh`. It transports the pinned
commit and Yosys toolchain, executes all four temporal drivers, requires the
complete-CNF marker to precede the solver outcome, validates each DIMACS file,
and returns only an allowlisted, fully checksummed artifact tree. A successful
emission run still carries no UNSAT claim.
