# Kettle story bible (synthetic data spec)

> **Status: AI-drafted on Oct 16 from `plan.md` sections 0, 5, 6 and 7. Ayan must review it** (see `HUMAN_REVIEW.md`, item R-01).
> This file is the **single source of truth** for the fake company. The data generator (`backend/lore/data_gen/`), the golden questions (`backend/eval/golden.jsonl`) and the demo script must agree with it. If you change a fact here, regenerate the data and re-run the evals.

All names are fictional. Every date in this file is a date in Kettle's story (the company's past, up to the demo incident), not a date of work on this project. All times are **IST (+05:30)** and are stored in the graph as **Unix seconds** (integers).

---

## 1. Company at a glance

| Item | Value |
|---|---|
| Company | Kettle, a food-delivery startup |
| Engineers | 45 people (44 employees + 1 contractor) in 6 teams |
| Services | 30 |
| Volume | 300 PRs · ~140 deploys · 150 Slack threads · 80 tickets · 15 ADRs · 10 past incidents |
| Business pain | median **47 min** alert-to-cause for P1/P2; **3 of last 10** incidents paged the wrong person first |
| Graph name | `org_kettle` (second tenant for the multigraph demo: `org_demo2`, P2) |

## 2. Id conventions

Every node has a string `id` property. It is what tools return, what citations point to, and what the UI highlights.

| Label | id pattern | Example |
|---|---|---|
| Person | `person:<slug>` | `person:arjun` |
| Team | `team:<slug>` | `team:pricing` |
| Role | `role:<slug>` | `role:security` |
| Channel | `channel:<slug>` | `channel:pricing-private` |
| Service | `svc:<name>` | `svc:pricing` |
| Repo | `repo:<name>` | `repo:pricing` |
| CodeModule | `mod:<path>` | `mod:pricing/config.yaml` |
| PR | `pr:<number>` | `pr:482` |
| Deploy | `deploy:<number>` | `deploy:991` |
| Ticket | `ticket:<KEY>` | `ticket:PRC-311` |
| Thread | `thread:<channel>-<nnnn>` | `thread:pricing-private-0142` |
| Doc (wiki / runbook / postmortem) | `wiki:<slug>`, `runbook:<slug>`, `pm:<incident>` | `wiki:pricing-cache` |
| Decision (ADR) | `adr:<nnn>` | `adr:011` |
| Incident | `inc:<KEY>` | `inc:INC-0307` |
| Alert | `alert:<KEY>` | `alert:A-3001` |
| Chunk | `<source id>#<n>` | `adr:011#0` |

## 3. Teams, roles and channels

**Teams (6):** `checkout`, `pricing`, `dispatch`, `payments`, `data`, `platform`.

**Roles:** `oncall-engineer`, `incident-commander`, `security`, `eng-manager`, `hr`, `contractor`.
No demo persona has the `hr` role.

**Channels:**

| Channel | private | access_level of its threads | Notes |
|---|---|---|---|
| `#general` | false | public | Contractors can read this |
| `#eng` | false | internal | |
| `#incidents` | false | internal | Where the Responder posts |
| `#oncall` | false | internal | |
| `#checkout`, `#pricing`, `#dispatch`, `#payments`, `#data`, `#platform` | false | internal | Team channels |
| `#pricing-private` | true | restricted | `VISIBLE_TO` → `channel:pricing-private` and `role:incident-commander` |
| `#sec-incidents` | true | confidential | `VISIBLE_TO` → `role:security` |
| `#hr-private` | true | restricted | `VISIBLE_TO` → `role:hr` only. **No persona may ever see it.** |

## 4. Demo personas

| Persona | id | Team | Roles | Channels (`IN_CHANNEL`) | employment | open levels |
|---|---|---|---|---|---|---|
| Arjun Mehta | `person:arjun` | checkout (joined 2026-09-23) | oncall-engineer | general, eng, incidents, oncall, checkout | employee | public, internal |
| Dana Okafor | `person:dana` | platform | incident-commander, security | general, eng, incidents, oncall, platform, sec-incidents | employee | public, internal |
| Sam Rivera | `person:sam` | none | contractor | general | contractor | public |
| Marco Bianchi | `person:marco` | data (since 2026-08-01) | none | general, eng, data | employee | public, internal |

Marco's history: `WAS_MEMBER_OF {from: 2023-04-01, to: 2026-08-01}` → `team:pricing`, and `WAS_IN_CHANNEL {to: 2026-08-01}` → `channel:pricing-private`. He has no current path to `#pricing-private`.

**Expected visibility of the key restricted sources:**

| Source | Arjun | Dana | Sam | Marco |
|---|---|---|---|---|
| `thread:pricing-private-0142` (ADR-011 discussion) | ❌ restricted warning | ✅ | ❌ | ❌ |
| `thread:pricing-private-0150` (vendor rates) | ❌ | ✅ | ❌ | ❌ |
| `inc:INC-0326` + `thread:sec-incidents-0007` (leaked key) | ❌ | ✅ | ❌ | ❌ |
| `thread:hr-private-0003` (Marco's transfer) | ❌ | ❌ | ❌ | ❌ |
| `adr:011` (internal) | ✅ | ✅ | ❌ | ✅ |
| `thread:general-*` (public) | ✅ | ✅ | ✅ | ✅ |

## 5. Named people (the rest are generated)

| id | Name | Team | Notes |
|---|---|---|---|
| `person:rahul` | Rahul Verma | pricing | Pricing team lead, role `eng-manager`. Owner on the org chart. Correct person to **page** for pricing. |
| `person:priya` | Priya Nair | pricing | Author of PR #482 |
| `person:wei` | Wei Zhang | pricing | Reviewer of PR #482 |
| `person:marco` | Marco Bianchi | data | The real pricing **expert** (most pricing PRs before Aug 2026, resolved INC-0307). Consult, don't page. |
| `person:leah` | Leah Cohen | checkout | Author of the red-herring PR #479 |
| `person:tomas` | Tomás García | dispatch | Author of PR #517 (Story B) |
| `person:ines` | Ines Duarte | payments | The only person who has touched `ledger` (bus factor 1) |
| `person:kofi` | Kofi Mensah | dispatch | Dispatch team lead / owner |
| `person:hana` | Hana Sato | payments | Payments team lead |

Members of `#pricing-private` (current): rahul, priya, wei.

## 6. Services (30) and dependencies

`tier` 1 = most critical. Owner = the team with `OWNS`.

| Service | tier | owner | `DEPENDS_ON` |
|---|---|---|---|
| api-gateway | 1 | platform | auth |
| auth | 1 | platform | user-profile |
| checkout | 1 | checkout | cart, promo-engine, payments-gateway, orders, auth |
| cart | 2 | checkout | menu, inventory |
| promo-engine | 2 | checkout | pricing, feature-flags |
| pricing | 1 | pricing | menu, config-service, feature-flags |
| surge-pricing | 2 | pricing | pricing, rider-location |
| menu | 2 | pricing | restaurant-catalog |
| restaurant-catalog | 3 | data | — |
| inventory | 2 | checkout | restaurant-catalog |
| orders | 1 | checkout | ledger, notifications |
| payments-gateway | 1 | payments | fraud-check, ledger |
| ledger | 2 | payments | — |
| fraud-check | 2 | payments | user-profile |
| refunds | 2 | payments | ledger, payments-gateway |
| invoices | 3 | payments | ledger |
| courier-payouts | 2 | payments | ledger |
| dispatch | 1 | dispatch | eta-predictor, rider-location, orders |
| eta-predictor | 2 | dispatch | maps-proxy, feature-flags |
| rider-location | 2 | dispatch | maps-proxy |
| maps-proxy | 3 | dispatch | — |
| notifications | 2 | platform | user-profile |
| user-profile | 2 | platform | — |
| feature-flags | 1 | platform | — |
| config-service | 2 | platform | — |
| search | 2 | data | restaurant-catalog |
| recommendation | 3 | data | search, analytics-ingest |
| analytics-ingest | 3 | data | — |
| reviews | 3 | data | user-profile |
| support-desk | 3 | platform | orders, user-profile |

Every service has one repo, `repo:<name>` (`BUILT_FROM`), and its repo `CONTAINS` 2–4 code modules, always including `mod:<name>/config.yaml`.

All `DEPENDS_ON` relationships carry `w: 1` (for `algo.SPpaths` if `weightProp` turns out to be required; see plan L.11).

## 7. Planted stories

### Story A: the main incident (demo time 2026-10-14 03:00 IST)

| Time (IST) | Event | Node |
|---|---|---|
| 2026-02-10 | ADR-011 "Pricing cache TTL must stay ≥ 300s" written by Marco. Internal. Reason: vendor tax/price API rate limit; low TTL caused a near-miss. | `adr:011` |
| 2026-02-09 | The detailed discussion behind ADR-011, incl. vendor rate-limit numbers, in `#pricing-private`. ADR-011 `DISCUSSED_IN` this thread. | `thread:pricing-private-0142` (restricted) |
| 2026-03-07 | INC-0307 "Pricing overload after cache TTL lowered to 30s". `AFFECTED` pricing and checkout. `CAUSED_BY` `pr:211` (Marco's colleague, reverted). `RESOLVED_BY` Marco. Postmortem `pm:INC-0307` (`RECORDED_IN`). Severity P1. | `inc:INC-0307` |
| 2025-06-01 | Old wiki "Pricing cache: 60s TTL is fine". `adr:011` `SUPERSEDES` it. | `wiki:pricing-cache` |
| 2025-11-20 | Old runbook "Pricing on-call: page Marco". Stale: Marco moved teams. | `runbook:pricing-oncall` |
| 2026-10-12 | Ticket PRC-311 "Promo price changes take 5 minutes to show". | `ticket:PRC-311` |
| 2026-10-13 18:10 | PR #482 "Lower pricing cache TTL to 5s for faster promo updates", author Priya, reviewer Wei, `MODIFIES` `mod:pricing/config.yaml` (300 → 5), `FIXES` PRC-311, `IN_REPO` `repo:pricing`. | `pr:482` |
| 2026-10-14 01:30 | Deploy 991 `DEPLOYED_TO` pricing, `INCLUDES` PR #482. | `deploy:991` |
| 2026-10-14 02:48 | **Red herring.** Deploy 990 `DEPLOYED_TO` checkout, `INCLUDES` PR #479 "Update checkout button copy" (Leah), which only `MODIFIES` `mod:checkout/i18n/en.json`. | `deploy:990`, `pr:479` |
| 2026-10-14 03:00 | Alert A-3001 "checkout p99 latency > 3s" `FIRED_ON` checkout. | `alert:A-3001` |

**Evidence path:** `alert:A-3001 -FIRED_ON-> svc:checkout -DEPENDS_ON-> svc:promo-engine -DEPENDS_ON-> svc:pricing <-DEPLOYED_TO- deploy:991 -INCLUDES-> pr:482`.

**Expected answer:** root cause `pr:482`; red herring `pr:479` rejected (copy-only change); severity P1 (tier-1 checkout in blast radius); page Rahul (owner), consult Marco (expert), notify Priya (author); cite `adr:011`, `inc:INC-0307`; for Dana also `thread:pricing-private-0142`.

### Story B: the memory demo (2026-10-21 03:10 IST)

| Time (IST) | Event | Node |
|---|---|---|
| 2026-10-20 17:40 | PR #517 "Reduce eta-predictor model cache TTL to 10s" by Tomás, `MODIFIES` `mod:eta-predictor/config.yaml`. | `pr:517` |
| 2026-10-21 01:50 | Deploy 1034 → eta-predictor, includes PR #517. | `deploy:1034` |
| 2026-10-21 02:55 | Red herring: deploy 1035 → notifications (PR #518 "Fix typo in push template"). | `deploy:1035` |
| 2026-10-21 03:10 | Alert A-3002 "dispatch assignment latency > 5s" `FIRED_ON` dispatch. | `alert:A-3002` |

**Expected:** root cause `pr:517`. With the playbook learned from Story A ("config/TTL change in a downstream dependency") it should take ~4 tool steps instead of ~11.

### Story C: ask the brain

- "Why is the pricing cache TTL 300 seconds?" → ADR-011, INC-0307 (+ thread 0142 for Dana).
- "Who knows the ledger service?" → Ines; flag bus factor 1 (every `repo:ledger` PR authored by Ines; reviews by Hana).

### Story D: conflicting and out-of-date sources

- `wiki:pricing-cache` (2025-06, "60s is fine") vs `adr:011` (2026-02, "≥ 300s"). ADR wins: higher source rank + `SUPERSEDES`.
- `runbook:pricing-oncall` says "page Marco". Correct: page Rahul, consult Marco.

### Story E: permission traps

- `inc:INC-0326` (2026-03-26) "Leaked payments API key in a public gist", confidential, discussed in `thread:sec-incidents-0007`. `VISIBLE_TO role:security`.
- `thread:pricing-private-0150` vendor contract rates, restricted.
- `thread:hr-private-0003` about Marco's transfer, `VISIBLE_TO role:hr`. Never visible to any persona.

## 8. Filler data rules (for the generator)

- Fixed random seed `20261015`. Output must be byte-identical between runs.
- Filler PRs: numbers 180–520 not used above, spread over 2025-10-01 … 2026-10-13, authored mostly by members of the owning team. Before 2026-08-01, Marco authors ≥ 25 pricing PRs. Ines authors every ledger PR.
- Filler threads: spread across the internal team channels and `#general`. Each thread `MENTIONS` 1–3 services and 0–2 people.
- Tickets: prefixes `CHK`, `PRC`, `DSP`, `PAY`, `DAT`, `PLT` by owning team. Access level internal.
- ADRs `adr:001`…`adr:015`, internal; only ADR-011 is special.
- Incidents: 10 in total. INC-0307 and INC-0326 are special; the other 8 are internal filler with `RESOLVED_BY` someone on the owning team.
- Text for threads, tickets, ADRs and docs is written by Gemini Flash **once** (`python -m lore.data_gen.text_gen`) and saved to `backend/data/text/*.json`. Until then the generator uses deterministic template text, so everything works offline.

## 9. Source rank (for conflicts)

`Decision (ADR) > runbook > postmortem > ticket > Slack thread > wiki`. Newer beats older at the same rank, and `SUPERSEDES` always wins.
