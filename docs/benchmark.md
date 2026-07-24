---
title: ReversiBench
---

# ReversiBench

ReversiBench is the evaluation core of the project: a **labelled corpus of real MCP tools** annotated with reversibility class, compensation availability, blast radius and reversibility half-life, plus a **live sandbox harness** where forward+inverse pairs actually execute and state-equivalence is verified. It is what turns Unwind's claims into measurements — and it is a publishable artifact in its own right.

!!! warning "All concrete numbers on this page are TBD"
    ReversiBench is under construction. Every headline number — coverage, fidelity distributions, Critical Error Rate, Interruptions@1% damage — is reported here as **TBD** and will be filled in from `make results` against pinned configs, with bootstrap 95% CIs. Nothing on this page should be cited as a result yet.

## Corpus construction

- **Sample from ecosystem scale.** The corpus draws from a catalog crawl of public MCP servers (the ecosystem is on the order of ~2,031 servers / ~31,000 tools). We commit the **crawler and content hashes**, never the scraped payloads.
- **Stratify by domain.** Sampling is stratified across files, VCS, DB, comms, payments, CRM, cloud and calendar, so the benchmark is **cross-vertical by construction** rather than dominated by one easy domain.
- **Dataset card.** Sources, licences and splits are documented in `bench/card.md`.

## Splits — server-disjoint, or the paper is dead

!!! danger "Splits are server-disjoint, never tool-disjoint within a server"
    Sibling tools on the same server share lexical patterns (`create_page` / `update_page` / `delete_page`). Splitting tool-disjoint *within* a server leaks those patterns from train into test and inflates every number. ReversiBench splits **server-disjoint** across train / calibration / test. **Calibration thresholds are fit only on the calibration split, never on test.**

## Labelling and inter-annotator agreement

- **≥2 independent annotators** on a stratified sample.
- Report **ordinal** inter-annotator agreement — **Krippendorff's α** and/or **Fleiss' κ** — because the R-scale is ordinal (an R4↔R3 disagreement is smaller than R4↔R0).
- **Publish the annotation guide**, adjudicate disagreements, and report the disagreement rate.

## The live sandbox — fidelity is measured, not asserted

!!! success "Fidelity claims come from the live sandbox"
    Rollback fidelity is graded by **actually executing forward + inverse against a real server and diffing the resulting state** — never from a model asserting that an undo should work. The sandbox composes real servers (filesystem, git, sqlite) with in-repo mock comms/payments servers, in isolated instances.

## The five metric families

=== "A · Classification"

    - **Macro-F1** and **per-class F1** over R0–R4.
    - **Ordinal MAE** on the R-scale (R4→R3 is a smaller error than R4→R0).
    - **Critical Error Rate (CER)** — fraction of true-R4 actions classified ≤R2. **This is the headline safety metric** — the asymmetric-loss number that everything else is subordinate to.
    - **Binary AUROC / AUPR** for irreversible-vs-not.
    - **Environment sensitivity** — Δ in class assignment when the environment descriptor changes (git-backed vs versionless), validating [environment-relativity](concepts/taxonomy.md#environment-relativity-class-is-ftool-environment).

    | Metric | Value |
    |---|---|
    | Macro-F1 | TBD |
    | Ordinal MAE | TBD |
    | **Critical Error Rate** | **TBD** |
    | Binary AUROC | TBD |
    | Environment sensitivity Δ | TBD |

=== "B · Compensation"

    - **Compensation coverage** — % of mutating tools receiving a candidate inverse.
    - **Compensation validity** — % of synthesised inverses that execute without error.
    - **Rollback fidelity** — graded exact / semantic / acceptable-approximation / failed. *Never a single "undo worked" number.*
    - **Residue rate** — % of undos leaving detectable side effects.
    - **Half-life accuracy** — predicted vs actual reversibility window.

    | Metric | Value |
    |---|---|
    | Coverage | TBD |
    | Validity | TBD |
    | Fidelity (exact / semantic / approx / failed) | TBD / TBD / TBD / TBD |
    | Residue rate | TBD |
    | Half-life accuracy | TBD |

=== "C · Escalation policy"

    Selective prediction with asymmetric loss — reuses the calibration machinery deliberately.

    - **Interruption–damage curve** — interruptions per session vs irreversible-damage rate (the risk–coverage analogue).
    - **E-AURC** on that curve — unitless, comparable across systems.
    - **Interruptions@1% damage** — **the headline product number**: how rarely we interrupt while letting through ≤1% of irreversible actions unconfirmed.
    - **Damage@AutoApprove(k)** — leakage under a fixed auto-approve budget.
    - **ECE / Adaptive ECE** on risk scores, with a reliability diagram.
    - **FPR@95%TPR** — needless interruptions when catching 95% of irreversible actions (a direct fatigue proxy).

    | Metric | Value |
    |---|---|
    | **Interruptions@1% damage** | **TBD** |
    | E-AURC | TBD |
    | ECE / Adaptive ECE | TBD |
    | FPR@95%TPR | TBD |

=== "D · System"

    - Added latency per call, p50/p95, split **R0 (must be ~free)** vs mutating.
    - End-to-end undo latency and success rate.
    - **Compatibility rate** — % of tested client×server pairs working unmodified. *Adoption depends on this being ~100%.*

    | Metric | Value |
    |---|---|
    | Added latency R0 (p50/p95) | TBD / TBD |
    | Added latency mutating (p50/p95) | TBD / TBD |
    | End-to-end undo latency / success | TBD / TBD |
    | **Compatibility rate** | **TBD** |

=== "E · End-to-end"

    On destructive-scenario suites (adapting ToolEmu, ClawsBench, AgentDojo-style traces):

    - **Damage prevented**.
    - **Task completion preserved** — does the guard break ordinary work?
    - The resulting **safety–utility frontier** — a guard that stops all damage by blocking everything is worthless; the frontier is the honest reporting format.

    | Metric | Value |
    |---|---|
    | Damage prevented | TBD |
    | Task completion preserved | TBD |
    | Safety–utility frontier | TBD |

## Statistical protocol

- **Bootstrap 95% CIs on every headline number.** Paired tests for system comparisons.
- **Pin everything**: model versions, seeds, server commit hashes.
- **Reproducibility**: `make results` regenerates every table and figure from pinned configs; generated tables are checked into `paper/`.

## Why the benchmark is itself a contribution

Nobody has published an ecosystem-scale, environment-relative, live-validated reversibility benchmark. Even if the classifier or the synthesiser under-performs, ReversiBench answers an unanswered empirical question — *which of the real ecosystem's tools are even compensable?* — and that finding stands on its own. See the [paper](paper.md).
