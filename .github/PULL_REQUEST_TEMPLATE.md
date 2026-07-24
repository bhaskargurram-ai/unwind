<!--
Thanks for contributing to Unwind! Please read CONTRIBUTING.md first.
Keep PRs focused. The squashed PR title MUST be a Conventional Commit
(feat:, fix:, docs:, test:, refactor:, chore:, perf:, bench:).
-->

## Summary

<!-- What does this PR do, and why? Link the issue it closes. -->

Closes #

## Type of change

- [ ] `feat:` — new feature
- [ ] `fix:` — bug fix
- [ ] `perf:` — performance improvement
- [ ] `docs:` — documentation only
- [ ] `test:` — tests only
- [ ] `refactor:` / `chore:` / `bench:` — no user-facing change
- [ ] Breaking change (`feat!:` or a `BREAKING CHANGE:` footer)

## Checklist

- [ ] PR title follows [Conventional Commits](https://www.conventionalcommits.org/).
- [ ] Commits are signed off (DCO): `git commit -s` (see CONTRIBUTING.md).
- [ ] Tests added or updated for the change.
- [ ] Metric code has a numeric regression test against a hand-computed fixture (if applicable).
- [ ] `make lint typecheck test conformance` passes locally.
- [ ] The **protocol-conformance** suite (`pytest -m protocol`) is green — no client-breaking behavior.
- [ ] Docs updated (`README.md` / `PROJECT.md` / `docs/`) if public API or protocol behavior changed.
- [ ] No crawled server data, credentials, sandbox state, or `paper/` content is committed.

## Golden-rule review (Unwind is not a filter, it is a recovery layer)

- [ ] Change **fails safe** — uncertainty escalates to a human, never auto-allows.
- [ ] Reversibility is **never over-promised** — fidelity stays graded, not boolean.
- [ ] R0 (read) calls remain ~free — no new latency on the hot path.
- [ ] No scope creep into gateway territory (auth / RBAC / rate limiting / secret scanning / isolation).

## How was this tested?

<!-- Commands run, clients/servers exercised, sandbox usage. -->

## Additional notes

<!-- Screenshots, follow-ups, anything reviewers should know. -->
