# Unwind — A Reversibility Layer for Agentic Tool Use

**Project document / build spec (v1.0).** Single source of truth for building Unwind with Claude Code. Contains the thesis, problem definition, literature-grounded design, the reversibility taxonomy, the compensation-synthesis algorithm, the evaluation methodology (paper core), architecture, repo layout, an 8-week plan, git workflow, adoption strategy, and paper plan.

**One-liner:** *Unwind sits between any AI agent and any MCP server, works out which actions can be taken back, quietly takes back the ones that go wrong, and interrupts you only for the ones that truly can't be undone.*

**Name note:** originally scoped as "Saga"; renamed because SagaLLM (Chang & Geng, VLDB 2025, arXiv:2503.11951) already occupies that name in this exact conceptual space. "Unwind" is the stack-unwinding metaphor — compensations execute in reverse order, exactly like unwinding a call stack.

---

## 1. The thesis

The obvious pitch for this project is "an undo button for AI agents." That's the demo, not the thesis. The thesis is sharper, and it is what makes this research rather than a utility:

> **Human oversight of agents is failing because approval prompts are undifferentiated. They are undifferentiated because nothing in the stack knows which actions are reversible. Reversibility inference is therefore the missing primitive — not a convenience feature, but the enabling mechanism that makes human oversight work at all.**

The chain of evidence:

1. **MCP has no consequence semantics.** A June 2026 audit of 2,031 MCP servers found that across 31,000 tools, the most common verbs after `get` and `list` are `create`, `search`, `update`, and `delete` — two of the top six are mutations the model cannot undo — and *the protocol provides no separation between any of them*. `delete_*` alone appears 466 times, roughly one destructive-named tool per five servers, before counting `drop`, `remove`, `wipe`, `purge`. And 96.1% of tool descriptions carry no consequence warning, despite those descriptions being the only briefing the model receives.

2. **Tool schemas were never designed to carry this.** "Mind the GAP" (arXiv:2602.16943) states that current tool-calling schemas define name, description and parameters but include *no safety-relevant metadata*, and proposes that tool definitions should structurally declare PII exposure, **action reversibility**, and authorization requirements — noting natural-language descriptions are demonstrably insufficient for safety reasoning. This is an explicit, citable open call for what Unwind builds.

3. **So every client falls back to a binary confirm/deny dialog — which fails.** Confirmation fatigue is documented as a *security* vulnerability, not a UX annoyance: when approvals come too often people develop an approve-approve-approve reflex, and a prompt injection that triggers an approval the user clicks through has bypassed human oversight entirely. OWASP's Agentic Top 10 (ASI09, Human-Agent Trust Exploitation) and Rippling's T10 ("Overwhelming Human-in-the-Loop") both name it. Per Changkun (Mar 2026): per-tool-call approval is *"solved in theory, unsolved in practice"* — risk-tiered frameworks exist, but **MCP provides no protocol-level mechanism for any of them, so every client reinvents the wheel.**

4. **The fix everyone converges on requires the one thing nobody has.** Every serious risk-tiering framework distinguishes "anything you can cleanly undo" (log it, let the agent proceed) from "money movement, data deletion, external communications" (never auto-approve). Blake Crosley's framing is the crispest: approval must sit before the **commit point** — the moment an agent crosses from reversible work into side effect — because *"human approval after the commit point becomes incident response, not authorization."* But **nothing today can tell you where the commit point is for an arbitrary third-party tool.** That classification is the missing primitive.

Unwind supplies it, then exploits it twice: to *auto-allow* the reversible majority with a real undo log behind it, and to *reserve interruption* for the irreversible minority — so the approval signal stops being noise and starts meaning something.

---

## 2. Problem statement (precise)

Unwind is a transparent MCP intermediary. It speaks MCP to the client and MCP to each upstream server, so **no client and no server needs modification**.

**Inputs:** the connected servers' tool catalogs (`tools/list`: names, descriptions, JSON schemas); the live stream of `tools/call` requests and results; optional environment descriptors (e.g. "this filesystem is git-backed", "this workspace has trash retention").

**Per-call outputs:**
- `reversibility_class ∈ {R0…R4}` with a calibrated confidence (§5),
- `blast_radius` — predicted count/scope of affected entities,
- `compensation_plan | null` — a concrete inverse call, pre-state capture included (§6),
- `decision ∈ {auto_allow, auto_allow_logged, elicit_confirmation, block}` from a policy tuned to a target damage rate,
- an entry in a durable, cross-server **undo log**.

**Session-level output:** `unwind(n)` — reverse the last *n* agent actions across every connected server, in reverse order, reporting per-action outcome as `restored` / `approximately_restored` / `could_not_undo` with reasons.

**Success contract:** at a chosen operating point, minimise **interruptions per session** subject to holding **irreversible-damage rate** below a target (e.g. ≤1% of truly-R4 actions executed without confirmation). This is a selective-prediction problem with asymmetric loss — structurally identical to VerifyDoc's abstention layer, applied to actions instead of extracted fields.

---

## 3. Literature review outcomes

### 3.1 The protocol and ecosystem (why a proxy is the right shape)
MCP is a JSON-RPC host/client/server protocol; servers expose **tools, resources, prompts**, clients expose **sampling, roots, elicitation**. Two standard transports: **stdio** (local; client spawns the server as a subprocess, newline-delimited JSON-RPC over stdin/stdout) and **Streamable HTTP** (remote; HTTP+SSE, replacing the older HTTP+SSE transport). Ecosystem scale mid-2026: ~97M monthly SDK downloads, 15,926 repos with the `mcp-server` topic (May 2026), `modelcontextprotocol/servers` ~86k stars; donated to the Agentic AI Foundation under the Linux Foundation in Dec 2025.

Two spec developments matter enormously here:
- **Elicitation is the native confirmation channel.** The 2026-07-28 RC rebuilds server→client requests as *input requests* embedded in results (MRTR, SEP-2322), the spec's own example being literally `{"type": "elicitation", "message": "Delete 3 files?", "schema": {"type":"boolean"}}`. Unwind's confirmations ride this — no custom UI, works in any compliant client.
- **Gateways are first-class.** Streamable HTTP now requires `Mcp-Method` and `Mcp-Name` headers (SEP-2243) *specifically so gateways and rate-limiters can route on the operation without inspecting the body.* The proxy pattern is blessed by the spec.

The RC also removed protocol-level sessions and the GET stream endpoint, favouring explicit model-visible handles over hidden transport state. **Design implication: Unwind must keep its own durable undo log; it cannot lean on protocol session state.**

### 3.2 The gateway landscape (crowded — so don't compete there)
Open-source/open-core MCP gateways as of 2026: Docker MCP Gateway (container isolation, signed images, secrets injection), MCPX/Lunar, Microsoft MCP Gateway, IBM ContextForge, MCPJungle, Stacklok **ToolHive** (Cedar-policy authz, OIDC, audit), **Envoy AI Gateway**, **agentgateway** (Linux Foundation), Kong AI Gateway, Pomerium, Lasso MCP Gateway (~360 stars), MCPGuard, Obot, Operant, Bifrost, ToolMesh. Cisco announced dedicated MCP security tooling at RSA 2026.

Their feature sets are near-identical: auth/OAuth, RBAC, routing, aggregation, rate limiting, tool filtering, secret scanning, audit logging, container isolation.

**Every one is a preventive control — allow or block. Not one performs recovery.** None classifies reversibility, none synthesises compensations, none can undo. That is the entire opening.

**Positioning rule (non-negotiable): Unwind is not another gateway.** It is the reversibility layer, shipped so it runs standalone *or* as middleware inside any of the above. Competing on auth/RBAC is a losing fight; being the thing all of them lack is a winning one.

### 3.3 Agent-safety benchmarks (they measure the harm; nobody recovers from it)
- **ToolEmu** (Ruan et al., 2024): even the safest LLM agent shows tool-related failures 23.9% of the time, 68.8% of identified failures validated as real-world risks.
- **SafeToolBench** (arXiv:2509.07315): prior benchmarks assess risk *retrospectively*, after execution — impractical precisely because high-risk executions are irreversible.
- **ClawsBench** (arXiv:2604.05172): productivity agents (email/calendar/docs); documents safety instructions lost under context compression leading to bulk-deletion of hundreds of emails.
- **LITMUS** (arXiv:2605.10779): OS-level behaviour jailbreaks, semantic-physical dual verification, OS-level state rollback *for benchmark isolation*.
- **"Beyond Attack-Success Rate"** (arXiv:2607.07474, July 2026): ordinal severity scale graded by action-effect properties, computed deterministically and by an LLM panel. Critical observation: **reversibility is environment-determined** — an append irreversible in a versionless drive is reversible in a versioned filesystem, so the metadata table must be re-derived per environment.
- **Safety-benchmark taxonomy survey** (arXiv:2605.16282): names "irreversible actions without confirmation" as a distinct, particularly consequential execution-layer failure class.
- **Irreversibility budgeting** (arXiv:2603.03515): proposes an irreversibility score ι: A → [0,1] and a cumulative budget before mandatory human re-authorisation.

**Gap:** these *measure* unsafe and irreversible actions. None provides a runtime that classifies reversibility for arbitrary third-party tools, synthesises inverses, and executes recovery.

### 3.4 Transactional foundations (the theory to stand on)
**Sagas** (Garcia-Molina & Salem, SIGMOD '87, pp. 249–259): a long-lived transaction decomposes into T₁…Tₙ, each with a compensating transaction Cᵢ; the guarantee is either T₁…Tₙ or T₁…Tⱼ, Cⱼ…C₁ in reverse order. **Crucial nuance for our metrics:** a compensating step undoes the transaction *semantically* — it does **not** necessarily restore exact prior state, only "an acceptable approximation." Rollback fidelity must therefore be graded, never bitwise.

Azure's Compensating Transaction Pattern adds the rule Unwind operationalises: *identify compensable versus irreversible steps, and order workflows so irreversible steps occur only after all critical validations succeed.*

**Closest prior work — and the differentiation:**
- **SagaLLM** (arXiv:2503.11951; VLDB, 10.14778/3750601.3750611) integrates the Saga pattern with persistent memory, automated compensation and independent validation agents for **multi-agent LLM planning**, evaluated on REALM-Bench. It is a *framework you author your workflow inside*, with compensations defined as part of that workflow. Unwind operates on **arbitrary third-party tools nobody authored for it**, at the protocol layer, where compensations must be *inferred* — and asks the empirical question SagaLLM never does: which of the real ecosystem's tools are even compensable?
- **GOEX** (Berkeley/Gorilla, EECS-2025-5) proposes runtime design principles for LLM-generated actions including rollback and **post-facto validation**. Genuinely close in spirit and the honest closest system-level ancestor. Differences: it is an execution runtime you adopt, predates MCP's ecosystem scale, and provides no reversibility taxonomy, no ecosystem-scale benchmark, and no calibrated escalation policy.
- **SafeFlow** (arXiv:2506.07564), **REPOT** (arXiv:2605.30052), **Generator-Assistant Stepwise Rollback** (arXiv:2503.02519): rollback *within* an agent's own reasoning trace, not across external stateful services.

### 3.5 Synthesis — the four-part gap
Nobody has: (a) a **reversibility taxonomy for real-world agent tools** that is environment-relative; (b) an **ecosystem-scale labelled benchmark** of tool reversibility; (c) **automatic compensation synthesis** for tools nobody annotated, with measured rollback fidelity; (d) a **calibrated escalation policy** that provably trades interruptions against irreversible damage. Unwind delivers all four, and each is independently publishable if the others disappoint.

---

## 4. Deliverables

1. **Unwind (the runtime)** — the `unwind` MCP proxy: one config line in any MCP client, wraps all servers, classifies every call, maintains the undo log, elicits confirmation via the native protocol channel, and exposes its own MCP tools (`unwind.preview`, `unwind.undo`, `unwind.explain_risk`, `unwind.history`, `unwind.checkpoint`) so **the agent itself can reason about and reverse its own actions** — this is what makes it agentic rather than a filter.
2. **ReversiBench (the benchmark)** — a labelled corpus of real MCP tools annotated with reversibility class, compensation availability, blast radius and reversibility half-life, plus a **live sandbox harness** where forward+inverse pairs actually execute and state-equivalence is verified.
3. **The synthesiser** — the compensation-inference algorithm (§6) with measured coverage, validity and fidelity.
4. **The paper** — taxonomy + benchmark + synthesiser + calibrated escalation, with a strong reproducible baseline.

---

## 5. The reversibility taxonomy (core conceptual artifact)

### 5.1 The R-scale (ordinal, 5 classes)
| Class | Name | Definition | Examples |
|---|---|---|---|
| **R0** | Nullipotent | No state change; safe to repeat. | `get_*`, `list_*`, `search_*`, `read_file` |
| **R1** | Self-reversible | The *same* tool restores exact prior state given captured pre-state. | `update_record`, `set_status`, `write_file` (prior content captured) |
| **R2** | Compensable | A *different* tool on the same server semantically undoes it; restores an acceptable approximation. | `create_page`→`delete_page`; `add_member`→`remove_member`; `grant`→`revoke` |
| **R3** | Mitigable only | No true inverse; partial mitigation only, and third parties may already have observed the effect. | `send_email`→retraction; `post_message`→delete (already read); `publish`→unpublish (already cached) |
| **R4** | Irreversible | No inverse and no meaningful mitigation. | payment capture, permanent delete with no trash, key destruction, physical actuation, immutable-ledger write |

The scale is **ordinal with asymmetric loss**: misclassifying R4 as R1 is catastrophic; misclassifying R1 as R4 merely annoys. Every metric in §8 respects this.

### 5.2 Orthogonal dimensions (a class alone is not enough)
- **Blast radius** — cardinality of affected entities. `delete_record(id)` and `delete_records(filter="*")` share a class but not a risk.
- **Externality** — does the effect become visible to third parties? Drives the R2/R3 boundary.
- **Reversibility half-life** *(novel contribution)* — many actions are reversible only within a window: email recall ~30 s, trash retention 30 days, payment void-before-settlement. Reversibility is **time-decaying**, so the undo log has an expiry. No existing framework models this; it falls straight out of taking compensation seriously and is clean, defensible novelty.
- **Environment-relativity** — the same tool is R1 on a git-backed filesystem and R4 on a versionless one. Following arXiv:2607.07474, class assignment is a function of (tool, environment), never tool alone. Unwind models environments as declarative capability descriptors and re-derives classes per environment.

### 5.3 Commit-point semantics
Adopting Crosley's framing: the **commit point** is where an action crosses from reversible to side-effecting. Unwind's job is to (a) locate it automatically, (b) place confirmation strictly *before* it, and (c) **push it later** wherever possible by capturing pre-state, so an action that would have been R4 becomes R1/R2.

---

## 6. Compensation synthesis (method core)

Given a mutating tool `T` and the full toolset `S` of its server:

**Stage 1 — Effect typing.** Classify `T`'s effect verb (create / update / delete / send / execute / grant) and target entity noun from name, description and schema. Ensemble of lexical rules + an LLM classifier (self-consistency over k samples yields a confidence signal).

**Stage 2 — Inverse candidate retrieval.** Search `S` by: verb-antonym matching (create↔delete, add↔remove, enable↔disable, grant↔revoke, archive↔restore); entity-noun agreement; and **parameter-schema compatibility** — does the candidate accept an identifier of the type `T` returns? This last is the strongest signal and is purely structural.

**Stage 3 — Pre-state capture planning.** Identify the read tool that snapshots the target entity before mutation (`get_X` matching `T`'s entity). Without a viable snapshot, R1 is unreachable and the class degrades.

**Stage 4 — Plan emission.** Produce `CompensationPlan{pre_read, forward, inverse_template, expiry}`, where `inverse_template` binds arguments from captured pre-state and `T`'s response.

**Stage 5 — Sandbox validation *(what makes this research, not heuristics)*.** In an isolated instance, execute pre_read → forward → inverse, then diff state. Grade fidelity as **exact** / **semantic** (key fields restored) / **acceptable approximation** (per Garcia-Molina) / **failed**. Record **residue** — side-effects undo cannot remove (notifications fired, audit entries, version bumps).

**Stage 6 — Confidence and fallback.** Combine structural-match strength, LLM agreement and validated fidelity into a calibrated confidence. Below threshold, degrade the class (R2→R3) and escalate rather than promise an undo that won't hold. **Never over-promise reversibility — a false undo guarantee is worse than none**, because it induces exactly the auto-approve reflex we're curing.

---

## 7. System architecture

```
MCP Client (Claude Desktop / Code / Cursor / Goose / VS Code / n8n / any)
        │  stdio or Streamable HTTP — unmodified
        ▼
┌──────────────────────────────────────────────────────────────┐
│                        UNWIND PROXY                          │
│                                                              │
│  Catalog Analyzer   ── on tools/list: classify every tool,   │
│      │                 synthesize compensation plans, cache  │
│      ▼                                                       │
│  Call Interceptor   ── on tools/call:                        │
│      ├─ Reversibility Classifier  (R0–R4 + confidence)       │
│      ├─ Blast-Radius Estimator    (dry-run / read-probe)     │
│      ├─ Pre-State Capturer        (snapshot before mutate)   │
│      ├─ Escalation Policy         (auto | elicit | block)    │
│      │      └─ confirmation via native MCP elicitation       │
│      └─ Undo Log (durable, cross-server, expiry-aware)       │
│                                                              │
│  Unwind Tools (exposed to the agent as a real MCP server):   │
│      unwind.preview · unwind.undo · unwind.explain_risk ·    │
│      unwind.history · unwind.checkpoint                      │
└──────────────────────────────────────────────────────────────┘
        │  fan-out, unmodified MCP
        ▼
Upstream MCP servers: filesystem · git · sqlite/postgres · Notion ·
Slack · Gmail · Stripe · Jira · CRM · cloud · calendar · …
```

**Deployment modes:** (a) *standalone stdio shim* — one line in `mcp.json`, zero infra, the default and the mode that wins stars; (b) *HTTP proxy* — for teams; (c) *middleware library* — embeddable inside Docker MCP Gateway / ToolHive / agentgateway, so Unwind complements rather than competes.

**Design invariants:** the proxy is transparent (any unrecognised method passes through untouched); classification never blocks the hot path for R0 calls (cache aggressively at `tools/list` time); the undo log survives process restart; failures fail *safe* (unknown → escalate, never → auto-allow).

---

## 8. Evaluation methodology (paper core)

Five metric families. Families C and D reuse the calibration/selective-prediction machinery from VerifyDoc — deliberate, and part of the coherent research identity.

### A. Reversibility classification
- **Macro-F1** and **per-class F1** over R0–R4.
- **Ordinal MAE** on the R-scale (R4→R3 is a smaller error than R4→R0).
- **Critical Error Rate (CER)** — fraction of true-R4 actions classified ≤R2. *The safety-critical asymmetric metric; report it as the headline.*
- **Binary AUROC/AUPR** for irreversible-vs-not.
- **Environment sensitivity** — Δ in class assignment when the environment descriptor changes (git-backed vs versionless), validating §5.2.

### B. Compensation synthesis
- **Compensation coverage** — % of mutating tools receiving a candidate inverse.
- **Compensation validity** — % of synthesised inverses that execute without error.
- **Rollback fidelity** — graded exact / semantic / acceptable-approximation / failed. *Never report a single "undo worked" number.*
- **Residue rate** — % of undos leaving detectable side-effects.
- **Half-life accuracy** — predicted vs actual reversibility window.

### C. Escalation policy (selective prediction, asymmetric loss)
- **Interruption–damage curve** (the risk–coverage analogue): interruptions per session vs irreversible-damage rate.
- **E-AURC** on that curve — unitless, comparable across systems.
- **Interruptions@1% damage** — *the headline product number*: how rarely we interrupt while letting through ≤1% of irreversible actions unconfirmed.
- **Damage@AutoApprove(k)** — leakage under a fixed auto-approve budget.
- **ECE / Adaptive ECE** on risk scores, with a reliability diagram.
- **FPR@95%TPR** — needless interruptions when catching 95% of irreversible actions (direct fatigue proxy).

### D. System
- Added latency per call, p50/p95, split R0 (must be ~free) vs mutating.
- End-to-end undo latency and success rate.
- **Compatibility rate** — % of tested client×server pairs working unmodified. *Adoption depends on this being ~100%.*

### E. End-to-end agent-level
On destructive-scenario suites (adapting ToolEmu, ClawsBench, AgentDojo-style traces): **damage prevented**, **task completion preserved** (does the guard break ordinary work?), and the resulting **safety–utility frontier**. A guard that stops all damage by blocking everything is worthless; the frontier is the honest reporting format.

### Experimental protocol
- **Corpus:** catalog public MCP servers at ecosystem scale (the PolicyLayer audit establishes ~2,031 servers / 31,000 tools to sample from). Stratify by domain (files, VCS, DB, comms, payments, CRM, cloud, calendar) so the benchmark is cross-vertical by construction.
- **Labelling:** ≥2 independent annotators on a stratified sample; report **Krippendorff's α / Fleiss' κ** (ordinal). Publish the annotation guide. Adjudicate disagreements and report the rate.
- **Splits:** **server-disjoint** train/calibration/test — never tool-disjoint within a server, or lexical leakage inflates results. Calibration thresholds fit only on the calibration split.
- **Live validation:** sandbox harness with real servers (filesystem, git, sqlite, plus mock email/CRM/payments) where forward+inverse actually execute and state is diffed. This makes fidelity claims real rather than asserted.
- **Statistics:** bootstrap 95% CIs on every headline number; paired tests for system comparisons. Pin model versions, seeds, server commit hashes.
- **Compute:** trivial — classification and orchestration only. Small open models locally; frontier APIs as comparison rows. No training.

---

## 9. Repository structure

```
unwind/
├── README.md                    # quickstart + the undo demo GIF
├── CLAUDE.md                    # Claude Code working context
├── PROJECT.md                   # this document
├── LICENSE                      # Apache-2.0
├── pyproject.toml               # pip install unwind-mcp
├── Makefile                     # test | lint | results | demo | bench
├── .github/workflows/ci.yml
├── unwind/
│   ├── types.py                 # ToolSpec, Call, ReversibilityClass, CompensationPlan, UndoEntry
│   ├── proxy/
│   │   ├── stdio.py             # stdio shim (default mode)
│   │   ├── http.py              # Streamable HTTP mode
│   │   ├── passthrough.py       # unrecognised methods forwarded untouched
│   │   └── elicit.py            # confirmations over native MCP elicitation
│   ├── classify/
│   │   ├── lexical.py           # verb/noun rules
│   │   ├── schema.py            # structural signals
│   │   ├── llm.py               # LLM classifier + self-consistency
│   │   ├── environment.py       # environment descriptors, re-derivation
│   │   └── ensemble.py
│   ├── synthesize/
│   │   ├── effect_typing.py
│   │   ├── inverse_search.py    # antonym + entity + schema-compat matching
│   │   ├── prestate.py
│   │   ├── plan.py
│   │   └── validate.py          # sandbox forward+inverse, fidelity grading
│   ├── blast.py                 # blast-radius estimation via read-probes
│   ├── undolog/                 # durable, expiry-aware, cross-server
│   ├── policy/                  # escalation thresholds, damage-rate solver
│   ├── tools.py                 # unwind.preview/undo/explain_risk/history
│   ├── calibration/             # temperature/isotonic/conformal on risk scores
│   └── cli.py
├── bench/                       # ReversiBench
│   ├── catalog/                 # server crawl + tool extraction
│   ├── labeling/                # guide, tooling, IAA scripts
│   ├── sandbox/                 # live servers for fidelity validation
│   ├── scenarios/               # destructive end-to-end scenarios
│   └── card.md                  # dataset card: sources, licenses, splits
├── eval/
│   ├── classification.py        # macro-F1, ordinal MAE, CER, AUROC
│   ├── compensation.py          # coverage, validity, fidelity, residue
│   ├── escalation.py            # interruption–damage, E-AURC, ECE, FPR@95
│   ├── system.py                # latency, compatibility
│   └── stats.py                 # bootstrap CIs, paired tests
├── scripts/
├── tests/
└── paper/
```

---

## 10. Tech stack

Python 3.11. `mcp` official SDK (client *and* server roles — the proxy is both), `pydantic` (typed protocol objects), `anyio` (async), `typer` (CLI), `sqlite`/`aiosqlite` (durable undo log), `httpx` (Streamable HTTP), `structlog`. Classification: small local models via Ollama/vLLM plus API models for comparison. `scikit-learn`/`scipy`/`numpy` for calibration and metrics; `matplotlib` for curves. Sandbox: Docker-composed real servers (filesystem, git, sqlite) plus mock comms/payments servers written in-repo.

Ship a **TypeScript port of the stdio shim** by week 7 — a large share of MCP client users live in Node, and this roughly doubles the addressable audience.

---

## 11. Implementation plan (8 weeks, solo)

**Week 1 — transparent proxy.** stdio shim wrapping a server, forwarding everything untouched; verify against `modelcontextprotocol/server-filesystem` with MCP Inspector; passthrough tests for every method. *DoD: Claude Desktop behaves identically with Unwind in the path; compatibility suite green.*

**Week 2 — classification v1 + catalog.** `types.py`; lexical + schema classifiers; catalog crawler over public servers; first 300 tools hand-labelled. *DoD: `unwind classify <server>` prints an R-scale table.*

**Week 3 — undo log + pre-state capture + `unwind.undo`.** Durable log; snapshot-before-mutate; R1 undo end-to-end on filesystem/sqlite. *DoD: the demo works — agent overwrites files, `unwind.undo` restores them.*

**Week 4 — compensation synthesis.** Effect typing, inverse search, plan emission, sandbox validation with fidelity grading. *DoD: R2 undo works on ≥2 real servers; coverage/validity/fidelity measured.*

**Week 5 — escalation policy + elicitation.** LLM classifier + self-consistency; calibration; damage-rate threshold solver; confirmations over native elicitation; blast-radius probes. *DoD: first interruption–damage curve.*

**Week 6 — ReversiBench.** Scale labelling with IAA; server-disjoint splits; scenario suite; full metric harness; `make results` reproduces everything. *DoD: all five metric families reported with bootstrap CIs.*

**Week 7 — polish + TS port + launch.** README with the GIF, one-line install, PyPI + npm, docs site, `good-first-issue` labels. *DoD: v0.1.0 tagged and published; Show HN / Reddit / X drafted.*

**Week 8 — paper.** Write against auto-generated tables/figures; arXiv; submit. *DoD: preprint live, venue submission in.*

---

## 12. Git workflow

Repo from commit #1; Apache-2.0. Trunk-based, `main` always green, short-lived `feat/…` branches, PR → squash-merge. Conventional Commits (`feat:`, `fix:`, `bench:`, `docs:`, `test:`). Every PR passes ruff + black + mypy + pytest in CI; no red merges. **Protocol-conformance tests are mandatory and non-negotiable** — a proxy that breaks a client is worthless, so passthrough fidelity gets its own suite run against every supported server. Never commit crawled server data or credentials; commit crawlers and hashes. Semantic version tags; PyPI/npm publish on tag. Results regenerated by `make results` from pinned configs and checked into `paper/`.

---

## 13. Adoption strategy (this is what earns stars)

- **The install must be one line.** Any friction here kills it.
- **The demo must be 20 seconds.** Agent deletes a page, drops a table, sends an email, force-pushes → type `undo` → three restore, and the email is flagged *"couldn't be undone — here's why I should have asked first."* That last line is the whole thesis in one screenshot, and it's honest.
- **Ship the taxonomy as a public artifact.** A browsable "reversibility index" of popular MCP servers is independently linkable, quotable and SEO-durable — it draws traffic even from people who never install the tool, and it *is* the benchmark.
- **Integrate, don't compete.** PRs adding Unwind as optional middleware to existing gateways convert competitors into distribution.
- **Comparable trajectories:** MCP security/infra tools reach 1–2k stars (mcp-scan ~2k, ToolHive ~1.9k); breakout agent tooling goes far higher. Target 1–5k within 6 months as success; treat 10k+ as upside, not plan.

---

## 14. Paper plan

**Working title:** *Unwind: Reversibility Inference and Compensation Synthesis for Agentic Tool Use.*

**Structure:** oversight-failure motivation (fatigue as a security bug; no reversibility metadata in schemas) → related work (sagas; SagaLLM; GOEX; agent-safety benchmarks; MCP gateways) → the taxonomy (R-scale, blast radius, half-life, environment-relativity) → compensation synthesis → ReversiBench construction → calibrated escalation → results across all five metric families → limitations → release.

**Claims to earn:** (1) reversibility is inferable from tool schemas at useful accuracy with a measurably low critical-error rate; (2) compensations can be synthesised for a substantial fraction of real mutating tools, with graded fidelity honestly reported; (3) reversibility-aware escalation cuts interruptions by a large factor at fixed irreversible-damage rate — i.e. **it makes human oversight sustainable**, which is the actual contribution.

**Venues (Aug–Oct 2026 window):** arXiv on tag; **IEEE SaTML 2027** (deadline ~Sep 29, 2026 — best fit; explicitly welcomes benchmarks/SoK); **ICLR 2027** (abstract Sep 19 / paper Sep 24, 2026); **NeurIPS 2026 workshops** on agents/trustworthy ML (late-Sept–Oct); **TMLR** rolling for fast archival. Honest expectation: a journal publication is impossible in this window; arXiv + workshop acceptance + repo traction is achievable and is the usable evidence.

---

## 15. Risks & pivots

- **Classification accuracy is mediocre.** Then the honest finding is *"tool schemas carry insufficient information to infer reversibility"* — which directly validates Mind-the-GAP's call for schema-level metadata and makes the benchmark plus a **proposed MCP schema extension (SEP)** the primary contribution. A proposed protocol extension is *stronger* EB1 evidence than a tool, not weaker.
- **Compensation coverage is low.** Report it. "Only X% of real MCP mutations are compensable" is an important, citable ecosystem finding, and it still justifies the escalation layer.
- **An official MCP reversibility annotation ships.** Best case, honestly — pivot to being the reference implementation and conformance checker; the benchmark becomes the conformance suite.
- **Proxy breaks clients.** Existential; mitigate with the mandatory conformance suite from week 1 and a `--passthrough-only` panic switch.
- **Scope creep into gateway features.** Refuse. Auth/RBAC/rate-limiting are out of scope forever.
- **Over-promising undo.** The worst failure mode: a false undo guarantee manufactures exactly the auto-approve reflex we're curing. Fidelity always graded; low-confidence compensations always degrade to escalation.

---

## 16. EB1-A mapping (honest)

Contributes to **authorship of scholarly articles** (arXiv + workshop/TMLR); **original contributions of major significance** (open-source adoption metrics; ReversiBench citations; strongest of all if a schema extension is adopted upstream); **judging** (review for the workshops you submit to). Pairs with VerifyDoc into one coherent thesis — *calibrated trust layers with selective human escalation*, VerifyDoc for perception and Unwind for action — materially better evidence than two unrelated tools, and it gives recommendation letters something specific to attest to.

**Reality check:** USCIS requires at least three criteria plus a holistic final-merits determination, and strong petitions document more with independent corroboration. Two projects are two pillars, not a petition. Plan complementary evidence (citations, talks, memberships, press, letters) in parallel, and consult an immigration attorney on overall strategy.

---

## References (verify at write-up)

Garcia-Molina & Salem, *Sagas*, SIGMOD '87, 249–259 · SagaLLM, arXiv:2503.11951 (VLDB, 10.14778/3750601.3750611) · GOEX, Berkeley EECS-2025-5 · SafeFlow, arXiv:2506.07564 · Mind the GAP, arXiv:2602.16943 · Beyond Attack-Success Rate, arXiv:2607.07474 · Safety-benchmark taxonomy, arXiv:2605.16282 · SafeToolBench, arXiv:2509.07315 · ClawsBench, arXiv:2604.05172 · LITMUS, arXiv:2605.10779 · ToolEmu (Ruan et al., 2024) · Irreversibility budgeting, arXiv:2603.03515 · MCP spec 2026-07-28 RC (SEP-2322 MRTR, SEP-2243 headers) · PolicyLayer, *State of MCP* (June 2026) · Azure Compensating Transaction Pattern · OWASP Agentic Top 10 (ASI09).

*All ecosystem figures, star counts, deadlines and spec details are point-in-time as of July 2026 and must be re-verified before submission.*
