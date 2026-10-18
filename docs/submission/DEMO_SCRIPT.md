# Lore demo video: story, screens and voice-over

**Format:** screen recording + voice-over only. No camera.
**Length:** 3:20–3:35. **Arc:** the pager at 3 AM → why the brain struggles then → why a graph → Lore solving the same night → proof the graph matters → back to 3 AM.
The narration is a guide for your own voice, not a script to read. Keep your Hinglish line; it's the hook.

**What you need on screen:** a few full-screen text slides (Keynote, Google Slides or any editor; black background, one line each), the live app, the README, and the agent architecture canvas.

---

## Shot list

### Act 1 · The pager (0:00–0:20)

| Time | On screen | Voice-over |
|---|---|---|
| 0:00 | Black slide. **"03:00"** fades in, large. Then Lore's alert card zoomed in: *A-3001 · checkout p99 latency > 3s*. | A phone buzz sound effect (free from any sound library), then you, half shouting: *"Bhai uth jaa, page hogaya hai!"* (subtitle it in English) |
| 0:05 | Slide: "My roommate · SDE · sometimes on call · deep sleeper" | "My roommate is an SDE who sometimes has to stay on call. He sleeps through his pager, so I'm usually his alarm." |
| 0:11 | Slide, line by line: "One P2" · "the whole team, principal architects included" · "fixed faster with the right context" | "Once, a P2 pulled in his whole team, principal architects and leads included. Later they found it could have been fixed faster if people had the right context. And the person paged first is often an SDE-1, two months into the project." |

### Act 2 · Why 3 AM is hard for any brain (0:20–0:35)

| Time | On screen | Voice-over |
|---|---|---|
| 0:20 | Slide: "Stress weakens the prefrontal cortex: working memory, planning, careful reasoning." Small text: *Arnsten, Nature Reviews Neuroscience, 2009* | "I'm curious about neuroscience. Under acute stress, the prefrontal cortex, the part that holds working memory and careful reasoning, gets weaker fast." |
| 0:27 | Slide: "Sleep loss makes the amygdala more reactive and less connected to the prefrontal cortex." Small text: *Yoo et al., Current Biology, 2007* | "Lose sleep, and the amygdala gets more reactive and less connected to the part that calms it. It happens to the best of us." |

### Act 3 · Why a graph (0:35–0:50)

| Time | On screen | Voice-over |
|---|---|---|
| 0:35 | Slide: **"A caused B. B caused C."** | "I build context systems at work, and I know where vector search breaks. It finds text that sounds similar, but it can't tell you that A caused B and B caused C. That's what graphs are for. I was new to graphs, so I used this hackathon to learn FalkorDB." |
| 0:44 | The README architecture diagram, slow zoom. | "Lore puts a whole company into one FalkorDB graph, with who's allowed to see what, and four agents walk it so you don't have to at 3 AM." |

### Act 4 · The same night, with Lore (0:50–1:50)

Persona **Arjun Mehta (On-call engineer)**, Graph **ON**, "Replay a recorded run" **unticked** (live). Click **▶ Run the 3 AM incident**.

| Time | On screen | Voice-over |
|---|---|---|
| 0:50 | Zoom on the alert card and the Run button. | "This is Arjun, our SDE-1 on call. Checkout is slow at 3 AM." |
| 0:55 | The trail streams and nodes light up. Zoom on the Triage steps. | "Triage computes the blast radius in Cypher. Checkout is tier 1, so it's P1. That's a rule in code, not the model's opinion." |
| 1:05 | Click a trail step, "Show Cypher". Hold on the query and the milliseconds. | "Every step shows the exact query it ran, in a few milliseconds." |
| 1:13 | The graph near deploy 990 / PR #479. | "The obvious suspect is the last deploy to checkout, PR 479. It only changed button text. Ruled out." |
| 1:23 | The camera glides along the lit evidence path. | "The real cause is two services away: checkout depends on promo-engine, which depends on pricing, where PR 482 cut a cache TTL from 300 seconds to 5." |
| 1:35 | The report card: root cause, path, ADR-011, INC-0307, Page Rahul, Consult Marco. | "It cites the decision that forbids this and the March incident with the same cause. It pages Rahul, the owner, not Marco, whom the old runbook still names because he moved teams. A clean RCA, with sources, for a calmer head to review." |

**Edit:** a live run takes about 60 s and sometimes wanders (the test run made 28 tool calls). Speed up the middle, label it "2× speed", and keep the start and the report at normal speed.

### Act 5 · Same question, different person (1:50–2:10)

| Time | On screen | Voice-over |
|---|---|---|
| 1:50 | Switch persona to **Dana**; run with replay ticked (the "REPLAY" tag visible). | "Same incident as Dana, the incident commander. She can see the private pricing channel, so her report cites it. Arjun only got: one restricted source exists, ask the Pricing team." |
| 2:01 | Switch to **Sam** (contractor). | "Sam is a contractor. He gets no PRs or deploys at all. The permission check is inside every query. Across 4 people and 63 test questions each, nothing restricted leaked." |

### Act 6 · A human stays in the loop (2:10–2:30)

| Time | On screen | Voice-over |
|---|---|---|
| 2:10 | Arjun's Actions panel: edit one line of the Slack draft, approve, then switch to the Slack tab showing the post. | "Nothing leaves Lore without a human. I edit the post, approve it, and it lands in Slack with names, not ids." |
| 2:20 | Dana's GitHub issue draft citing the private thread: Approve, then the red block reason. | "If a draft would leak a private source into a public repo, code blocks it and says why." |

Rehearse Act 6 first: whether Dana's draft cites the private thread depends on the run. If no live draft does, use a recorded Dana run and say "recorded".

### Act 7 · Does the graph actually matter? (2:30–2:55)

| Time | On screen | Voice-over |
|---|---|---|
| 2:30 | Arjun, click **Compare Graph ON vs OFF** (recorded runs). Hold on the table, zooming into rows as you name them. | "This is what I wanted to learn. Same alert, same agents, same models, but Graph OFF only gets vector search. It still finds PR 482, because the PR's text mentions the TTL." |
| 2:42 | Zoom on suspects ruled out, severity, evidence path, who to page, time, cost. | "But it takes twice as long, costs three and a half times as much, never checks the red herring, and can't say how bad it is or who to wake up. On our 59-question eval: 75% recall with the graph, 38% without." |

### Act 8 · It learns (2:55–3:10)

| Time | On screen | Voice-over |
|---|---|---|
| 2:55 | Story B alert (A-3002), run as Arjun; zoom on the playbook step. | "When a human confirms the cause, it becomes a playbook in the graph. A week later, a different service breaks the same way, and the Investigator needs 4 steps instead of 8." |
| 3:05 | The agent architecture canvas, "Which design template it follows" artboard, slow pan. | "Under the hood it's a fixed workflow of four agents, with code checking the facts between them and a human at the end." |

### Act 9 · Back to 3 AM (3:10–3:30)

| Time | On screen | Voice-over |
|---|---|---|
| 3:10 | Black slide, **"03:00"** again, then a cut to Lore's finished report. | "Next time his pager goes off, he wakes up to the context, not just the alert." |
| 3:16 | End card: "Lore · built solo for Graph Hacks" · the live URL · github.com/ayan2809/Lore · "Built with Claude Code (disclosed in the README)". | "I built Lore solo in four days, new to graphs, with Claude Code as my coding assistant. I planned it, tested it, broke it and fixed it. The repo says exactly how. Thanks, FalkorDB and WeMakeDevs." |

---

## Production (screen + voice only)

**Before you record**
- Reload the live site; check the health dots are green and "live" is shown. A live run costs about $0.03–0.04 and uses 1 of 100 daily runs.
- Do one rehearsal run as Arjun. If the report summary names the wrong service (it said "promo-engine" once in testing), run again or use the recorded run for Act 4, and say it's recorded.
- Make the slides first: black background, white text, one idea per slide, citations in small grey text.

**Screen**
- 1920×1080, 30 fps, browser zoom 110%, bookmarks bar hidden, notifications off (macOS: Focus on).
- QuickTime (File › New Screen Recording) or OBS. Turn on click highlighting if your recorder has it.
- Record each act as its own clip; it's easier to redo one.
- Zoom in during editing on what you're talking about (the alert card, a Cypher step, the report). Don't leave a full screen on view for more than 4 s without a zoom or movement.

**Voice**
- Record the voice-over after the screen clips, act by act, in a quiet room with the phone 15 cm from your mouth, or any USB mic. Voice-type the narration first, then read it naturally.
- Keep *"Bhai uth jaa, page hogaya hai!"* raw and real, with English subtitles.
- Music: one low ambient track only under Acts 1–3 and 9. Silence under the product demo, so the narration is clear.

**Edit and upload**
- Subtitles on the whole video (judges often watch muted).
- YouTube chapters: 0:00 The pager · 0:20 Why 3 AM is hard · 0:35 Why a graph · 0:50 Live investigation · 1:50 Permissions · 2:10 Human in the loop · 2:30 Graph ON vs OFF · 2:55 Memory · 3:10 Close.
- Title: "Lore: waking up to the context, not just the alert · FalkorDB Graph Hacks". Thumbnail: the lit evidence path with "03:00" in large type.
- Upload to YouTube (public or unlisted) before 23:59 IST. Put the link on the README's "Demo video" line (under Live link and video) and in the submission form.

---

## Numbers and facts you can say

| Claim | Source |
|---|---|
| Story A live: PR #482 found and PR #479 ruled out in 6 of 6 runs; about 50–60 s; $0.022–0.027 a run | `docs/FIX_LOG.md`, test results |
| Today's live check after the deploy: all 9 checks passed; root cause at 54.6 s; $0.039 | live run on the deployed site |
| Tool calls take a few milliseconds (1–7 ms in today's live run) | the run's trail |
| Retrieval recall@5: 75% with the graph vs 38% without; lookups 93% vs 11% | `backend/eval/report.md` |
| Leaks: 0 across 4 personas × 63 test questions | eval reports, leak tests |
| Compare on A-3001: 54 s vs 102 s to the root cause; $0.026 vs $0.091 | FIX_LOG F-19 (one recorded run each) |
| Playbook: Story B Investigator 8 → 4 steps, 50 s → 39 s | FIX_LOG F-11 |
| Acute stress quickly impairs prefrontal cortex functions | Arnsten 2009, *Nature Reviews Neuroscience* |
| Sleep loss raises amygdala reactivity and weakens its link to the prefrontal cortex | Yoo et al. 2007, *Current Biology* |

Don't say "zero hallucinations" or "under 15 seconds": neither was measured. Don't say the amygdala "takes over" the brain or that the prefrontal cortex "does all our thinking": both overstate the science. Don't name your roommate's company or the real incident's details.
