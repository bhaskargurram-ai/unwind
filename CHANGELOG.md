# Changelog

All notable changes to Unwind are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Releases are produced automatically from [Conventional Commits](https://www.conventionalcommits.org/)
via `python-semantic-release`; entries below are grouped accordingly.

## [Unreleased]

_Changes on `main` that have not yet been released will appear here._

## [0.1.0] - 2026-07-23

The first public beta of Unwind — the reversibility layer for agentic tool use.

### Added

- **Transparent MCP proxy (stdio).** Wrap any upstream server with
  `unwind run -- <upstream cmd>`. Any method Unwind does not understand is forwarded
  byte-faithfully; `--passthrough-only` acts as a panic switch that disables all
  classification.
- **Reversibility taxonomy (R0–R4).** Ordinal `ReversibilityClass` with
  environment-relative assignment — the same tool can be R1 on a git-backed tree and R4
  on a versionless one.
- **Core typed protocol objects** in `unwind/types.py`: `ToolSpec`,
  `CompensationPlan`, `UndoEntry`, `EnvironmentDescriptor`, `Decision`, and the
  fidelity/outcome enums.
- **Classification v1.** Lexical (verb/noun) and schema-structural signals to infer a
  tool's reversibility class at `tools/list` time, cached so R0 reads stay ~free.
- **Durable cross-server undo log.** SQLite-backed, expiry-aware, survives process
  restart, with pre-state capture (snapshot-before-mutate).
- **`unwind.undo` and the agentic tool surface.** Unwind is itself an MCP server
  exposing `unwind.preview`, `unwind.undo`, `unwind.explain_risk`, `unwind.history`,
  and `unwind.checkpoint`, so the agent can reason about and reverse its own actions.
- **Fail-safe escalation.** Unknown tool, failed classification, timeout, or crashed
  classifier all escalate to a human — never auto-allow on uncertainty.
- **Graded fidelity reporting.** Rollback fidelity is reported as
  exact / semantic / acceptable-approximation / failed, with residue, never as a
  boolean — Unwind never over-promises undo.
- **CLI** (`unwind`) via Typer, packaged for PyPI as `unwind-mcp`.
- **Community & project scaffolding.** README, contributing guide, code of conduct,
  security policy, governance, roadmap, issue/PR templates, and full CI/CD (lint,
  typecheck, matrix tests, mandatory protocol-conformance gate, CodeQL, OpenSSF
  Scorecard, Sigstore signing, SBOM, PyPI/npm/Docker publishing).

[Unreleased]: https://github.com/bhaskargurram-ai/unwind/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bhaskargurram-ai/unwind/releases/tag/v0.1.0
