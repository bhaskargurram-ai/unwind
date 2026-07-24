# CHANGELOG


## v0.1.0 (2026-07-24)

### Chores

- Bootstrap Apache-2.0 repo, packaging, and tooling config
  ([`2fea179`](https://github.com/bhaskargurram-ai/unwind/commit/2fea1798a79ca1ef2678dccf92a6a04740c8c76f))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

### Continuous Integration

- Full pipeline (lint/type/test matrix, conformance gate, release, PyPI/npm OIDC, docs, docker,
  codeql, scorecard, sbom, signing)
  ([`ed4faf3`](https://github.com/bhaskargurram-ai/unwind/commit/ed4faf3dc9844d49e92aeccd862895a23ae11e21))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

### Documentation

- Community health files, Docker/devcontainer, Makefile, pre-commit, demo assets
  ([`584fe3a`](https://github.com/bhaskargurram-ai/unwind/commit/584fe3a3c67cb6a245fae385fcc8fd5f2ac921c5))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- Mkdocs-material site, taxonomy/compensation/architecture, reversibility index, launch drafts
  ([`a85561b`](https://github.com/bhaskargurram-ai/unwind/commit/a85561b6b553e2504e3c171946041a800a0c0de0))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

### Features

- Durable expiry-aware undo log, escalation policy, and risk calibration
  ([`37b25ce`](https://github.com/bhaskargurram-ai/unwind/commit/37b25cee859ee9df905f34036aed9c0d84d5a115))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **bench**: Reversibench corpus + live sandbox and the five-family eval harness
  ([`20c230f`](https://github.com/bhaskargurram-ai/unwind/commit/20c230fd5c5b60e1652f7283776412db9bf61020))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **classify**: Lexical + schema + LLM ensemble with environment re-derivation
  ([`8a937f7`](https://github.com/bhaskargurram-ai/unwind/commit/8a937f72fd3c69e3427664d20c32c0b00bf2cbee))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **cli**: Typer CLI (run/classify/index/history/undo) and the hermetic undo demo
  ([`c7236a2`](https://github.com/bhaskargurram-ai/unwind/commit/c7236a22b879ae2daedfe3ae532d4280b37a5a45))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **engine**: Reversibility engine, upstream abstraction, and unwind.* agentic MCP surface
  ([`9d8e139`](https://github.com/bhaskargurram-ai/unwind/commit/9d8e139b9c875bbff7c141535eadb17a7b82a143))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **proxy**: Transparent stdio proxy, HTTP mode, byte-faithful passthrough, native elicitation
  ([`a60a1f8`](https://github.com/bhaskargurram-ai/unwind/commit/a60a1f84e678524d05cfdc24498e3080dd6c5691))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **synthesize**: Compensation synthesis, inverse search, sandbox fidelity + blast radius
  ([`20758d2`](https://github.com/bhaskargurram-ai/unwind/commit/20758d293116ae80061e27fa0813067d60c8063a))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **ts**: Typescript stdio shim (unwind-mcp on npm) with faithful passthrough + tests
  ([`180bc1f`](https://github.com/bhaskargurram-ai/unwind/commit/180bc1f7fd417cc3d6b711fc9405099648cfcb50))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

- **types**: Core reversibility types (R0-R4 ordinal scale, plans, undo log)
  ([`24c3ae0`](https://github.com/bhaskargurram-ai/unwind/commit/24c3ae04a01acf132d0f392679eea5e00b4a22f2))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb

### Testing

- Unit suite + mandatory protocol-conformance gate (byte-faithful passthrough)
  ([`95774ab`](https://github.com/bhaskargurram-ai/unwind/commit/95774abb5d8a3fa56659c18773b9ad27430c7279))

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>

Claude-Session: https://claude.ai/code/session_01MVfAxqLHCMCbyBWKQJrBAb
