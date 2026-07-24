# Support

Thanks for using Unwind. Here is how to get help, and which channel fits your question.

## Before you ask

- Read the [README](./README.md) — install, client config, and the R0–R4 taxonomy.
- Skim the [docs](https://bhaskargurram-ai.github.io/unwind/).
- Check [`PROJECT.md`](./PROJECT.md) for the thesis and design, and
  [`ROADMAP.md`](./ROADMAP.md) to see whether something is planned rather than missing.
- Search existing [issues](https://github.com/bhaskargurram-ai/unwind/issues) and
  [discussions](https://github.com/bhaskargurram-ai/unwind/discussions) — your question
  may already be answered.

## Where to go

| I want to… | Go to |
|------------|-------|
| Ask "how do I…?" or "is this possible?" | [Discussions → Q&A](https://github.com/bhaskargurram-ai/unwind/discussions/categories/q-a) |
| Report a reproducible bug | [New issue → Bug report](https://github.com/bhaskargurram-ai/unwind/issues/new/choose) |
| Propose a feature or idea | [Discussions → Ideas](https://github.com/bhaskargurram-ai/unwind/discussions/categories/ideas), then a Feature request issue |
| Show what you built with Unwind | [Discussions → Show and tell](https://github.com/bhaskargurram-ai/unwind/discussions/categories/show-and-tell) |
| Report a security vulnerability | **Privately** per [`SECURITY.md`](./SECURITY.md) — never a public issue |
| Chat in real time | Discord — **coming soon** |

## Filing a good bug report

Please use the [bug report form](https://github.com/bhaskargurram-ai/unwind/issues/new/choose)
and include:

- Unwind version (`unwind --version`), Python/Node version, and OS;
- the MCP client and the upstream server you were wrapping;
- your `unwind run -- …` command (redact secrets);
- what you expected vs. what happened, with logs if you have them.

A minimal reproduction dramatically speeds up a fix. If a call was auto-allowed that
should have escalated — a **fail-open** — say so prominently; those are top priority.

## What we don't support here

- Debugging upstream MCP servers or MCP clients themselves — report those to their
  maintainers (we're happy to help identify which side an issue is on).
- Private/commercial support contracts — not offered at this stage.

## Response expectations

Unwind is maintained on a best-effort basis during early beta. Issues and discussions
are triaged regularly; security reports follow the SLAs in [`SECURITY.md`](./SECURITY.md).
Please be patient and kind — see the [Code of Conduct](./CODE_OF_CONDUCT.md).
