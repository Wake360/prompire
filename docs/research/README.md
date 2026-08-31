# The research record

Every document here is a frozen verdict or survey from the 2026 research program
that produced the current design. They are kept verbatim — several cite exact
commits, preserved by the `frozen/*` tags — and are not user documentation.

Read in this order:

**Surveys — where is the demand?**
[DEVTOOL-SURVEY-NULL-2026-08-25.md](DEVTOOL-SURVEY-NULL-2026-08-25.md) — dev-tooling opportunity survey; explicit null result.
[ECONOMIC-PULL-SURVEY-2026-08-25.md](ECONOMIC-PULL-SURVEY-2026-08-25.md) — economically-pulled problems; all four verified candidates killed.
[PINCITE-VERDICT.md](PINCITE-VERDICT.md) — the "pincite" product investigation and its competitive kill.
[PROMPIRE-DEEP-PRODUCT-DISCOVERY.md](PROMPIRE-DEEP-PRODUCT-DISCOVERY.md) — deep product discovery and open-source strategy.

**Positioning the shipped verifier**
[positioning_verdict.md](positioning_verdict.md) — what to fix before showing it to a stranger.
[product-validation_verdict.md](product-validation_verdict.md) — standalone assessment; "YES, BUT".
[synthesis_verdict.md](synthesis_verdict.md) — adjudicates the two above; "FIX THEN SHIP".

**The compiler family — four generations, one lineage**
[compiler-v1.md](compiler-v1.md), [compiler-v2.md](compiler-v2.md), [compiler-v2-report.md](compiler-v2-report.md) — the safe-task-compiler design and the E1 defect closure.
[task-compiler.md](task-compiler.md) — the task compiler prototype, its evaluation, and its verdict (evidence in [tc-evidence/](tc-evidence/)).
[task-context-compiler-verdict.md](task-context-compiler-verdict.md), [execution-compiler-verdict.md](execution-compiler-verdict.md), [universal-prompt-compiler-report.md](universal-prompt-compiler-report.md) — the sibling theses and their outcomes.
[task-compiler-thesis_verdict.md](task-compiler-thesis_verdict.md) — "the verifier remains the stronger product".

**The kills and what they mean**
[preregistered-kills.md](preregistered-kills.md) — five preregistered experiments that killed their own hypotheses.
[e5-validated-agent-learning-verdict.md](e5-validated-agent-learning-verdict.md) — validated agent learning, rejected.
[ml-research-assessment.md](ml-research-assessment.md) — neural methods for this problem; "mostly no".
[OPTIMIZER-VERDICT.md](OPTIMIZER-VERDICT.md) — behavior-constrained patch optimization, final verdict.
[product-thesis.md](product-thesis.md) — the terminal synthesis: no compiler-family product thesis survived.

Net verdict: nothing that generates authority survived measurement — four
independent "a model writes the contract" implementations died on preregistered
gates. What shipped instead is the verifier/bench identity: authority comes from
a mechanical measurement or a human confirmation, never from generated text.
That is why `prompire compile` exists in the tree but is not documented as a
product surface.
