# Discovery brief: Kettle engineering

> Standalone copy of `plan.md` section 0. The customer is fictional and all data is synthetic (hackathon rule 6).
> These numbers are made up for the story. They are identical in the README, the video and the blog. Do not change one without changing all of them.

Lore starts from a customer problem, not from a technology: a fictional food-delivery startup whose on-call engineers lose almost an hour at the start of every serious incident, and sometimes wake up the wrong person.

| Item | Kettle (a fictional food-delivery startup) |
|---|---|
| **Customer** | Kettle's engineering department: 45 engineers in 6 teams, running about 30 microservices (small programs that each do one job and talk to each other) |
| **Users** | On-call engineers, who take turns each week and many of whom joined in the last 6 months; incident commanders, who lead the response during an outage; engineering managers; and contractors, who have limited access |
| **Current workflow** | An alert fires. The on-call engineer opens a Slack "war room" channel, scrolls through recent GitHub merges and deploy logs, searches Slack and the design decision records (ADRs), asks "who knows pricing?" in #eng, and finally pages whoever the CODEOWNERS file lists |
| **Pain** | It takes a median of **47 minutes** from alert to finding the cause of serious (P1/P2) incidents. **3 of the last 10** incidents paged the wrong person first. Knowledge left with people who changed teams. |
| **Systems involved** | GitHub (PRs, reviews, CODEOWNERS), deploy pipeline logs, Slack (public and private channels), Jira, ADRs and docs, incident history |
| **Constraints** (rules the solution must respect) | 1. People may see only what their access allows: private channels, security incidents and HR are restricted, contractors see public content only, and access changes when someone changes team. 2. Data changes constantly: code merges and deploys land every few minutes. 3. No automatic changes to production: a human approves every action that leaves the system. 4. Only synthetic (made-up) data is allowed (hackathon rule 6). |
| **Success metrics** (how we know it works) | Time from alert to cause **under 3 minutes**. The right owner and expert named the first time. **Zero permission leaks** in the tests. **At least 90%** of statements in answers carry a valid source link. Correct refusals when someone asks about something they can't see. |

## Headline numbers

| Today | Target with Lore |
|---|---|
| 47 min median from alert to cause (P1/P2) | under 3 min |
| 3 of the last 10 incidents paged the wrong person first | right owner and expert named the first time |
| n/a | 0 permission leaks in the tests |
| n/a | at least 90% of statements carry a valid source link |

The "today" column is the story's baseline. Whether Lore reaches the targets is measured in `backend/eval/report.md` and summarised in the README (TODO until the evals have run).
