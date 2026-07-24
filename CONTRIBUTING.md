# Contributing to Unwind

Thanks for wanting to help build the reversibility layer for agentic tool use. This
guide gets you from a clean clone to a green PR. Please read [`CLAUDE.md`](./CLAUDE.md)
and [`PROJECT.md`](./PROJECT.md) first — they carry the thesis and the golden rules
that every change must respect (transparency is sacred; fail safe, never fail open;
never over-promise reversibility; we are not a gateway).

## Table of contents

- [Code of Conduct](#code-of-conduct)
- [Development setup](#development-setup)
- [Makefile targets](#makefile-targets)
- [Branching & commits](#branching--commits)
- [The mandatory CI gates](#the-mandatory-ci-gates)
- [Pull request process](#pull-request-process)
- [Developer Certificate of Origin (DCO)](#developer-certificate-of-origin-dco)
- [Good first issues](#good-first-issues)

## Code of Conduct

This project is governed by the [Contributor Covenant](./CODE_OF_CONDUCT.md). By
participating you agree to uphold it. Report unacceptable behavior to
`security@zasti.ai`.

## Development setup

Unwind uses [**uv**](https://docs.astral.sh/uv/) for fast, reproducible environments.
Python **>=3.11** is required.

```bash
# 1. Clone
git clone https://github.com/bhaskargurram-ai/unwind.git
cd unwind

# 2. Create a virtualenv and install the package with dev extras
uv venv --python 3.11
uv pip install -e ".[dev]"

# ...or install everything you might touch:
uv pip install -e ".[dev,docs,metrics,llm]"    # or: make install

# 3. Install the git hooks (runs ruff/black/mypy + the paper guard on commit)
pre-commit install

# 4. Sanity-check
make lint typecheck test conformance
```

> `pip install -e ".[dev]"` works too if you prefer stdlib venvs — uv is a
> recommendation, not a requirement.

### The TypeScript shim (`ts/`)

The stdio shim has a TypeScript port published as `unwind-mcp` on npm.

```bash
cd ts
npm ci
npm run build
npm test
```

### The Docker sandbox

Integration and fidelity tests run against real MCP servers in Docker:

```bash
make sandbox-up      # docker compose up: filesystem, git, sqlite, mock comms/payments
make test            # unit tests (fast)
pytest -m integration   # the sandbox-backed suite
make sandbox-down
```

## Makefile targets

| Target | What it does |
|--------|--------------|
| `make install` | `uv pip install -e ".[dev,docs,metrics]"` |
| `make lint` | `ruff check` + `ruff format --check` |
| `make fmt` | auto-fix: `ruff format` + `black` |
| `make typecheck` | `mypy --strict` on `unwind/` |
| `make test` | `pytest` (excludes `integration` and `slow`) |
| `make conformance` | `pytest -m protocol` — the mandatory protocol gate |
| `make bench` | `pytest-benchmark` |
| `make cov` | tests with coverage report |
| `make demo` | run the 20-second demo script |
| `make docs` / `make docs-build` | mkdocs serve / build |
| `make sandbox-up` / `make sandbox-down` | bring the Docker sandbox up/down |
| `make clean` | remove build/test artifacts |

Run `make help` for the full list.

## Branching & commits

- Trunk-based development. `main` is **always green** — never merge a red build.
- Short-lived branches off `main`, named by area:
  - `feat/<module>` — a new capability (e.g. `feat/blast-radius`)
  - `fix/<module>` — a bug fix (e.g. `fix/passthrough-notification`)
  - also `docs/…`, `test/…`, `refactor/…`, `chore/…`, `perf/…`, `bench/…`
- PRs are **squash-merged**. Keep them focused.

### Conventional Commits

Every commit **and** every squashed PR title must follow
[Conventional Commits](https://www.conventionalcommits.org/). Versioning is
automated from these messages via `python-semantic-release`, so the prefix
determines the next release:

| Prefix | Meaning | Version bump |
|--------|---------|--------------|
| `feat:` | new feature | minor |
| `fix:` | bug fix | patch |
| `perf:` | performance improvement | patch |
| `docs:` / `test:` / `refactor:` / `chore:` / `bench:` | no release | none |
| `feat!:` or a `BREAKING CHANGE:` footer | breaking change | major (post-1.0) |

Examples:

```text
feat(classify): add schema-compatibility signal to inverse search
fix(proxy): forward unrecognised notifications byte-faithfully
bench(sandbox): add sqlite forward+inverse fidelity fixture
```

## The mandatory CI gates

Every PR must pass **all** of these before it can merge. There are no exceptions —
`main` stays green.

1. **`ruff check` + `ruff format --check`** — lint & formatting.
2. **`black --check`** — formatting (belt and suspenders with ruff format).
3. **`mypy --strict`** on `unwind/` — full type safety.
4. **`pytest`** across the OS × Python matrix (Linux/macOS/Windows × 3.11/3.12/3.13).
5. **`pytest -m protocol`** — the **protocol-conformance suite**. This is
   **non-negotiable**: a proxy that breaks a client is worthless. Any method Unwind
   does not understand must be forwarded byte-faithfully, and `--passthrough-only`
   must always work as a panic switch. Changes that touch the proxy path *will* be
   scrutinized here.
6. **`ts`** — the TypeScript shim builds and tests on Node 22.

Locally, `make lint typecheck test conformance` covers 1–5.

### Non-negotiable design rules for reviewers

- **Fail safe, never fail open.** Unknown tool / failed classification / timeout →
  escalate to the human. Never auto-allow on uncertainty.
- **Never over-promise reversibility.** Fidelity is graded (exact / semantic /
  acceptable-approximation / failed), never a boolean. Low-confidence compensations
  degrade a class and escalate.
- **R0 calls must stay ~free.** Classify at `tools/list` time and cache. Do not add
  latency to reads.
- **We are not a gateway.** PRs adding auth/RBAC/rate-limiting/secret-scanning will be
  declined — that is permanent, deliberate scope.
- **New code has tests.** Metric code needs a numeric regression test against a
  hand-computed fixture; `eval/` coverage must stay ≥ 80%.
- **Public API or protocol behavior changes** must update `README.md` / `PROJECT.md`.
- **Never commit** crawled server data, credentials, sandbox state, or anything under
  `paper/` (it is gitignored and guarded by a pre-commit hook).

## Pull request process

1. Open (or comment on) an issue describing the change first, for anything larger than
   a typo — it saves you from building something out of scope.
2. Branch, implement, add tests, run `make lint typecheck test conformance`.
3. Fill in the [PR template](./.github/PULL_REQUEST_TEMPLATE.md) checklist.
4. Ensure your commits are signed off (see DCO below).
5. A maintainer reviews; address feedback; we squash-merge with a Conventional Commit
   title.

## Developer Certificate of Origin (DCO)

We use the [DCO](https://developercertificate.org/) instead of a CLA. Sign off each
commit to certify you have the right to submit it under Apache-2.0:

```bash
git commit -s -m "feat(policy): add damage-rate threshold solver"
```

This appends a `Signed-off-by: Your Name <you@example.com>` trailer. Set your identity
with `git config user.name` / `git config user.email` beforehand. PRs with unsigned
commits will be asked to amend.

## Good first issues

New here? Look for the
[`good first issue`](https://github.com/bhaskargurram-ai/unwind/labels/good%20first%20issue)
and [`help wanted`](https://github.com/bhaskargurram-ai/unwind/labels/help%20wanted)
labels. Adding a client config recipe, extending the reversibility index for a new
server, or writing a conformance fixture are all great starting points. Say hi in
[Discussions](https://github.com/bhaskargurram-ai/unwind/discussions) if you get stuck.
