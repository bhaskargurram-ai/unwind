# WITNESS — reversibility by discharged refutation

`WITNESS` (Witnessed Irreversibility Testing via Discharged Refutation) is
Unwind's research-grade reversibility classifier. It decides whether an action
can be undone **not by aggregating a model's beliefs** (self-consistency) **nor by
trusting its arguments** (debate), but by placing the **burden of proof on
reversibility** and **discharging it operationally**.

Try it live:

```bash
unwind classify --witness -- npx -y @modelcontextprotocol/server-filesystem /path
```

## Why belief-averaging fails

The catastrophic error is calling a truly irreversible (R4) action reversible.
This happens on *lexically benign* actions:

- a message **send** whose target row is perfectly restorable but whose delivery
  a third party already observed;
- a **payment** that is voidable inside a settlement window and irreversible
  after;
- a **create** whose only inverse needs a server-assigned id the create never
  returns.

A model agrees with itself — confidently and wrongly — on all three, because its
confidence is uncorrelated with correctness on *systematic* errors.

## The mechanism

1. **Typed irrefutation grammar.** An adversarial proposer enumerates *typed,
   checkable* irreversibility witnesses from a closed grammar — never free-text
   doubt:
    - `EXTERNALITY(channel)` — the effect is observable on a read channel outside
      the target entity (an outbox, audit feed, read-receipt).
    - `HALF_LIFE(window)` — the inverse is valid only within a window; after
      settlement/expiry no inverse exists.
    - `LOST_INVERSE_PARAM(field)` — the inverse needs an id the forward call never
      returns.
    - `MISSING_SNAPSHOT_CASCADE` — pre-state cannot be captured, or the mutation
      cascades beyond the inverse.

2. **Discharged-refutation voter.** Each witness is `CONFIRMED`/`REFUTED`/
   `UNTESTABLE` by a **deterministic** discharge function — a schema-graph check
   or a real/paired-environment execution — **never the model's assertion**.

3. **Monotone hardening.** The worst-case *confirmed* witness can only **raise**
   the class, never lower it. Two consequences follow by construction:
    - WITNESS **cannot manufacture a false undo** (the failure mode that recreates
      the auto-approve reflex Unwind exists to cure); and
    - its Critical Error Rate is **no worse than** the ensemble baseline it
      augments.

## Safety invariants (pinned by tests)

| # | Invariant |
|---|-----------|
| I1 | Monotone hardening — the witness voter never softens the class. |
| I2 | The environment descriptor is a hard ceiling. |
| I3 | Fidelity is **measured**, never asserted from a lexical score. |
| I4 | Any probe exception / missing inverse / suspected-untestable witness fails safe → escalate. |
| I5 | A witness is confirmed only by discharge, never by the proposer's assertion. |

## Executable discharge

Where a tool has a sandbox analog, WITNESS confirms witnesses by *executing*
probes rather than reasoning about them:

- **Environment-relativity** — run `forward + inverse` on the real backend and a
  capability-paired counterfactual (git-backed vs versionless); the *differential*
  residual measures that the same overwrite is R4 in one environment and R1 in the
  other. This is a property of the real backends, not any label.
- **Externality** — read a separate observation channel before/after with a
  forward-only control; a surviving footprint confirms the effect was observed.
- **Half-life** — advance the reversibility clock past the window and re-run the
  inverse; if it no longer round-trips, the same tool flips R2→R4.

WITNESS was designed by an adversarial panel of scientist-agents and is described
in the accompanying paper.
