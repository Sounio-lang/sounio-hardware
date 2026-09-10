# PIREUS Measurement Stratum: Ownership and Boundary

Date: 2026-09-10

Status: **BOUNDARY DECLARED, CONTRACT NOT YET IMPLEMENTED**.

## Scope of this document

PIREUS is the ontology and novel-operator genesis engine of Sounio. It lives in
`Sounio-lang/sounio`. This document does not move it. It declares which single
stratum of PIREUS this repository owns, and why the remainder must not migrate.

## Why PIREUS does not move here

The admission boundary of PIREUS is `tools/pireus/continuity/admission.sio`,
compiled through `bin/souc`. Three of its five continuity test suites
(`test_admission.py`, `test_cycle.py`, `test_material_controls.py`) refuse to
run without that compiled engine as an argument; only `test_pilot.py` (7 tests)
and `test_tokenized_cycle.py` (3 tests) are self-contained Python. The ontology
it queries is a TripleStore/SPARQL surface over `stdlib/`, and its proof
obligations are 97 Lean 4 files.

Migrating PIREUS here would make this repository depend on the Sounio compiler,
standard library, triple store, and Lean proof corpus. That inverts the
ownership clause stated in this repository's `README.md` and `AGENTS.md`, under
which `Sounio-lang/sounio` owns language-level semantics and this repository
owns hardware-facing contracts and receipts. The dependency must continue to
point from the language repository toward this one.

## What this repository owns

One stratum: **material parity measurement**. PIREUS materializes an admitted
proposal onto a target and compares a candidate against a control. The act of
measuring that comparison, and of deciding whether the measurement is
admissible evidence, is hardware-facing. It belongs here, expressed in the same
form as every other obligation in this repository: an executable contract with
a software oracle, adversarial vectors, mutation rejection, and a deterministic
receipt.

The planned contract identifier is `eisa_h.pireus_material_parity.v1`. PIREUS
consumes it as an external oracle. It carries no semantics of admission, no
ontology, and no authority over what a valid proposal is.

## Boundary of claim

This document declares an intended contract. It does not claim the contract
exists, that any measurement has been reproduced here, or that any PIREUS
milestone advances because of it. No performance, novelty, or promotion claim
is made or transferred by this boundary.

## Recorded upstream state at the time of this declaration

Observed in `Sounio-lang/sounio` on 2026-09-10:

- PR 2434 (canonical plan) is **merged** into `main`. This is why `main` carries
  `docs/roadmap/PIREUS_CONTINUITY_PLAN.md` and two continuity JSON files.
- PR 2437 (ontology and typed lowering continuity) is **closed and not merged**.
- PR 2439 (proposal pipeline) is open and draft, with base branch
  `codex/pireus-integration-20260906` -- the head of the closed PR 2437.
  It therefore has no open path to `main`. It carries 4,099 changed files and
  212 commits.
- CI run 34491511493, the CPU36 source qualification for PR 2439, has remained
  in `queued` state since 2026-09-10T14:48:41Z; its
  `Madaros Current-Source f64 Lowering` job was never picked up by a runner.
  The qualification described upstream as "not yet qualified" is stalled, not
  pending.
- Slurm job 11991 measured gen2 self-compilation at 5,131.146 s with maximum
  child RSS 27,294,756 KiB (approximately 26.0 GiB).

These are observations of upstream state. They are recorded because they bound
what this repository can verify locally, and for no other purpose.
