# Unwind — Launch Checklist & Handoff

Everything below is what remains to take Unwind from a **complete, private repo**
to a **public launch**. The code, tests, docs, demo, TS shim, and benchmark
harness are all done. These are the steps that need *your* accounts / one-time UI
actions (a bot can't or shouldn't do them).

Repo: <https://github.com/bhaskargurram-ai/unwind> (currently **private**).

---

## ⚠️ READ FIRST — GitHub Actions is out of quota (billing, not code)

**CI passed fully green on commit `2ea130c`** — all 14 jobs (lint, mypy, the
3×3 OS/Python test matrix, the mandatory protocol-conformance gate, and the
TypeScript build). You can see that green run in the Actions tab.

**After that, GitHub Actions stopped running** and later runs fail in ~7 seconds
with *zero* steps executed. The exact reason (from the run annotations) is:

> *"The job was not started because recent account payments have failed or your
> spending limit needs to be increased. Please check the 'Billing & plans'
> section in your settings."*

This is **not a code or workflow problem** — the pipeline is proven correct. It's
that a **private** repo meters Actions minutes (macOS bills 10×, Windows 2×), and
the initial burst of Dependabot + every-workflow runs drained the monthly quota.

**Two ways to make CI green again (pick one):**
1. **Go public** (the plan anyway) — public repos get *free unlimited* Actions.
   The moment you flip visibility, CI runs and goes green. *(Recommended.)*
2. **Raise the Actions spending limit** — GitHub → Settings → Billing & plans →
   Actions → set a spending limit (even a few dollars restores it immediately).

To reduce burn in the meantime, I already: cancelled in-flight runs, slimmed the
test matrix (9→5 jobs; full 3×3 is proven and restored at launch), made Docker
amd64-only except on tags, moved Benchmark to PR-only, set Dependabot to monthly
+ minor/patch-only, and gated CodeQL/Scorecard/Pages to public.

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
- [ ] OpenSSF **Scorecard** + **Benchmark** trend + **CodeQL** + **Pages** deploy
      all auto-activate on public (they're gated on `repository.visibility`).
- [ ] Optionally widen `ci.yml`'s `test` matrix back to the full 3×3 (list
      `macos-latest` and `windows-latest` under `matrix.os` and drop the
      `include:`) and set Docker `platforms` back to multi-arch on push — cheap
      once Actions is free on public.

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
