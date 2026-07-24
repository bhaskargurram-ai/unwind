---
title: Research paper
---

# The research paper

Unwind is a research project as much as a tool. The paper argues that **reversibility inference is the missing primitive** that makes human oversight of agents sustainable, and backs the argument with a taxonomy, a benchmark, a synthesiser and a calibrated escalation policy.

!!! abstract "Working title"
    *Unwind: Reversibility Inference and Compensation Synthesis for Agentic Tool Use.*

!!! note "Preprint and DOI are TBD"
    The preprint link (arXiv) and archival DOI (Zenodo) are **TBD** and will be posted here on release. The paper draft itself is not distributed with the docs.

## Summary of contributions

The paper makes four contributions, each independently publishable if the others disappoint:

1. **A reversibility taxonomy for real-world agent tools that is environment-relative.** The ordinal [R0–R4 scale](concepts/taxonomy.md) with three orthogonal dimensions — blast radius, externality, and the novel **reversibility half-life** — and the principle that class is a function of *(tool, environment)*, never tool alone.
2. **ReversiBench** — an [ecosystem-scale labelled benchmark](benchmark.md) of tool reversibility with server-disjoint splits and a **live sandbox** where forward+inverse pairs actually execute and state-equivalence is verified. It answers an unanswered empirical question: *which of the real ecosystem's tools are even compensable?*
3. **The compensation synthesiser** — [automatic inverse-operation synthesis](concepts/compensation.md) for tools nobody annotated, with coverage, validity and **graded** rollback fidelity measured on the live sandbox, and residue reported honestly.
4. **A calibrated escalation policy** — a selective-prediction layer with asymmetric loss that provably trades interruptions against irreversible damage, reported as an interruption–damage curve with the headline **Interruptions@1% damage**.

## The claims to earn

The paper commits to earning three claims, empirically:

1. Reversibility is **inferable from tool schemas** at useful accuracy, with a measurably low [Critical Error Rate](benchmark.md).
2. Compensations can be **synthesised for a substantial fraction** of real mutating tools, with graded fidelity honestly reported.
3. Reversibility-aware escalation **cuts interruptions by a large factor at a fixed irreversible-damage rate** — i.e. it makes human oversight *sustainable*, which is the actual contribution.

All supporting numbers are [TBD](benchmark.md) until `make results` runs against pinned configs.

## Where Unwind sits in the literature

- **Transactional foundations.** Garcia-Molina & Salem's **Sagas** (SIGMOD '87) give the compensating-transaction model — and the crucial nuance that a compensation restores *"an acceptable approximation,"* not exact prior state, which is why Unwind grades fidelity. Azure's Compensating Transaction Pattern adds the ordering rule: put irreversible steps after all critical validations.
- **Closest prior systems.** **SagaLLM** (VLDB 2025) integrates the Saga pattern into *multi-agent LLM planning* — a framework you author your workflow inside, with compensations defined as part of it. Unwind instead operates on **arbitrary third-party tools nobody authored for it**, at the protocol layer, where compensations must be *inferred*. **GOEX** (Berkeley/Gorilla) proposes runtime rollback and post-facto validation for LLM actions — the honest closest system-level ancestor — but predates MCP's ecosystem scale and provides no reversibility taxonomy, no ecosystem benchmark and no calibrated escalation.
- **Agent-safety benchmarks** (ToolEmu, SafeToolBench, ClawsBench, LITMUS, "Beyond Attack-Success Rate", irreversibility budgeting) *measure* unsafe and irreversible actions but none provide a runtime that classifies reversibility for arbitrary tools and executes recovery.
- **The open call.** "Mind the GAP" argues tool schemas carry no safety metadata and should structurally declare **action reversibility** — an explicit, citable call for exactly what Unwind builds.

## Target venues

The window is Aug–Oct 2026. Honest expectation: arXiv + a workshop acceptance + repo traction is achievable; a full journal publication in this window is not.

| Venue | Fit | Timing (point-in-time, re-verify) |
|---|---|---|
| **arXiv** | Preprint on release tag | On tag |
| **IEEE SaTML 2027** | Best fit — welcomes benchmarks / SoK | Deadline ~Sep 29, 2026 |
| **ICLR 2027** | Main track | Abstract Sep 19 / paper Sep 24, 2026 |
| **NeurIPS 2026 workshops** | Agents / trustworthy ML | Late Sep–Oct 2026 |
| **TMLR** | Rolling, fast archival | Rolling |

## If the results disappoint — the honest pivots

The research is robust to negative results:

- **If classification accuracy is mediocre**, the finding *"tool schemas carry insufficient information to infer reversibility"* directly validates Mind-the-GAP's call and makes the benchmark plus a **proposed MCP schema extension (SEP)** the primary contribution — a stronger result, not a weaker one.
- **If compensation coverage is low**, *"only X% of real MCP mutations are compensable"* is an important, citable ecosystem finding that still justifies the escalation layer.
- **If an official MCP reversibility annotation ships**, Unwind pivots to being the reference implementation and conformance checker, and the benchmark becomes the conformance suite.

*All ecosystem figures, deadlines and spec details are point-in-time as of July 2026 and must be re-verified before submission.*
