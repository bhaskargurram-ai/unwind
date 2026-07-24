# Security Policy

Unwind sits in the trust path between an AI agent and the servers it acts on, so we
take its security posture seriously. Thank you for helping keep it and its users safe.

## Supported versions

Unwind is in early beta. Security fixes land on the latest `0.x` minor series; we
publish patched releases from `main`.

| Version | Supported |
|---------|:---------:|
| `0.1.x` (latest) | ✅ |
| `< 0.1` (pre-release) | ❌ |

Once `1.0` ships, this table will list the maintained majors. We recommend always
running the latest published release.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Report privately through either channel:

1. **GitHub Security Advisories** — use
   ["Report a vulnerability"](https://github.com/bhaskargurram-ai/unwind/security/advisories/new)
   on the repository's Security tab (preferred; keeps the disclosure coordinated).
2. **Email** — `security@zasti.ai`. Encrypt if you can; we will reply with a key on
   request.

Please include:

- a description of the issue and its impact,
- affected version(s) and platform,
- reproduction steps or a proof of concept,
- any suggested remediation.

Especially valuable are reports where Unwind **fails open** rather than safe — e.g. a
crafted tool or response that causes an irreversible action to be auto-allowed without
escalation, or a passthrough path that leaks or mutates traffic it should forward
byte-faithfully. Those are the failure modes the project exists to prevent.

## Response-time expectations

| Stage | Target |
|-------|--------|
| Acknowledge receipt | within **48 hours** |
| Initial assessment & severity triage | within **5 business days** |
| Fix or mitigation for confirmed high/critical issues | within **30 days** |
| Coordinated public disclosure | after a fix is released, by mutual agreement |

We follow coordinated disclosure. We will keep you updated on progress, credit you in
the advisory and release notes (unless you prefer to remain anonymous), and let you
know when the fix ships. We do not currently operate a paid bug-bounty program.

## Release integrity

Releases are engineered to be verifiable end to end:

- **Sigstore keyless signing.** Release artifacts (Python and npm distributions) are
  signed with [Sigstore](https://www.sigstore.dev/)/cosign; signatures (`.sig` /
  bundle) are attached to each GitHub release.
- **PyPI Trusted Publishing (OIDC).** The PyPI package `unwind-mcp` is published via
  GitHub OIDC with no long-lived token — provenance is attested by the workflow.
- **npm provenance.** The npm package is published with `--provenance`.
- **SBOM.** A CycloneDX Software Bill of Materials is generated and attached to each
  tagged release.

Verify a downloaded artifact's Sigstore signature before trusting it in sensitive
environments. Instructions accompany each release.

## Scope

In scope: the `unwind` proxy, its classification/synthesis/undo-log/policy code, the
CLI, the Python package `unwind-mcp`, the TypeScript shim, and the published Docker
image. Out of scope: vulnerabilities in upstream MCP servers Unwind wraps, in MCP
clients, or in third-party dependencies (report those upstream, though we appreciate a
heads-up so we can pin or patch).
