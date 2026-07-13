# EISA-H ZD Pair State-Step Partition Design

Date: 2026-07-13

Status: **GEOMETRY VALIDATED, CERTIFICATES ABSENT**.

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
