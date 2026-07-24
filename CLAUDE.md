# CLAUDE.md — Working context for building Unwind

You are building **Unwind**, a reversibility layer for agentic tool use: a transparent MCP proxy that classifies which tool calls can be taken back, synthesises inverse operations, maintains a cross-server undo log, and interrupts the human only for genuinely irreversible actions. Read `PROJECT.md` for the full spec. This file is the operational contract.

## The thesis (keep this in mind on every design call)
The product is not "an undo button." The thesis is: **human oversight of agents fails because approval prompts are undifferentiated, and they are undifferentiated because nothing knows which actions are reversible.** Reversibility inference is the missing primitive. Every feature either sharpens that classification or exploits it (auto-allow the reversible majority, interrupt for the irreversible minority). Features that do neither are out of scope.

## Golden rules (do not violate)
1. **Transparency is sacred.** The proxy must be invisible when idle. Any method Unwind does not understand is forwarded byte-faithfully. A proxy that breaks a client is worthless — protocol-conformance tests gate every PR, and `--passthrough-only` must always work as a panic switch.
2. **Fail safe, never fail open.** Unknown tool, failed classification, timeout, crashed classifier → escalate to the human. Never auto-allow on uncertainty.
3. **Never over-promise reversibility.** A false undo guarantee is worse than no guarantee — it manufactures the exact auto-approve reflex the project exists to cure. Low-confidence compensations degrade a class (R2→R3) and escalate. Fidelity is always reported graded, never as a boolean.
4. **Compensation is semantic, not bitwise.** Per Garcia-Molina & Salem, a compensating action restores "an acceptable approximation," not exact prior state. Grade fidelity as exact / semantic / acceptable-approximation / failed, and always report **residue** (notifications fired, audit entries, version bumps that undo cannot remove).
5. **Reversibility is a function of (tool, environment), never tool alone.** The same `write_file` is R1 on a git-backed tree and R4 on a versionless one. Environment descriptors are first-class; classes are re-derived per environment.
6. **We are not a gateway.** Auth, RBAC, rate limiting, secret scanning, container isolation are permanently out of scope — that space is saturated (Docker MCP Gateway, ToolHive, MCPX, ContextForge, Kong, agentgateway, Pomerium). We do the one thing none of them do: recovery. Reject scope creep.
7. **R0 calls must be ~free.** Classify at `tools/list` time and cache. Never add latency to reads.
8. **Confirmations ride native MCP elicitation** (MRTR / SEP-2322), never a bespoke UI. This is what makes it work in every compliant client.
9. **The undo log is ours and must be durable.** The 2026-07-28 spec RC removed protocol-level sessions — do not lean on transport state. SQLite, survives restart, expiry-aware.
10. **Metrics match `PROJECT.md` §8 exactly.** Every metric gets a docstring citing its definition and a numeric regression test against a hand-computed fixture.

## Core types (define first, `unwind/types.py`)
- `ReversibilityClass`: ordinal enum `R0…R4` (§5.1). Ordinal comparisons must be meaningful.
- `ToolSpec`: `{server, name, description, input_schema, output_schema, effect_verb, entity, rev_class, confidence, blast_radius_hint, half_life}`.
- `CompensationPlan`: `{pre_read, forward, inverse_template, expiry, fidelity_grade, confidence}`.
- `UndoEntry`: `{id, ts, server, tool, args, result, prestate, plan, expires_at, status}`.
- `EnvironmentDescriptor`: capability flags (versioned? trash? soft-delete? retention window?).
- `Decision`: `auto_allow | auto_allow_logged | elicit_confirmation | block`.

## Build order (PROJECT.md §11 — do not skip ahead)
W1 transparent proxy + conformance suite → W2 classification v1 + catalog crawler → W3 undo log + pre-state capture + `unwind.undo` (**the demo must work this week**) → W4 compensation synthesis + sandbox validation → W5 escalation policy + elicitation + calibration → W6 ReversiBench + full metric harness → W7 polish + TypeScript stdio shim + launch → W8 paper.

Each week has a Definition of Done in §11. Do not advance until it is met and CI is green.

## The agentic surface
Unwind is itself an MCP server exposing `unwind.preview`, `unwind.undo`, `unwind.explain_risk`, `unwind.history`, `unwind.checkpoint`. This matters: the agent can reason about and reverse *its own* actions. This is what makes Unwind agentic rather than a filter — treat these tools as a first-class product surface, not a debug afterthought.

## Tech stack
Python 3.11; official `mcp` SDK (Unwind is both client and server), `pydantic`, `anyio`, `typer`, `aiosqlite`, `httpx`, `structlog`. Metrics/calibration: `numpy`, `scipy`, `scikit-learn`, `matplotlib`. Sandbox: Docker-composed real servers (filesystem, git, sqlite) plus in-repo mock comms/payments servers. TypeScript port of the stdio shim in week 7.

## Definition of Done (per PR)
- ruff + black + mypy + pytest green in CI; **plus the protocol-conformance suite**. No red merges.
- New code has tests; metric code has a numeric regression test; `eval/` coverage ≥80%.
- Public API or protocol behaviour changes update `README.md` / `PROJECT.md`.
- Conventional Commit message (`feat:`, `fix:`, `bench:`, `docs:`, `test:`, `refactor:`, `chore:`, `perf:`).

## Git conventions
Trunk-based; `main` always green; `feat/<module>` branches; PR → squash-merge. Never commit crawled server data, credentials, or sandbox state — commit crawlers and hashes. Semantic version tags; PyPI/npm publish on tag. Results regenerated by `make results` from pinned configs; generated tables checked into `paper/`.

## Benchmark hygiene (gets this wrong once and the paper is dead)
- Splits are **server-disjoint**, never tool-disjoint within a server — sibling tools share lexical patterns and leak.
- Calibration thresholds fit only on the calibration split, never test.
- ≥2 annotators on a stratified sample; report ordinal IAA (Krippendorff's α / Fleiss' κ); publish the annotation guide.
- Fidelity claims must come from the **live sandbox** (actual forward+inverse execution and state diff), never from model assertion.
- Bootstrap 95% CIs on every headline number.

## When unsure
Prefer the choice that fails safe and the simplest thing satisfying the metric definitions. If a decision affects the paper's claims (how a class boundary is drawn, how fidelity is graded, how blast radius is estimated), leave a `# DECISION:` comment explaining the reasoning and add a test pinning the behaviour.
