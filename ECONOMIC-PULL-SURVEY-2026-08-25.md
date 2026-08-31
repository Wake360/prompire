---
title: Economic-pull opportunity survey — resolved; primary direction + 2 alternatives
tags: [survey, product-discovery, verification]
date: 2026-08-25
source: brainstorming run, 7 discovery agents + 8 fresh-context adversarial verifiers (4 initial + 4 resolution round) + 10 combined discovery/verifier probes (alternatives round)
related: [DEVTOOL-SURVEY-NULL-2026-08-25, coding-agent-tooling-survey-null, pincite-product-decision]
---

# Run status: RESOLVED 2026-08-25 — direction: independent billing-completeness monitoring (see final section)

Different search class than the 2026-08-25 dev-tooling null: economically important
problems (recurring cost, paid incumbents, headcount) instead of visible dev pains.
Seven domains surveyed: security/compliance ops, SRE/FinOps, data ops, support
engineering, internal/IT ops, budget-line dev infra, expert knowledge work.
~30 candidates examined, 5 rated STRONG by discovery, 4 verified by fresh-context
adversarial verifiers. All 4 verified theses killed. Final verification round on the
2 unresolved candidates was interrupted; direction not yet rendered.

## Verified kills (fresh-context verifiers, WebFetch against primary sources)

### 1. Agent PR governance layer — KILLED
Policy+spend+audit control plane between coding agents and the repo. Pain verified
first-hand: Faros AI 2026 (~22k devs) — median review time +441.5%, zero-review
merges +31.3%, churn +861%; CircleCI 2026 — main-branch success 70.8%, 5-year low,
attributed to AI code. Kill: squeezed from both sides. CodeRabbit announced
"Agentic Change Management — the control layer for software changes created by
humans and agents" 2026-08-12 with a $143M Series C at $1.5B. GitHub Agent HQ
(2025-10-28) ships agent identity, policies, branch controls — GitHub's own words:
"your agent governance layer." Remaining fragment (cross-vendor spend-per-change
attribution) is technically fragile: gateway logs carry no PR context, co-author
trailers are spoofable, and the merge-critical-path trust level is unreachable for
a solo dev. This was the one candidate with direct Prompire leverage; leverage did
not save it.

### 2. Mid-market PKI/certificate inventory — KILLED
Kill argument is a segment pinch. The 47-day forcing function (CA/B SC081v3,
verified passed: 398→200d Mar 2026, →100d 2027, →47d 2029) applies only to
publicly-trusted certs — exactly the ones being pushed onto free ACME automation
and watched by $0–79/mo commodity monitors. The differentiated slice (K8s,
private CA, mesh) has no deadline pressure and is an afternoon of OSS assembly:
enix/x509-certificate-exporter (946★, active) does multi-cluster inventory with
Grafana dashboards today. The tailwind is the headwind: shorter lifetimes force
automation, which shrinks the unmanaged-cert population the product would find.
Only buyers needing the full union are enterprises already on Keyfactor/Palo Alto.

### 3. Usage-based billing reconciliation — KILLED
Independent invoice recompute vs. the customer's warehouse. Kill: Stripe docs say
"Metronome is now part of Stripe" and route all new usage billing there; the
remaining Stripe-native cohort has simple pricing where leakage is smallest; the
complex-pricing segment (where "4–7% leakage" vendor claims live) already gets full
billing-data warehouse exports from Metronome/Orb, collapsing the product into a
SQL diff one first-party sprint can ship. Deterministic external recompute is
infeasible exactly where pricing is complex. Surviving fragment: metering-ingestion
completeness (events lost before ingest — platforms can't reconcile what they never
received); feasible via documented APIs, but finance-trust sale + feature-sized.
Needs 3–5 discovery interviews before it's more than an OSS script.

### 4. Security exception / risk-acceptance management — KILLED
Differentiation anchor was false. Vanta ships Accept treatments with up to 5-step
approval workflows, forced re-approval, reminders, auditor-shareable snapshots —
as a monetized upsell (help docs dated 2026-05-15). Drata captures acceptance,
justification, reviewer in-product. Scrut has approval-gated treatments with full
audit log. No evidence auditors reject spreadsheet exception logs (ISO/SOC2 are
tool-agnostic), so no forcing function; WTP caps near an Airtable base. Natural
experiment: Spectra (securityexceptions.com), a live focused competitor, has
placeholder pricing and zero visible traction. Genuine residual gap (hard expiry
on acceptances, employee-facing intake, Slack routing) is feature-sized on Vanta's
upsell path.

## Unresolved at time of first writing — since resolved (verdicts in final section)

- **Cross-system metric/dashboard reconciliation** ("why don't our numbers match").
  Discovery rated STRONG: broad buyer, recurring trigger, no incumbent found
  shipping "diff two dashboards without a semantic-layer migration." Never
  verified, and its author's credibility is impaired (see evidence-hygiene below);
  its cost citations (bluepes.com "$525k/yr", 30–60% analyst time) are SEO-grade
  and unchecked. Verify: citation authenticity; whether Datafold/Monte Carlo/
  Metaplane/Euno ship this; whether BI-tool APIs make the mechanism feasible.
- **Patent prior-art opinion-memo wedge** ($100–300/search vs. verified
  $1,000–3,000 attorney searches; PatSnap Eureka $100–200/mo exists but is
  search/analytics, not citation-verified opinion drafting). One check from
  resolution: do funded AI patent startups (Patlytics, Solve Intelligence, DeepIP,
  IPRally, &AI…) already ship exactly this? Prior says the space is crowded;
  unverified this run.
- **Unevaluated territory** (search quota died before evaluation): technical due
  diligence (PE/VC — consulting-priced, recurring deal flow; likely incumbents to
  check first: CodeScene, Software Improvement Group), grant writing, standards-
  compliance mapping. Honest coverage gap, not a null.

## Evidence-hygiene findings (as important as the kills)

Discovery agents fabricated or garbled sources under search pressure; verifiers
caught them from primary URLs:
- data-ops agent: 4 of 5 billing-recon citations false — leaksshield.com does not
  resolve; kanopylabs.com is a dev agency with zero billing content; withorb.com
  post exists but contains none of the quoted figures; Metronome "Spark rechecker"
  post does not exist.
- eng-ops agent: cited competitor "CertPulse" does not resolve on any TLD.
- dev-infra agent: "Gartner Q1 2026, 18% of merged PRs agent-authored" —
  unverifiable anywhere; "CodeRabbit ships no governance product" — false 13 days
  before the report.
Rule confirmed for future runs: no discovery claim survives to a verdict without a
fresh-context verifier fetching the primary source. Verifier claim-by-claim format
(VERIFIED/FALSE/UNVERIFIABLE + strongest-argument-for) worked well; keep it.

## Meta-pattern (differs from the dev-tooling null)

Economically-pulled categories don't die by OSS commoditization in weeks; they die
because the money already summoned incumbents years ago — usually the platform that
owns the data (GitHub, Stripe/Metronome, Vanta) shipping the wedge as a bundled
feature or upsell. Surviving gaps are consistently feature-sized slivers on an
incumbent's roadmap path. Where the verifiers found genuine open gaps (ingestion
completeness, agent spend-per-change attribution, exception expiry), each was real
but structurally weak for a solo dev: trust-gated buyer, platform one sprint away,
or OSS-script-sized.

## Operational notes

- Session WebSearch cap (200 calls, shared across all subagents) exhausted mid-run;
  all four verifiers ran WebFetch-only against primary URLs and flagged
  unverifiable claims instead of guessing. Budget the cap per-agent next time.
- Machine slept mid-run; killed the first knowledge-work agent three times.
  Fix applied: caffeinate for the session. Respawned agent completed a
  constrained but useful report.
- Prompire leverage: checked only after survival per protocol. Only agent-PR
  governance had real leverage (diff-vs-contract verification, scope hooks);
  it was killed on incumbent motion, not on leverage grounds.

# Resolution round (2026-08-25, same day) — survey resolved

Four fresh-context adversarial verifiers, WebFetch-only against primary URLs
(session WebSearch cap already exhausted at round start; unreachable claims
marked unverifiable, never guessed).

## Resolution-round kills

### 5. Cross-system metric/dashboard reconciliation — KILLED
Both legs failed independently. Demand evidence fabricated: bluepes.com is an
e-commerce dev-shop blog with zero reconciliation content and no "$525k" figure;
the "30-60% analyst time" claim has no primary source (closest real: dbt State of
Analytics Engineering 2024, 57% cite data quality as a chief obstacle — prevalence,
not time share). Direct incumbent ships the thesis: Euno's homepage demos tracing
divergent DAU metrics across dashboards via column-level lineage (dbt, Looker,
Power BI, Tableau), no semantic-layer migration. Monte Carlo and Datadog/Metaplane
(acquisition verified) are one lineage feature away. Useful residue: feasibility
fully verified — Power BI scanner API, Tableau Metadata API, Looker
lookml_model_explore expose metric definitions and lineage to third parties.

### 6. Patent prior-art opinion-memo wedge — KILLED
Core premise false on primary sources: Patlytics ships citation-backed claim
charts and analysis reports (Am Law 100 clients); DeepIP ships a Patentability
Module with novelty/non-obviousness scoring; PatSnap Eureka gives inventors
novelty search FREE (Basic tier; "$100-200/mo" was wrong — Pro tiers are
$200-400/mo). Economics anchor was real (UpCounsel: $1,000-3,000 attorney
searches). Hard legal bar: 37 CFR 11.5(b)(1) reserves patentability advice to
registered practitioners, so a non-practitioner "opinion memo" is unauthorized
practice before the USPTO; the legal fallback (opinion-free search report) is
commoditized at $0 by Eureka. Residue (patent-agent-signed productized service)
is a regulated services business, a different thesis.

### 7. Technical due diligence for PE/VC — KILLED (territory evaluated this round)
Wedge occupied at both ends. Commodity end: SIG "Product Risk & Value Scan" —
automated, €999 fixed price, 24h turnaround, 30,000+ system benchmark database.
Trust end: Crosslake (500+ PE firms), TechMiners (named CTOs), Sema ("7 of 9
largest global investors"). TechMiners publicly documents its internal multi-agent
LLM DD pipeline and markets against "just prompt Claude" — incumbents absorb the
AI angle as internal tooling. Demand real (Software Equity Group: 2,698 SaaS M&A
deals 2025, +28% YoY) but the buyer purchases defensibility and a name to blame,
not software. Engagement pricing ($20k-100k) unverifiable from primary sources.

### 8. Metering-ingestion completeness (fragment promoted, dedicated check) — KILL verdict, selected anyway (see decision)
Verifier confirmed: pain real and vendor-acknowledged (m3ter: "lose 4-7% of
revenue to under-billing"; Metronome docs name "silent revenue loss" twice and
instruct customers to "build custom leakage detection alerts"; Lago docs make the
source-of-truth diff a customer DIY paragraph; Orb has no automatic detection);
competitor vacuum verified (no independent monitor at Amberflo, m3ter, Togai,
Monte Carlo); APIs sufficient for external diff (Stripe per-customer meter
summaries, Lago /events, Orb account-level hourly volumes, Metronome
sampling-only Event Search). Kill arguments: native trajectory (Stripe owns
Metronome, which ships the leakage-detection primitive + recipe; Adyen acquired
Orb; OpenMeter ships source-side loss prevention) and feature size (per-platform
diff is sprint-sized for the customer's own data team).

## Final decision — strongest imperfect opportunity (per goal contract: rank, don't null)

**Independent billing-completeness monitoring for usage-based billing.**
User: billing/platform engineer at usage-billed SaaS and AI-infra companies.
Recurring economic problem: silent under-billing from events dropped before
platform ingest (every deploy, schema change, queue incident); 4-7% of revenue
per m3ter, "silent revenue loss" per Metronome's own docs.
Smallest wedge: read-only 30-day completeness audit against one platform (Stripe
meters or Lago /events) diffing the customer's source of truth; report the dollar
value of never-ingested events. Audit sells the finding; continuous monitoring is
the subscription.
Distribution: bottom-up OSS collector + auditor, "we found $X unbilled" case
studies at month-close, Lago OSS community and AI-infra/token-billing beachhead.
Strongest alternatives: customer's own SQL-diff cron job (the real competitor);
Metronome Event Search (sampling-only, Metronome-only, DIY recipe); OpenMeter
Collector (prevention, own pipeline only); m3ter (full billing-stack migration).
Why it survives the adversarial check: its KILL rested on trajectory and size
predictions, not existence facts — unlike every other candidate (Euno ships #5,
Patlytics/DeepIP ship #6, SIG/Crosslake own #7). Counter to native-trajectory:
the audited party can't be the auditor; source-side counting lives in customer
infra platforms don't own; no single platform builds cross-platform coverage;
Metronome's sampling rate-limit itself pushes the design source-side. Counter to
feature-size: the diff script is the wedge, not the product — the collector +
continuous reconciliation + finance-grade evidence trail is the durable asset.
Accepted residual risk: platform absorption and feature-size remain real; that is
what "strongest imperfect" means.
Ranking behind the selection: 1) metering completeness (verified pain + verified
vacuum + reachable buyer; predictive kill only), 2) metric reconciliation
(verified feasibility, but shipping incumbent + fabricated demand), 3) tech DD
(verified demand, occupied wedge), 4) patent memos (verified economics, false
premise + UPL bar), 5) earlier fragments (exception expiry, spend attribution:
feature-sized or fragile).
Gate before building: 3-5 discovery interviews with usage-billed companies plus
the read-only audit as first artifact; until then this is a direction, not a
build commitment. Prompire leverage: indirect only (shared DNA: independent
verification of claimed-vs-actual system behavior); not a selection factor.

# Alternatives round (2026-08-25, same day) — 10 territories probed, 2 survived

Goal: 2-3 verified alternatives to the primary direction, not kills. Ten
combined discovery+adversarial probes, WebFetch-only against primary URLs
(WebSearch quota exhausted session-wide). Eight killed, two survived with full
direction blocks.

## Alternatives-round kills (one line each; full reports in session transcript)

- Grant tooling: discovery+drafting saturated AI-native at $9-150/mo (Grantable,
  Granted AI, Grantboost, OpenGrants verified w/ pricing); post-award occupied
  both sides (EMDESK €15/user/mo EU moat, Euna AI grantee-side).
- Requirements traceability (SaMD): Ketryx IS the hypothesis ($53M raised, AI
  agents, MCP, free tier for pre-market startups); Matrix One + Greenlight Guru
  ship AI traceability behind it; Doorstop/StrictDoc ~1k combined stars
  evidences weak bottom-up pull.
- Subprocessor-change monitoring: publisher-side absorption (SafeBase/Drata
  trust-center subscribe feeds), objection right contractually toothless
  (Stripe DPA: remedy = lose the service), changedetection.io $9/mo substrate,
  exact prior art (subprocessorwatch $79-299/mo) at 0 stars.
- Royalty reconciliation: recompute infeasible where money is largest (DSP
  revenue pools, licensee self-reported sales unobservable — same kill as
  billing recon); MLC needed a STATUTORY audit right; statement-parsing
  commoditized (Reprtoir 180+ providers).
- EAA accessibility: Stark owns self-serve mid-market at published $2.5-21k/yr,
  Evinced owns dev-native AI remediation, Level Access + Deque ship EAA
  packages; zero verified enforcement actions 14 months post-deadline.
- Consent-enforcement QA: Trackingplan IS the product ($249-999/mo, agency
  plan, 485+ orgs); Sourcepoint/Didomi above, EDPB free tool + CMP-bundled
  scanners below. Demand side verified real (CNIL small-fine waves, noyb mass
  complaints) — category occupied at every tier.
- Backup restore drills: AWS Backup restore testing native (incl. audit
  controls); databasus OSS (8.3k stars/14mo) does real restore verification
  free; Drata operationalizes the compliance bar as ONE annual uploaded PDF —
  checkbox-grade bars can't carry continuous paid products.
- EU Pay Transparency reporting: Figures (figures.hr) ships the exact wedge to
  EU mid-market (directive reports, 5%-by-category, equal-value leveling,
  Art 7 letters); mandated analytics are mean/median/quartile arithmetic;
  Art 9(8) lets member states compute reports from tax data. Corrections from
  directive text: 150+ employers in first 2027 wave; ads need not carry ranges.

## Alternative A — EU Cyber Resilience Act readiness tooling (SURVIVES-WEAK)

User: CTO/head of eng at a 10-200-person EU-selling ISV/SaaS/device maker, no
compliance hire; secondary: fractional CISOs, CE-marking consultancies.
Problem: per-product, per-release CRA evidence set (Annex I risk assessment,
SBOM per release, vuln-handling proof, support-period declaration, technical
file, declaration of conformity) vs fines up to €15M/2.5% turnover; 24h/72h
reporting process required by 2026-09-11, applying to products ALREADY on the
market (verified: digital-strategy.ec.europa.eu cra-summary + 66-page
Commission FAQ, doc 122331).
Mechanism verified: default product class self-assesses "irrespective of the
technical specification used" (cra-conformity-assessment page) — software, not
auditors, delivers conformity. Harmonised standards absent until 2027 RAISES
documentation burden (FAQ 6.10: standards voluntary, other means must be
documented).
Wedge: OSS CLI/CI tool: repo + CycloneDX SBOM in → scored Annex I
self-assessment with named gaps + draft technical file per the July 2026
Commission guidance (67 examples). Paid: continuous evidence, release drift,
Art 14 reporting runbook, multi-product dashboards.
Distribution: GitHub, HN/embedded newsletters, SEO vs law-firm prose,
CE-consultancy and vCISO partnerships. Bottom-up, no auditor gate.
Alternatives: ONEKEY/Cybeats/NetRise (demo-gated enterprise firmware); law
firms; 10+ EU-funded free SME projects; doing nothing until 2027 (the real
competitor).
Evidence: Cybeats homepage banners "EU CRA Reporting Deadline: Sep 11, 2026";
three vendors run CRA countdowns; Commission publishes FAQ + guidance; EU funds
10+ SME-support projects.
Adversarial check: Vanta/Drata/Secureframe list 30-40+ frameworks incl. NIS2/
DORA/AI Act — none mentions CRA (verified absence). Survives because CRA is
per-product/per-release, wired to the SDLC (CI-shaped, not attestation-shaped).
Accepted weakness: moat is temporal (12-24 mo), not structural. Play: own the
OSS standard for the technical file; be what Vanta integrates or acquires.

## Alternative B — vendor-side DORA response room (SURVIVES-WEAK, fast-cash)

User: head of compliance or deal-owning sales engineer at a 20-500-person SaaS
vendor with EU financial-entity customers, deal-blocked by a DORA addendum or
RoI data request.
Problem: Art 28(3) yearly register reporting + annual ESA RoI collection forces
every financial customer to refresh vendor data (LEI, service taxonomy,
locations, subcontractor chain, criticality) each year; Art 30(2)/(3) clauses
(audit rights, exit transition, TLPT, incident assistance) recur per deal and
renewal. Economically meaningful because deal-blocking.
Wedge: hosted "DORA response room" — RoI dataset in ITS (EU) 2024/2956 field
structure exportable to any customer template, subcontractor register,
clause-by-clause Art 30 position paper, incident-notification runbook.
Distribution: deal-blocked sales teams mid-procurement, vCISO networks, GRC
communities, SEO on addendum clause language.
Alternatives: manual per-customer spreadsheets (free, tolerable annually);
copying AWS's published DORA Financial Services Addendum; law firms;
Conveyor/Drata/Vanta trust centers once they add a template.
Evidence: ESAs JC 2024 99 (2024-12-04) — annual RoI mechanism + direct call on
ICT providers to self-assess; ITS standard template as Implementing Regulation
2024/2956; AWS ships a dedicated DORA contract addendum; verified vendor-side
vacuum (Conveyor zero DORA mentions; Drata/Vanta serve only the financial-
entity side).
Adversarial check: survives on timing only; trust-center incumbents are natural
owners and a document pack is absorbable in a quarter. Defensible only as the
subcontractor-chain system of record (changing data propagating to all
customers). Honest grade: services-led / fast-cash wedge, not venture-scale.

## Final ranking and round meta-pattern

1) Billing completeness (primary — structural moat: audited party can't be the
auditor; source-side data in customer infra). 2) CRA tooling (bigger market,
stronger forcing function, temporal moat). 3) DORA response room (immediate
deal-blocking pain, weakest defensibility).
New kill patterns confirmed this round: checkbox-grade compliance bars cannot
carry continuous paid products (restore drills); an "independent monitor"
thesis dies the moment one shipped monitor with distribution exists
(Trackingplan); funded EU mid-market incumbents close comp/HR gaps fast
(Figures). Survival pattern held: per-product/per-release deliverables wired to
the SDLC, with compliance-platform incumbents absent, survive; org-level
templates and annual checkboxes die.
