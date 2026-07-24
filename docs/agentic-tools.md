---
title: Agentic tools
---

# Agentic tools — the Unwind MCP surface

Unwind is not only a proxy that sits *behind* the agent. It is **itself an MCP server** that sits *alongside* the agent, exposing five tools the model can call directly:

`unwind.preview` · `unwind.undo` · `unwind.explain_risk` · `unwind.history` · `unwind.checkpoint`

!!! quote "Why this makes Unwind *agentic* rather than a filter"
    A filter decides *for* the agent and stays mute. Unwind instead gives the agent the vocabulary to **reason about the reversibility of its own actions and reverse them itself**. The model can ask "is this recoverable before I do it?" (`preview`), set a savepoint before a risky sequence (`checkpoint`), inspect what it has done (`history`), understand why something is dangerous (`explain_risk`), and take an action back (`undo`) — all without a human in the loop for the reversible majority. The human is reserved for the irreversible minority. That closed loop — the agent inspecting and undoing its own side effects — is the difference between a guardrail and a genuine reversibility layer.

The examples below show representative inputs and outputs. Field names follow the [core types](reference.md); concrete numbers are illustrative.

## `unwind.preview`

**Classify a call *before* it runs** — no side effect, purely predictive. This is the tool a careful agent calls before any mutation to decide whether it should proceed autonomously or ask.

=== "Input"

    ```json
    {
      "server": "gmail",
      "tool": "send_email",
      "args": { "to": "board@example.com", "subject": "Q3 numbers", "body": "…" }
    }
    ```

=== "Output"

    ```json
    {
      "rev_class": "R3",
      "class_name": "mitigable-only",
      "confidence": 0.88,
      "effect_verb": "send",
      "entity": "email",
      "externality": "external",
      "blast_radius": { "count": 1, "unbounded": false },
      "half_life_s": 30,
      "compensation": {
        "inverse_tool": null,
        "fidelity_grade": "acceptable-approximation",
        "residue": ["recipient may have already read the message"]
      },
      "decision": "elicit_confirmation",
      "rationale": "External send; no true inverse, only a ~30s recall window. Escalating."
    }
    ```

The agent now knows this is R3, that recall is possible only for ~30 seconds, and that Unwind will elicit confirmation. It can choose to ask the human proactively rather than be interrupted.

## `unwind.undo`

**Reverse the last *n* actions across every connected server, in reverse order** — the stack-unwinding operation Unwind is named for. Each reversed action reports its own graded outcome and residue; the tool never claims a blanket success.

=== "Input"

    ```json
    { "last": 4 }
    ```

=== "Output"

    ```json
    {
      "undone": [
        { "id": 6, "server": "sqlite",  "tool": "drop_table",   "outcome": "restored",                "fidelity": "exact",    "residue": [] },
        { "id": 7, "server": "notion",  "tool": "create_page",  "outcome": "restored",                "fidelity": "semantic", "residue": ["version counter bumped"] },
        { "id": 4, "server": "git",     "tool": "push --force", "outcome": "approximately_restored",  "fidelity": "semantic", "residue": ["ref-update webhook already fired"] },
        { "id": 5, "server": "gmail",   "tool": "send_email",   "outcome": "could_not_undo",          "fidelity": "failed",   "residue": ["recall window (30s) expired; recipient notified"] }
      ],
      "summary": "3 restored, 1 could not be undone (see reasons)."
    }
    ```

That last line — an honest `could_not_undo` with the reason — is the whole thesis. Unwind does not manufacture a false undo.

You can also target a specific entry (`{"id": 6}`) instead of the last *n*.

## `unwind.explain_risk`

**Explain, in plain language, why an action carries the class it does** — the reasoning behind a `preview`, for surfacing to a human or for the agent's own chain of thought.

=== "Input"

    ```json
    { "server": "filesystem", "tool": "write_file", "args": { "path": "/scratch/notes.md" } }
    ```

=== "Output"

    ```json
    {
      "rev_class": "R4",
      "explanation": "write_file is R1 on a git-backed or trash-enabled tree because the prior blob is recoverable. This environment (/scratch) is versionless with no trash, so the overwrite is final — the class re-derives to R4. Capturing pre-state first would move it back to R1.",
      "environment": { "name": "scratch", "versioned": false, "has_trash": false, "supports_snapshot": true },
      "how_to_make_reversible": "Enable pre-state capture, or point the server at a versioned path."
    }
    ```

Note the [environment-relativity](concepts/taxonomy.md#environment-relativity-class-is-ftool-environment): the same tool is explained differently depending on where it runs.

## `unwind.history`

**Inspect the durable undo log** — what has happened, what is still reversible, and when each entry's [half-life](concepts/taxonomy.md#reversibility-half-life-a-novel-dimension) expires.

=== "Input"

    ```json
    { "limit": 5, "status": "active" }
    ```

=== "Output"

    ```json
    {
      "entries": [
        { "id": 7, "server": "notion", "tool": "create_page", "rev_class": "R2", "status": "active", "fidelity": "semantic", "expires_at": null },
        { "id": 6, "server": "sqlite", "tool": "drop_table",  "rev_class": "R1", "status": "active", "fidelity": "exact",    "expires_at": null },
        { "id": 5, "server": "gmail",  "tool": "send_email",  "rev_class": "R3", "status": "active", "fidelity": "acceptable-approximation", "expires_at": 1753286700.0 }
      ]
    }
    ```

## `unwind.checkpoint`

**Set a named savepoint** so a later `undo` can roll the whole session back to a known-good state — the transactional bracket around a risky multi-step plan. The agent takes a checkpoint before a sequence it is unsure about, attempts the work, and unwinds to the checkpoint if it goes wrong.

=== "Input"

    ```json
    { "label": "before-migration" }
    ```

=== "Output"

    ```json
    {
      "checkpoint_id": "cp_01H…",
      "label": "before-migration",
      "created_at": 1753286400.0,
      "note": "Actions after this point can be reversed with unwind.undo --to-checkpoint before-migration (subject to per-action fidelity and half-life)."
    }
    ```

!!! warning "A checkpoint is not a magic snapshot"
    Rolling back to a checkpoint reverses each intervening action using its own compensation plan, so it inherits every action's [graded fidelity and residue](concepts/compensation.md). If one of those actions was R3/R4 or its half-life lapsed, the rollback reports that action as `could_not_undo` — a checkpoint never over-promises what the individual undos cannot deliver.

## Design note

These five tools are a **first-class product surface**, not a debug afterthought. They are what let the agent participate in its own oversight: previewing risk, bracketing work with checkpoints, and cleaning up after itself — escalating to a human only where the taxonomy says it genuinely must.
