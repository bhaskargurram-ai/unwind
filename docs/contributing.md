---
title: Contributing
---

# Contributing

Contributions are welcome — code, benchmark annotations, gateway integrations, and reversibility-index ratings. This page is a quick pointer; the authoritative source is [`CONTRIBUTING.md`](https://github.com/bhaskargurram-ai/unwind/blob/main/CONTRIBUTING.md) in the repository root.

## Dev setup

```bash
git clone https://github.com/bhaskargurram-ai/unwind
cd unwind
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,metrics,docs]"
pre-commit install
```

A one-click environment is available via the checked-in `.devcontainer/` (GitHub Codespaces / Gitpod).

## The gates (Definition of Done per PR)

Every PR must be green on all of these before it can merge — `main` is always green:

- [x] **ruff** + **black** + **mypy** (strict) + **pytest** in CI.
- [x] **The protocol-conformance suite** — mandatory and non-negotiable. A proxy that breaks a client is worthless, so passthrough fidelity is tested against every supported server (`pytest -m protocol`).
- [x] **New code has tests.** Metric code additionally needs a **numeric regression test** against a hand-computed fixture. `eval/` coverage ≥ 80%.
- [x] **Docs updated** when public API or protocol behaviour changes (`README.md` / `PROJECT.md` / these docs).
- [x] **Conventional Commit** messages (`feat:`, `fix:`, `bench:`, `docs:`, `test:`, `refactor:`, `chore:`, `perf:`).

```bash
make lint      # ruff + black --check + mypy
make test      # pytest incl. the protocol-conformance gate
make results   # regenerate benchmark tables from pinned configs
make demo      # run the 20-second demo
```

## Git workflow

Trunk-based. Branch from `main` as `feat/<module>`, open a PR, squash-merge. Semantic-version tags trigger the PyPI/npm/GHCR publish. **Never commit crawled server data, credentials, or sandbox state** — commit the crawlers and content hashes only.

## The golden rules (read before proposing a design change)

Contributions are held to the project's [golden rules](faq.md). The short form:

1. **Transparency is sacred** — unknown methods pass through byte-faithfully; `--passthrough-only` always works.
2. **Fail safe, never fail open** — uncertainty escalates to the human; the default class is R4.
3. **Never over-promise reversibility** — fidelity is graded, low-confidence compensations degrade and escalate.
4. **Compensation is semantic, not bitwise** — grade fidelity, always report residue.
5. **Reversibility is `f(tool, environment)`** — never tool alone.
6. **We are not a gateway** — auth / RBAC / rate limiting / secret scanning / isolation are permanently out of scope.
7. **R0 reads stay ~free** — classify at `tools/list` time and cache.

If a change affects a paper claim (a class boundary, a fidelity grade, a blast-radius estimate), leave a `# DECISION:` comment explaining the reasoning and add a test pinning the behaviour.

## Good first contributions

- **Reversibility-index ratings** — add a server to `bench/catalog/` with the labelling pipeline (≥2 annotators, ordinal IAA, live-sandbox fidelity). See the [Reversibility Index](reversibility-index.md).
- **Client configs** — a working `mcp.json` for a client not yet in the [Quickstart](quickstart.md).
- **Gateway middleware adapters** — wire Unwind into a gateway not yet covered in [Integrations](integrations.md).
- **Conformance tests** — a passthrough test for a new upstream server.

Look for issues labelled `good-first-issue` on the [issue tracker](https://github.com/bhaskargurram-ai/unwind/issues).
