# Governance

This document describes how decisions get made in the Unwind project. It is
intentionally lightweight — the project is young — and will evolve as the community
grows.

## Model

Unwind currently follows a **BDFL-style** model with an active maintainer team.

- **Project lead / BDFL:** Bhaskar Gurram ([@bhaskargurram-ai](https://github.com/bhaskargurram-ai)).
  Holds final say on direction, scope, and any decision that cannot be resolved by
  consensus, and is the tie-breaker of last resort.
- **Maintainers:** contributors with commit and review rights, listed in
  [`CODEOWNERS`](./CODEOWNERS). Maintainers review PRs, triage issues, and steward
  their areas (proxy, classify, synthesize, undolog, policy, bench, eval, docs, ts).

As the contributor base matures, we intend to migrate toward a steering-committee model
with documented voting; this file will be updated when that happens.

## Guiding principles (non-negotiable)

Decisions are measured against the thesis and golden rules in [`CLAUDE.md`](./CLAUDE.md)
and [`PROJECT.md`](./PROJECT.md). These constrain governance itself:

1. **Reversibility inference is the product.** Every feature must sharpen the R0–R4
   classification or exploit it. Features that do neither are out of scope.
2. **Transparency is sacred.** The proxy must be invisible when idle and pass unknown
   methods through byte-faithfully.
3. **Fail safe, never fail open.** Uncertainty escalates to a human.
4. **Never over-promise reversibility.** Fidelity is graded, never boolean.
5. **We are not a gateway.** Auth, RBAC, rate limiting, secret scanning, and container
   isolation are permanently out of scope. No governance process can adopt them —
   that space is saturated and is deliberately not ours.

## How decisions are made

We prefer **lazy consensus**: a proposal that draws no sustained objection within a
reasonable window is accepted.

| Decision size | Process |
|---------------|---------|
| Bug fixes, docs, small changes | Open a PR; one maintainer approval; merge. |
| New features / behavior changes | Open an issue or [Discussion → Ideas](https://github.com/bhaskargurram-ai/unwind/discussions/categories/ideas) first; reach rough consensus; then PR. |
| Design/architecture changes, scope questions, class-boundary or fidelity-grading changes | Discussion thread, then maintainer consensus. If it affects the paper's claims (a class boundary, how fidelity is graded, how blast radius is estimated), it requires a `# DECISION:` comment in code and a test pinning the behavior. |
| Anything unresolved | The project lead decides. |

Substantial disagreements are settled in the open, on GitHub, so the reasoning is
recorded.

## Becoming a maintainer

Maintainers are invited based on a sustained track record of high-quality
contributions, sound reviews, and alignment with the project's principles. There is no
fixed contribution count. Express interest in Discussions or to the project lead.
Maintainers who become inactive for an extended period may be moved to emeritus status
(with thanks) to keep the active roster accurate.

## Release process

- Trunk-based; `main` is always green.
- Versioning is **automated from Conventional Commits** via `python-semantic-release`
  on merge to `main` (see [`CONTRIBUTING.md`](./CONTRIBUTING.md)).
- Tags `v*` trigger PyPI (Trusted Publishing/OIDC), npm (`--provenance`), Docker
  (GHCR), SBOM generation, and Sigstore signing.
- Semantic versioning; the [`CHANGELOG.md`](./CHANGELOG.md) follows Keep a Changelog.

## Deprecation policy

We aim to keep Unwind dependable for the clients and servers it wraps.

- **Public Python/TS API and CLI:** deprecations are announced in the CHANGELOG and
  emit a runtime deprecation warning for at least **one minor release** before removal.
  Breaking removals happen only on a **major** version bump (post-1.0). During `0.x`,
  breaking changes may occur in minor releases but will always be called out in the
  CHANGELOG with a migration note.
- **Protocol/proxy behavior:** transparency and passthrough fidelity are covered by the
  mandatory conformance suite and are treated as stable contracts, not subject to
  casual change.
- **Reversibility taxonomy & fidelity grades:** changes to class boundaries or grade
  definitions are versioned, documented in the CHANGELOG, and pinned by tests, because
  downstream benchmark results depend on them.

## Code of Conduct

All participation is governed by the [Code of Conduct](./CODE_OF_CONDUCT.md), enforced
by the maintainers. Reports go to `security@zasti.ai`.
