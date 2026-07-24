---
title: FAQ
---

# FAQ

Honest answers to the questions Unwind gets asked most. Where a claim would need a number, it is marked [TBD](benchmark.md) rather than invented.

## Is this just an undo button?

**No.** The undo button is the demo; reversibility *inference* is the primitive. The insight is that human oversight of agents fails because approval prompts are undifferentiated, and they are undifferentiated because nothing in the stack knows which actions are reversible. Unwind supplies that missing classification, then exploits it twice — auto-allowing the reversible majority with a real undo log behind it, and reserving interruption for the irreversible minority. A plain undo button doesn't tell you *when to worry*; the [taxonomy](concepts/taxonomy.md) does.

## What if the classification is wrong?

Unwind **fails safe, never fails open**. On an unknown tool, a failed classification, a timeout, or a crashed classifier, the action resolves to the fail-safe default — **R4** — and escalates to the human. It never auto-allows on uncertainty. And when confidence is merely *low* rather than absent, Unwind **degrades the class one step toward irreversible** (R2→R3) and escalates, rather than shipping a compensation it cannot stand behind.

The cost of getting it wrong is deliberately asymmetric: misclassifying a true-R4 action *down* into the auto-allow band is catastrophic and is the [headline Critical Error Rate](benchmark.md) we minimise; misclassifying a reversible action *up* merely produces one needless prompt.

## Will it break my client?

**No — transparency is a golden rule.** Unwind is a transparent proxy: any MCP method it does not understand is forwarded byte-faithfully, so it is invisible when idle. Three things protect you:

1. A **protocol-conformance suite** gates every change — a proxy that breaks a client is worthless, so passthrough fidelity is tested against every supported server.
2. Confirmations ride the **native MCP elicitation** channel, not a bespoke UI, so they render in whatever your client already shows.
3. The **`--passthrough-only` panic switch** turns off every feature and forwards everything untouched:
   ```bash
   unwind run --passthrough-only -- <your server command>
   ```
   This must always work, by design.

## Does it add latency?

**Not to reads.** R0 (nullipotent) calls stay effectively free: classification happens **once at `tools/list` time and is cached**, never on the hot path. Only mutating calls pay for classification and pre-state capture, and even that is bounded. The [benchmark](benchmark.md) reports R0 and mutating latency separately (p50/p95) and holds R0 to a near-zero budget — actual figures are [TBD](benchmark.md).

## Can undo always restore exactly?

**No, and Unwind never claims it can.** Following Garcia-Molina & Salem, a compensation restores *"an acceptable approximation,"* not necessarily exact prior state. So:

- Fidelity is always **graded** — exact / semantic / acceptable-approximation / failed — never a boolean "it worked."
- Unwind always reports **residue**: the notifications that already fired, the audit entries, the version bumps that an undo cannot erase.
- **It never over-promises.** A false undo guarantee is worse than none, because it manufactures the exact auto-approve reflex the project exists to cure. See [Compensation synthesis](concepts/compensation.md).

The demo's fourth action — the sent email that comes back marked *"couldn't be undone — here's why I should have asked first"* — is that honesty made visible.

## Why is the same tool sometimes R1 and sometimes R4?

Because reversibility is a function of *(tool, environment)*, never the tool alone. `write_file` is **R1** on a git-backed tree (the prior blob is recoverable) and **R4** on a versionless, backupless drive (the overwrite is final). Unwind models environments as declarative capability descriptors and re-derives the class per environment. See [environment-relativity](concepts/taxonomy.md#environment-relativity-class-is-ftool-environment).

## What's the "reversibility half-life"?

Many actions are reversible only within a **time window** — email recall ~30 s, trash retention ~30 days, a payment voidable only before settlement. Reversibility is time-decaying, so the undo log has an **expiry**: once the half-life elapses, an entry flips to `EXPIRED` and `unwind undo` returns `could_not_undo` rather than a false success. It is a [novel dimension](concepts/taxonomy.md#reversibility-half-life-a-novel-dimension) that falls straight out of taking compensation seriously.

## We are not a gateway {#we-are-not-a-gateway}

**Auth, RBAC, rate limiting, secret scanning and container isolation are permanently out of scope.** That space is saturated — Docker MCP Gateway, ToolHive, agentgateway, ContextForge, MCPJungle, Kong, Pomerium and more all do it well. Unwind does the one thing none of them do: **recovery**. It runs standalone or [embeds inside those gateways](integrations.md) as middleware, adding reversibility to their prevention. Competing on gateway features is a losing fight; being the thing they all lack is a winning one.

## Does it need my LLM keys?

Classification uses an ensemble of lexical/schema rules plus an optional LLM classifier. The structural and lexical signals work without any API key; the LLM classifier (installed via the `[llm]` extra) sharpens borderline cases and provides a self-consistency confidence signal. Either way, R0 reads never invoke a model.

## How do I trust the numbers?

You don't have to take them on assertion. Fidelity comes from a **live sandbox** — actual forward+inverse execution and a state diff, not a model claiming success. Splits are **server-disjoint** to prevent lexical leakage, calibration is fit only on the calibration split, labelling uses ≥2 annotators with reported ordinal agreement, and every headline number carries a bootstrap 95% CI. See [ReversiBench](benchmark.md). Until those runs land, the numbers are honestly marked TBD.

## Does it work on Windows?

The **core library** (classification, compensation synthesis, the undo log, the eval harness) is cross-platform. The **stdio proxy transport** is currently POSIX-only — it uses asyncio pipe transports that the Windows Proactor event loop does not implement. On Windows, run Unwind under **WSL**, or use the **HTTP proxy mode**. Native Windows stdio (via a thread-backed reader) is tracked as future work.
