---
title: Twitter / X thread (draft)
---

# Twitter / X thread (draft)

!!! warning "Launch-day draft — not published yet"
    This is a **draft** thread. No hype, no fabricated numbers. Lead with the thesis, show the demo, stay honest about limits. Attach the 20-second demo GIF to tweet 2. Numbers stay TBD until `make results`.

---

**1/**
Human oversight of AI agents is failing — and not for the reason people think.

It's failing because approval prompts are all identical. "Allow this tool call?" looks the same whether the agent reads a file or deletes your database.

So you stop reading them. 🧵

**2/**
That reflex is a security bug, not a UX nit. A prompt injection that triggers one approval you rubber-stamp has bypassed oversight completely.

The prompts are undifferentiated because nothing knows which actions are *reversible*.

I built Unwind to supply that missing primitive. [demo GIF]

**3/**
Unwind is a transparent MCP proxy. It classifies every tool call by reversibility:

R0 nullipotent · R1 self-reversible · R2 compensable · R3 mitigable-only · R4 irreversible

Then it auto-allows the reversible majority (with a real undo log) and interrupts you only for the irreversible minority.

**4/**
The demo, and I mean this honestly:

Agent deletes a page, drops a table, sends an email, force-pushes.
You type `unwind undo`.
3 come back.
The email comes back marked: "couldn't be undone — here's why I should have asked first."

That last line is the entire thesis.

**5/**
Unwind never fakes an undo. It grades fidelity — exact / semantic / approximation / failed — and reports the residue it *can't* erase: notifications that fired, audit entries, version bumps.

A false undo guarantee would just re-create the auto-approve reflex I'm curing.

**6/**
Two ideas I think are the interesting part:

• Reversibility = f(tool, environment). write_file is reversible on a git-backed tree, irreversible on a versionless one. Class is re-derived per environment.

• Reversibility has a half-life: recall ~30s, trash ~30d, payment void-before-settlement. The undo log expires.

**7/**
Setup is one line. Wrap any existing MCP server:

`unwind run -- <your server>`

No client or server changes. Unknown methods pass through untouched. `--passthrough-only` is the panic switch. Confirmations ride MCP's native elicitation, so it works in any compliant client.

**8/**
What Unwind is NOT: a gateway.

Auth / RBAC / rate limiting / secret scanning is a saturated space (Docker MCP Gateway, ToolHive, agentgateway, ContextForge…). Permanently out of scope.

Unwind embeds *inside* them. They prevent; Unwind recovers.

**9/**
There's also a benchmark — ReversiBench — with server-disjoint splits and a live sandbox that actually runs forward+inverse and diffs state, so fidelity is measured, not asserted.

Numbers are still landing. I'd rather show TBD than fake a chart.

**10/**
Open source, Apache-2.0, Python + a Node shim.

Repo, docs, and the 20-second demo below. I'd love to hear where you think the classifier or the auto-synthesised inverses will break — that's the risky, interesting part. 👇

[link]
