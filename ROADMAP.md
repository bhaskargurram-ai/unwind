# Roadmap

This roadmap tracks Unwind against the build plan in [`PROJECT.md`](./PROJECT.md) §11
and then looks past launch. It is a statement of intent, not a promise of dates —
priorities shift as we learn from the ecosystem and from you. Ideas and reprioritization
requests are welcome in [Discussions](https://github.com/bhaskargurram-ai/unwind/discussions/categories/ideas).

Legend: ✅ done · 🚧 in progress · ⬜ planned

## Phase 1 — the runtime (8-week build, `PROJECT.md` §11)

Each week has a Definition of Done (DoD); we do not advance until it is met and CI is
green.

### W1 — Transparent proxy 🚧
- Stdio shim wrapping a server, forwarding every method untouched.
- Verified against `modelcontextprotocol/server-filesystem` with MCP Inspector.
- Passthrough conformance tests for every method; `--passthrough-only` panic switch.
- **DoD:** Claude Desktop behaves identically with Unwind in the path; conformance
  suite green.

### W2 — Classification v1 + catalog crawler ⬜
- `unwind/types.py`: `ReversibilityClass`, `ToolSpec`, `CompensationPlan`, `UndoEntry`,
  `EnvironmentDescriptor`, `Decision`.
- Lexical + schema-structural classifiers; catalog crawler over public servers; first
  ~300 tools hand-labelled.
- **DoD:** `unwind classify <server>` prints an R-scale table.

### W3 — Undo log + pre-state capture + `unwind.undo` ⬜ *(the demo must work this week)*
- Durable, expiry-aware, cross-server undo log (SQLite; survives restart).
- Snapshot-before-mutate; R1 undo end-to-end on filesystem & sqlite.
- **DoD:** the 20-second demo works — agent overwrites files, `unwind.undo` restores
  them.

### W4 — Compensation synthesis + sandbox validation ⬜
- Effect typing, inverse-candidate search (antonym + entity + schema-compat), pre-state
  planning, plan emission.
- Live sandbox forward+inverse execution with **graded** fidelity (exact / semantic /
  acceptable-approximation / failed) and residue reporting.
- **DoD:** R2 undo works on ≥2 real servers; coverage/validity/fidelity measured.

### W5 — Escalation policy + elicitation + calibration ⬜
- LLM classifier with self-consistency; calibration (temperature/isotonic/conformal);
  damage-rate threshold solver.
- Confirmations over **native MCP elicitation** (MRTR / SEP-2322) — no bespoke UI.
- Blast-radius read-probes.
- **DoD:** first interruption–damage curve.

### W6 — ReversiBench + full metric harness ⬜
- Scale labelling with ≥2 annotators; ordinal IAA (Krippendorff's α / Fleiss' κ);
  published annotation guide.
- **Server-disjoint** train/calibration/test splits; destructive scenario suite.
- All five metric families with bootstrap 95% CIs; `make results` reproduces
  everything from pinned configs.
- **DoD:** all five metric families reported with CIs.

### W7 — Polish + TypeScript stdio shim + launch ⬜
- README with the demo GIF, one-line install, PyPI + npm publish, docs site,
  `good-first-issue` labels.
- **DoD:** `v0.1.0` tagged and published.

### W8 — Paper ⬜
- Write against auto-generated tables/figures; arXiv preprint; venue submission.
- **DoD:** preprint live, submission in.

## Phase 2 — post-launch

Ordered by priority, not committed to dates.

- ⬜ **ReversiBench v1** — publish the labelled corpus, the live sandbox harness, and
  the dataset card (sources, licenses, server-disjoint splits) as a citable artifact.
- ⬜ **Reversibility index** — a browsable, linkable R-class catalog of popular MCP
  servers, SEO-durable and independently useful even to non-users. It *is* the
  benchmark, shipped as a public artifact.
- ⬜ **TypeScript HTTP client** — extend the TS port beyond the stdio shim to
  Streamable HTTP, doubling the addressable audience.
- ⬜ **Gateway integration PRs** — land Unwind as optional recovery middleware inside
  Docker MCP Gateway, ToolHive, and agentgateway. Integrate, don't compete: convert
  gateways into distribution.
- ⬜ **Expanded environment descriptors** — richer capability modelling (retention
  windows, soft-delete, version control) so classes re-derive accurately across more
  backends.
- ⬜ **Reversibility half-life modelling** — predict and surface time-decaying undo
  windows in the log and in `unwind.explain_risk`.
- ⬜ **Proposed MCP schema extension (SEP)** — if schema-level reversibility metadata
  gains traction upstream, pivot to being the reference implementation and conformance
  checker.

## Explicitly out of scope — forever

To keep the project sharp, these will not be built, no matter how often requested:

- Authentication, authorization, RBAC.
- Rate limiting, quota management.
- Secret scanning / injection, container isolation.

That space is saturated (Docker MCP Gateway, ToolHive, agentgateway, ContextForge, Kong,
Pomerium, and others). Unwind does the one thing none of them do: **recovery**. See the
["Not a gateway"](./README.md#not-a-gateway) note.

---

Want to influence the order, or pick something up? Comment on the roadmap discussion or
grab a [`good first issue`](https://github.com/bhaskargurram-ai/unwind/labels/good%20first%20issue).
