---
title: The reversibility taxonomy
---

# The reversibility taxonomy

The taxonomy is Unwind's core conceptual artifact. A tool call is placed on an **ordinal five-class scale (R0–R4)** and annotated with three orthogonal dimensions — **blast radius**, **externality**, and **reversibility half-life** — each derived as a function of *(tool, environment)*, never the tool alone.

## The R-scale

| Class | Name | Definition | Examples |
|---|---|---|---|
| **R0** | Nullipotent | No state change; safe to repeat. | `get_*`, `list_*`, `search_*`, `read_file` |
| **R1** | Self-reversible | The *same* tool restores exact prior state given captured pre-state. | `update_record`, `set_status`, `write_file` (prior content captured) |
| **R2** | Compensable | A *different* tool on the same server semantically undoes it; restores an acceptable approximation. | `create_page`→`delete_page`; `add_member`→`remove_member`; `grant`→`revoke` |
| **R3** | Mitigable only | No true inverse; partial mitigation only, and third parties may already have observed the effect. | `send_email`→retraction; `post_message`→delete (already read); `publish`→unpublish (already cached) |
| **R4** | Irreversible | No inverse and no meaningful mitigation. | payment capture, permanent delete with no trash, key destruction, physical actuation, immutable-ledger write |

### The scale is ordinal, with asymmetric loss

The classes are ordered, and the *distance* between them is meaningful — this is why `ReversibilityClass` is an `IntEnum` (`R0 < R1 < … < R4`), and why the [benchmark](../benchmark.md) reports **ordinal MAE** rather than plain accuracy.

The loss is deliberately **asymmetric**:

!!! danger "Misclassifying down is catastrophic; misclassifying up merely annoys"
    - Calling a true **R4** action an **R1** is a disaster — Unwind would auto-allow an irreversible payment believing it could take it back.
    - Calling a true **R1** action an **R4** is a minor annoyance — one needless confirmation prompt.

    Every metric in [ReversiBench](../benchmark.md) respects this asymmetry. The **headline** metric is the **Critical Error Rate**: the fraction of true-R4 actions classified as R2 or lower. When the classifier is uncertain, Unwind **degrades toward R4 and escalates** — it never rounds an uncertain action *down* into the auto-allow band.

### Fail-safe default

The default reversibility class in code is **R4**, not R0. An unknown tool, a failed classification, a timeout, or a crashed classifier all resolve to "escalate to the human." Unwind fails safe, never fails open.

## Orthogonal dimensions

A class alone is not enough. `delete_record(id=42)` and `delete_records(filter="*")` share a class but not a risk. Three dimensions run orthogonal to the R-scale.

### Blast radius

The **cardinality of affected entities**. Two calls of the same class can differ enormously in scope; blast radius captures that. Unwind estimates it from the call arguments and, where safe, a read-probe (a nullipotent query that counts what a mutation *would* touch, without touching it). An unbounded or `filter="*"` blast radius is always treated as high, and pushes an otherwise auto-allowed action toward escalation.

### Externality — the R2/R3 boundary

**Does the effect become visible to a third party?** This is precisely the line between R2 (compensable) and R3 (mitigable only).

- Deleting a draft page you created → **internal** → the create/delete inverse fully compensates → **R2**.
- Sending an email → **external** → you can send a retraction, but the recipient may already have read it → the effect has *escaped the controlled system* → **R3**.

Externality is why "compensable" and "mitigable" are different classes rather than one. A perfect inverse on your own server does not un-ring a bell that has already rung elsewhere.

### Reversibility half-life (a novel dimension)

!!! abstract "Novel contribution"
    Many actions are reversible only **within a time window**, after which the same action becomes irreversible. Email recall lasts ~30 seconds. Trash retention lasts ~30 days. A payment can be voided only *before settlement*. Reversibility is therefore **time-decaying**.

    No existing agent-safety framework models this. It falls straight out of taking compensation seriously, and it has a direct operational consequence: **the undo log has an expiry**. Every `UndoEntry` carries an `expires_at`; once the half-life elapses, its status flips to `EXPIRED` and `unwind undo` on it returns `could_not_undo` rather than a false success.

The half-life is a property of *(tool, environment)*. The same delete is recoverable for 30 days on a filesystem with trash and 0 seconds on one without. Unwind estimates the window during synthesis and reports predicted-vs-actual accuracy in the [benchmark](../benchmark.md).

### Environment-relativity — class is `f(tool, environment)`

!!! important "The same tool has different classes in different environments"
    `write_file` is **R1** on a git-backed tree (the prior blob is always recoverable) and **R4** on a versionless, backupless drive (the overwrite is final). The reversibility class is a function of *(tool, environment)*, never the tool alone.

Unwind models environments as declarative capability descriptors and **re-derives** the class per environment. The descriptor carries flags such as:

| Flag | Meaning |
|---|---|
| `versioned` | git-backed / object-versioning present |
| `has_trash` | soft-delete / recycle-bin available |
| `soft_delete` | tombstoning rather than hard delete |
| `retention_window_s` | how long deletes stay recoverable (feeds the half-life) |
| `supports_snapshot` | can pre-state be read before mutating? (gates R1) |
| `external_side_effects` | do actions leak to third parties by nature? |

```python
from unwind.types import EnvironmentDescriptor

git_backed = EnvironmentDescriptor(name="repo", versioned=True, supports_snapshot=True)
versionless = EnvironmentDescriptor(name="scratch", versioned=False, has_trash=False)
# The same write_file classifies as R1 against `git_backed`, R4 against `versionless`.
```

The benchmark measures **environment sensitivity** directly: the change in class assignment when the descriptor flips from git-backed to versionless. A classifier that ignores the environment scores badly here — correctly.

## Commit-point semantics

Adopting Blake Crosley's framing, the **commit point** is the moment an action crosses from reversible work into an irreversible side effect. *"Human approval after the commit point becomes incident response, not authorization."* Unwind's job is three-fold:

1. **Locate** the commit point automatically for an arbitrary third-party tool — the classification problem nothing else solves.
2. **Place confirmation strictly before it** — the human is asked while the action is still reversible, not after.
3. **Push it later wherever possible** — by capturing pre-state, Unwind can turn an action that would have been R4 into an R1 or R2. Pre-state capture is *how the commit point moves*.

This is the mechanism behind the [compensation synthesiser](compensation.md): capturing a snapshot before a mutation is what makes "self-reversible" reachable at all.

## How a class becomes a decision

The class, its confidence, blast radius, externality and half-life feed the [escalation policy](architecture.md), which emits one of four decisions:

| Decision | When |
|---|---|
| `auto_allow` | R0 reads — never touch the hot path |
| `auto_allow_logged` | Reversible (R1/R2) with a validated compensation and a confident classification |
| `elicit_confirmation` | R3/R4, high blast radius, or low confidence → ask the human via native elicitation |
| `block` | Refused by policy, or the `--passthrough-only` / panic path |

The confidence is calibrated on a held-out split so the threshold corresponds to a real target damage rate — see [ReversiBench](../benchmark.md).
