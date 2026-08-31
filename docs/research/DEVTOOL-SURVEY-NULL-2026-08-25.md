---
title: Dev-tooling survey — no project survived
tags: [survey, null-result, product-discovery]
date: 2026-08-25
source: brainstorming run, 4 discovery agents + 2 fresh-context adversarial verifiers
related: [coding-agent-tooling-survey-null, pincite-product-decision]
---

# NO PROJECT SURVIVED

Broad evidence-first sweep for one public GitHub project buildable as a one-day MVP.
Territory: Git/GitHub workflows, CLI/local dev, CI/testing/debugging, AI-assisted dev,
data workflows. Two finalists emerged; both killed by fresh-context verifiers on
directly observed facts.

## Finalist 1: runner-image diff CLI — KILLED

"CI went red with zero code changes — what changed in the GitHub runner image?"

Best demand evidence of the run: image pinning formally declined by GitHub
(actions/runner-images#13034 closed not_planned), recurring breakage threads, no
incumbent, mechanism verified working end-to-end via `gh api`.

Kill: GitHub already publishes the exact diff. Every runner-image release body
contains a categorized Previous→Current table of every updated/added/removed tool,
plus a machine-readable JSON manifest. The failing run's own "Set up job" log links
directly to that release page. Manual workflow is ~1 minute, zero tools. And in the
marquee image-caused incidents (hanging builds #13182, #13770) the culprit was
kernel/infra-level — a software-manifest diff would not have contained the answer.
What remains is a gist, not an install.

| Source | Date | What it demonstrates |
|---|---|---|
| actions/runner-images#13034, closed not_planned | Sep 2025 | Pinning declined — pain permanent (verified via gh api) |
| runner-images#10636, 384 reactions | Dec 2024–2025 | Image changes break CI at scale |
| runner-images#13770, open, 22 comments | Mar 2026 | Recurring and current — but culprit was infra, not manifest-visible |
| Release body of runner-images 20260823.283.1 | Aug 2026 | The kill: native Previous→Current diff table + JSON manifest, fetched live |
| "Set up job" log of a live run | Aug 2026 | Failing run links directly to that release page |

## Finalist 2: orphaned dev-process reaper — KILLED

Stale build watchers / test workers holding RAM on no port, missed by port killers.

Kill: zclean (`npx z-clean`, active, safety filters, provider attribution) already
owns the growing AI-agent-orphan segment. Verifier reproduced the full detection
pipeline in three shell one-liners (ps PPID=1 filter, `lsof -p -d cwd`, stat of the
path). Upstream sources being fixed (vitest #9123 closed, esbuild #3558 closed).
66 stars after sustained promotion is the observed ceiling of the category.

## Category kill-list confirmed this run

Stacked PRs (GitHub native github/gh-stack public preview 2026-07-30, server-side
cascading rebases). Terminal PR review threads (agynio/gh-pr-review, 174★, LLM-ready,
exact wedge taken). Worktree managers (worktrunk + saturation). Agent session search
(5+ OSS entrants, MCP context injection covered). CI log triage (Copilot Explain
Error GA 1/2025, Fix with Copilot 5–6/2026). Port kill / localhost visibility (Sonar
204pt HN + ~8 tools). .env drift (dotenv-linter compare; in-code validation won).
Local Actions iteration (act/wrkflw/actionlint; parity gap is months, not a day).
Parquet/CSV quick-look (pq, duckdb, visidata). Notebook-to-script (marimo won).
JSON exploration (jnv/fx/jless + terminal LLMs).

## Meta-pattern (third confirmation on 2026-08-25)

Every visible dev-workflow pain in 2025–26 either spawns 3–5 OSS entrants within
weeks or gets vendor-shipped within a release cycle. Least picked-over ground
observed: pains only the vendor can fix (anthropics/claude-code#2511, 610 reactions,
no CLI access to claude.ai Projects) — argues for waiting, not building.

## Notes

Prompire leverage: checked only after finalists survived discovery — essentially
none for either. Played no role in the verdict.

Uncertainty: finalist kills verified first-hand by verifiers (live gh api calls,
fetched release bodies). Second-tier kill claims (star counts, HN points, changelog
dates) are agent-reported, not independently re-verified; none would flip the
verdict if wrong.
