# Unwind — Launch Checklist & Handoff

Everything below is what remains to take Unwind from a **complete, green, private
repo** to a **public launch**. The code, tests, CI, docs, demo, TS shim, and
benchmark harness are all done and passing. These are the steps that need *your*
accounts / one-time UI actions (a bot can't or shouldn't do them).

Repo: <https://github.com/bhaskargurram-ai/unwind> (currently **private**).

---

## 0. State at handoff (already done)
- ✅ Python package `unwind-mcp` — transparent MCP proxy, R0–R4 classifier,
  compensation synthesis, durable undo log, escalation policy, `unwind.*` agentic tools.
- ✅ Works against **real** MCP servers (verified live vs `@modelcontextprotocol/server-filesystem`).
- ✅ TypeScript stdio shim in `ts/` (`unwind-mcp` on npm), 51 tests passing.
- ✅ ReversiBench (`bench/`) + 5-family eval harness (`eval/`) with hand-computed fixtures.
- ✅ Full CI/CD: lint/type/test matrix (3 OS × 3 Py), mandatory conformance gate,
  CodeQL, Docker→GHCR, release, PyPI/npm (OIDC), docs, SBOM, signing — all wired.
- ✅ MkDocs-Material docs site (builds `--strict`), demo SVG, community-health files.
- ✅ 300+ tests green; ruff + black + mypy --strict clean.
- ✅ Research paper scaffolded in `paper/` and **hard-gitignored** (never committed).

## 1. External service setup (one-time, needs your accounts)
- [ ] **PyPI Trusted Publisher**: create the `unwind-mcp` project on PyPI → *Publishing* →
      add a GitHub trusted publisher: owner `bhaskargurram-ai`, repo `unwind`,
      workflow `pypi-publish.yml`. No token needed (OIDC).
- [ ] **npm**: create the `unwind-mcp` package; add `NPM_TOKEN` repo secret
      (or wait for npm OIDC GA and drop it — `npm-publish.yml` already sets `--provenance`).
- [ ] **Codecov**: link the repo at codecov.io (public repos need no token; else add `CODECOV_TOKEN`).
- [ ] **Discord**: create a server + invite; replace the `TBD` invite link in
      `README.md`, `SUPPORT.md`, `docs/`.
- [ ] **GitHub Sponsors**: enable; `.github/FUNDING.yml` already points to `bhaskargurram-ai`.
- [ ] **Zenodo**: enable the GitHub↔Zenodo integration so a DOI is minted on release;
      paste the DOI badge into `README.md` + `CITATION.cff`.

## 2. Flip to public (launch day)
- [ ] `gh repo edit bhaskargurram-ai/unwind --visibility public --accept-visibility-change-consequences`
- [ ] Enable **GitHub Pages** (Settings → Pages → Source: GitHub Actions). The
      `docs.yml` deploy job auto-activates once public (it's gated on visibility).
- [ ] Enable **branch protection** on `main` (requires Pro or public): require the
      `CI success` check + ≥1 review. (A ready API call is in section 5.)
- [ ] Upload a **social preview** image (Settings → General → Social preview), 1280×640.
- [ ] OpenSSF **Scorecard** + **Benchmark** trend workflows auto-activate on public.

## 3. First release
- [ ] Confirm CI is green on `main`.
- [ ] Re-enable automatic releases: in `.github/workflows/release.yml`, change the
      trigger from `workflow_dispatch:` back to `push: branches: [main]` (a one-line
      revert of the pre-launch guard), **or** just run the Release workflow manually once.
- [ ] The `v0.1.0` tag already exists (auto-created). Deleting + re-cutting it after
      Trusted Publishing is configured will publish to PyPI; or bump to `v0.1.1`.
- [ ] Verify the PyPI + npm + GHCR artifacts published and the Sigstore signatures attached.

## 4. Announce
- [ ] Post the drafts in `docs/launch/` (Show HN, Reddit r/LocalLLaMA + r/mcp, X thread).
      They lead with the thesis + the honest demo, no fabricated numbers.
- [ ] Submit Unwind to MCP registries/catalogs (Glama, the official MCP registry,
      MCPJungle) — see `docs/integrations.md`.
- [ ] Open the "integrate as middleware" PRs against Docker MCP Gateway / ToolHive /
      agentgateway (turns competitors into distribution — `PROJECT.md` §13).

## 5. Handy commands
```bash
# Make public
gh repo edit bhaskargurram-ai/unwind --visibility public --accept-visibility-change-consequences

# Branch protection (after public / Pro)
gh api -X PUT repos/bhaskargurram-ai/unwind/branches/main/protection \
  -H "Accept: application/vnd.github+json" \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[checks][][context]=CI success' \
  -F 'enforce_admins=false' \
  -F 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F 'restrictions=null'

# Cut a release manually
gh workflow run release.yml --repo bhaskargurram-ai/unwind
```

## 6. Research paper (private)
- [ ] Run `paper/experiments/run_classification.py` + `run_escalation.py` on RunPod
      (see `paper/README.md`) to populate real numbers, then `make results`.
- [ ] Fill `paper/main.tex`; post to arXiv; the `CITATION.cff` + Zenodo DOI link back.
- Reminder: `paper/` stays gitignored — never `git add -f` it.
