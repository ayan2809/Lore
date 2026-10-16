"""The Kettle story bible (docs/story-bible.md) as plain Python constants.

Everything the generator must reproduce EXACTLY lives here: named people, teams, roles, channels,
the 30 services and their dependencies, and the planted stories A-E with exact ids and times.
Random filler (the other PRs, threads, tickets...) is made in generate.py.

All times are written in IST (+05:30) and converted to Unix seconds with `ist()`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def ist(text: str) -> int:
    """'2026-10-14 03:00' (IST) -> Unix seconds. A date alone means 10:00 IST."""
    if " " not in text:
        text += " 10:00"
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=IST).timestamp())


# ------------------------------------------------------------------ time anchors

DATA_START = ist("2025-10-01 09:00")  # earliest filler PR / thread
FILLER_END = ist("2026-10-12 18:00")  # latest filler PR (the planted ones land after this)
MARCO_MOVE = ist("2026-08-01 00:00")  # Marco leaves Pricing, joins Data
SEED = 20261015

# ------------------------------------------------------------------ teams and roles

TEAMS = ["checkout", "pricing", "dispatch", "payments", "data", "platform"]
TEAM_LEADS = {
    "pricing": "rahul",
    "dispatch": "kofi",
    "payments": "hana",
    "checkout": "meera",
    "data": "neha",
    "platform": "isha",
}
# Ticket key prefix per owning team (story-bible section 8)
TICKET_PREFIX = {
    "checkout": "CHK",
    "pricing": "PRC",
    "dispatch": "DSP",
    "payments": "PAY",
    "data": "DAT",
    "platform": "PLT",
}
ROLES = ["oncall-engineer", "incident-commander", "security", "eng-manager", "hr", "contractor"]

# ------------------------------------------------------------------ channels
# (slug, private, access_level of its threads, ids the threads are VISIBLE_TO)

CHANNELS = [
    ("general", False, "public", []),
    ("eng", False, "internal", []),
    ("incidents", False, "internal", []),
    ("oncall", False, "internal", []),
    ("checkout", False, "internal", []),
    ("pricing", False, "internal", []),
    ("dispatch", False, "internal", []),
    ("payments", False, "internal", []),
    ("data", False, "internal", []),
    ("platform", False, "internal", []),
    ("pricing-private", True, "restricted", ["channel:pricing-private", "role:incident-commander"]),
    ("sec-incidents", True, "confidential", ["role:security"]),
    ("hr-private", True, "restricted", ["role:hr"]),
]
# Number of threads per channel (sums to 150)
THREADS_PER_CHANNEL = {
    "general": 22, "eng": 20, "incidents": 12, "oncall": 10,
    "checkout": 12, "pricing": 12, "dispatch": 12, "payments": 12, "data": 12, "platform": 12,
    "pricing-private": 6, "sec-incidents": 4, "hr-private": 4,
}  # fmt: skip
# Thread number -> time in the private channels (the planted ones are 0142, 0150, 0007, 0003)
PRIVATE_THREAD_TIMES = {
    "pricing-private": {
        139: "2026-01-28 15:00", 142: "2026-02-09 16:20", 145: "2026-02-26 12:10",
        148: "2026-03-10 17:45", 150: "2026-04-02 11:30", 153: "2026-06-18 14:00",
    },
    "sec-incidents": {
        5: "2025-12-05 10:20", 6: "2026-02-17 16:40", 7: "2026-03-26 14:30",
        9: "2026-06-11 13:15",
    },
    "hr-private": {
        1: "2025-11-10 10:00", 2: "2026-03-16 11:30", 3: "2026-07-02 10:30",
        4: "2026-09-14 15:00",
    },
}  # fmt: skip

# ------------------------------------------------------------------ people (45)
# (slug, display name, current team or None, job title, joined, extra roles)
# Persona channels are listed separately below because the bible fixes them exactly.

PEOPLE = [
    # --- named in the story bible
    ("rahul", "Rahul Verma", "pricing", "Pricing Team Lead", "2023-01-16", ["eng-manager"]),
    ("priya", "Priya Nair", "pricing", "Senior Engineer", "2024-05-06", []),
    ("wei", "Wei Zhang", "pricing", "Engineer", "2024-02-12", []),
    ("marco", "Marco Bianchi", "data", "Staff Engineer", "2023-04-01", []),
    ("leah", "Leah Cohen", "checkout", "Engineer", "2025-03-10", []),
    ("tomas", "Tomás García", "dispatch", "Senior Engineer", "2024-09-02", []),
    ("ines", "Ines Duarte", "payments", "Staff Engineer", "2023-08-21", []),
    ("kofi", "Kofi Mensah", "dispatch", "Dispatch Team Lead", "2022-11-07", ["eng-manager"]),
    ("hana", "Hana Sato", "payments", "Payments Team Lead", "2023-02-13", ["eng-manager"]),
    # --- demo personas
    ("arjun", "Arjun Mehta", "checkout", "Engineer", "2026-09-23", ["oncall-engineer"]),
    ("dana", "Dana Okafor", "platform", "Incident Commander", "2022-06-20",
     ["incident-commander", "security"]),
    ("sam", "Sam Rivera", None, "Contractor", "2026-08-17", ["contractor"]),
    # --- generated people
    ("meera", "Meera Iyer", "checkout", "Checkout Team Lead", "2022-09-12", ["eng-manager"]),
    ("omar", "Omar Haddad", "checkout", "Senior Engineer", "2023-06-05", ["oncall-engineer"]),
    ("chloe", "Chloe Martin", "checkout", "Engineer", "2024-11-18", ["oncall-engineer"]),
    ("vikram", "Vikram Singh", "checkout", "Engineer", "2025-01-27", []),
    ("elena", "Elena Petrova", "checkout", "Engineer", "2025-07-14", []),
    ("jonas", "Jonas Weber", "checkout", "Engineer", "2026-05-18", []),
    ("nikhil", "Nikhil Rao", "pricing", "Engineer", "2024-03-04", []),
    ("aisha", "Aisha Khan", "pricing", "Engineer", "2025-02-17", []),
    ("diego", "Diego Alvarez", "pricing", "Senior Engineer", "2023-10-09", ["oncall-engineer"]),
    ("yuki", "Yuki Tanaka", "pricing", "Engineer", "2026-04-27", []),
    ("farah", "Farah Ali", "dispatch", "Engineer", "2026-05-04", []),
    ("lucas", "Lucas Oliveira", "dispatch", "Senior Engineer", "2023-12-04", ["oncall-engineer"]),
    ("anita", "Anita Desai", "dispatch", "Engineer", "2024-07-22", []),
    ("ben", "Ben Carter", "dispatch", "Engineer", "2025-04-07", []),
    ("mei", "Mei Lin", "dispatch", "Engineer", "2025-09-15", []),
    ("sofia", "Sofia Rossi", "payments", "Senior Engineer", "2023-05-15", ["oncall-engineer"]),
    ("ravi", "Ravi Menon", "payments", "Engineer", "2024-06-10", ["oncall-engineer"]),
    ("gita", "Gita Sharma", "payments", "Engineer", "2026-06-01", []),
    ("tobias", "Tobias Nielsen", "payments", "Engineer", "2025-05-26", []),
    ("neha", "Neha Kapoor", "data", "Data Team Lead", "2022-08-29", ["eng-manager"]),
    ("ahmed", "Ahmed Said", "data", "Senior Engineer", "2023-09-18", ["oncall-engineer"]),
    ("lina", "Lina Moreau", "data", "Engineer", "2024-10-14", []),
    ("pavel", "Pavel Novak", "data", "Engineer", "2024-01-22", ["oncall-engineer"]),
    ("zoe", "Zoe Adams", "data", "Engineer", "2026-06-22", []),
    ("karan", "Karan Malhotra", "data", "Engineer", "2026-07-06", []),
    ("isha", "Isha Reddy", "platform", "Platform Team Lead", "2022-05-02",
     ["eng-manager", "incident-commander"]),
    ("hugo", "Hugo Bernard", "platform", "Senior Engineer", "2023-03-27",
     ["oncall-engineer", "incident-commander"]),
    ("amara", "Amara Okeke", "platform", "Security Engineer", "2024-04-15",
     ["oncall-engineer", "security"]),
    ("sven", "Sven Larsen", "platform", "Engineer", "2024-08-12", ["oncall-engineer"]),
    ("tara", "Tara Joshi", "platform", "Engineer", "2025-06-02", []),
    ("mateo", "Mateo Silva", "platform", "Engineer", "2025-10-20", []),
    ("noor", "Noor Rahman", "platform", "Engineer", "2026-03-09", []),
    ("felix", "Felix Braun", "platform", "Engineer", "2026-05-25", []),
]  # fmt: skip

# Channels each demo person is IN (story-bible section 4). Everyone else is derived in generate.py.
PERSONA_CHANNELS = {
    "arjun": ["general", "eng", "incidents", "oncall", "checkout"],
    "dana": ["general", "eng", "incidents", "oncall", "platform", "sec-incidents"],
    "sam": ["general"],
    "marco": ["general", "eng", "data"],
}
PRICING_PRIVATE_MEMBERS = ["rahul", "priya", "wei"]  # current members of #pricing-private
# Marco's history: he was in Pricing and in #pricing-private until he moved to Data.
MARCO_PRICING_FROM = ist("2023-04-01 00:00")

# ------------------------------------------------------------------ services (30)
# (name, tier, owner team, depends on)

SERVICES = [
    ("api-gateway", 1, "platform", ["auth"]),
    ("auth", 1, "platform", ["user-profile"]),
    ("checkout", 1, "checkout",
     ["cart", "promo-engine", "payments-gateway", "orders", "auth"]),
    ("cart", 2, "checkout", ["menu", "inventory"]),
    ("promo-engine", 2, "checkout", ["pricing", "feature-flags"]),
    ("pricing", 1, "pricing", ["menu", "config-service", "feature-flags"]),
    ("surge-pricing", 2, "pricing", ["pricing", "rider-location"]),
    ("menu", 2, "pricing", ["restaurant-catalog"]),
    ("restaurant-catalog", 3, "data", []),
    ("inventory", 2, "checkout", ["restaurant-catalog"]),
    ("orders", 1, "checkout", ["ledger", "notifications"]),
    ("payments-gateway", 1, "payments", ["fraud-check", "ledger"]),
    ("ledger", 2, "payments", []),
    ("fraud-check", 2, "payments", ["user-profile"]),
    ("refunds", 2, "payments", ["ledger", "payments-gateway"]),
    ("invoices", 3, "payments", ["ledger"]),
    ("courier-payouts", 2, "payments", ["ledger"]),
    ("dispatch", 1, "dispatch", ["eta-predictor", "rider-location", "orders"]),
    ("eta-predictor", 2, "dispatch", ["maps-proxy", "feature-flags"]),
    ("rider-location", 2, "dispatch", ["maps-proxy"]),
    ("maps-proxy", 3, "dispatch", []),
    ("notifications", 2, "platform", ["user-profile"]),
    ("user-profile", 2, "platform", []),
    ("feature-flags", 1, "platform", []),
    ("config-service", 2, "platform", []),
    ("search", 2, "data", ["restaurant-catalog"]),
    ("recommendation", 3, "data", ["search", "analytics-ingest"]),
    ("analytics-ingest", 3, "data", []),
    ("reviews", 3, "data", ["user-profile"]),
    ("support-desk", 3, "platform", ["orders", "user-profile"]),
]  # fmt: skip

# Modules that story-bible fixes; every other service gets 2-4 random ones (generate.py).
FIXED_MODULES = {
    "checkout": ["config.yaml", "i18n/en.json", "handlers.py"],
    "pricing": ["config.yaml", "cache.py", "rules.py"],
    "eta-predictor": ["config.yaml", "model.py", "features.py"],
    "notifications": ["config.yaml", "sender.py", "templates/push.json"],
    "ledger": ["config.yaml", "entries.py", "reconcile.py"],
}
MODULE_POOL = ["handlers.py", "models.py", "client.py", "service.py", "jobs.py", "utils.py"]

# How many filler PRs each service gets. Sum must be 296 = 300 - the 4 planted PRs
# (#479, #482, #517, #518). PR #211 is counted under pricing.
FILLER_PRS_PER_SERVICE = {
    "api-gateway": 14, "auth": 14, "checkout": 30, "cart": 12, "promo-engine": 12,
    "pricing": 45, "surge-pricing": 8, "menu": 8, "restaurant-catalog": 5, "inventory": 7,
    "orders": 18, "payments-gateway": 12, "ledger": 12, "fraud-check": 6, "refunds": 6,
    "invoices": 4, "courier-payouts": 4, "dispatch": 18, "eta-predictor": 8,
    "rider-location": 7, "maps-proxy": 4, "notifications": 7, "user-profile": 6,
    "feature-flags": 6, "config-service": 4, "search": 6, "recommendation": 4,
    "analytics-ingest": 3, "reviews": 3, "support-desk": 3,
}  # fmt: skip
MARCO_PRICING_PRS = 30  # Marco authors this many pricing PRs before 2026-08-01 (rule: >= 25)
FILLER_PR_NUMBER_RANGE = (180, 478)  # numbers not used by planted PRs (211 is planted too)
FILLER_DEPLOYS = 136  # + 4 planted = 140 deploys
FILLER_DEPLOY_FIRST_NUMBER = (
    854  # filler deploys are 854..989; planted ones are 990, 991, 1034, 1035
)

# ------------------------------------------------------------------ planted stories

# Planted PRs. `mods` = (module file, edge props). `text` is the PR description.
STORY_PRS = {
    211: dict(
        service="pricing", author="nikhil", reviewer="aisha", merged_at=ist("2026-03-05 15:40"),
        title="Lower pricing cache TTL to 30s",
        text="Lowers pricing cache_ttl_seconds from 300 to 30 so promo price changes show up "
        "faster. Reverted on 2026-03-07 during INC-0307.",
        mods=[("config.yaml", {"key": "cache_ttl_seconds", "old": 300, "new": 30})],
    ),
    479: dict(
        service="checkout", author="leah", reviewer="meera", merged_at=ist("2026-10-14 02:20"),
        title="Update checkout button copy",
        text="Copy-only change: the checkout button now says 'Pay now' instead of 'Place order'. "
        "Only touches the English strings file. No logic changes.",
        mods=[("i18n/en.json", {})],
    ),
    482: dict(
        service="pricing", author="priya", reviewer="wei", merged_at=ist("2026-10-13 18:10"),
        title="Lower pricing cache TTL to 5s for faster promo updates",
        text="Lowers pricing cache_ttl_seconds from 300 to 5 so promo price changes show up "
        "quickly. Fixes PRC-311 (promo price changes take 5 minutes to show).",
        mods=[("config.yaml", {"key": "cache_ttl_seconds", "old": 300, "new": 5})],
        fixes="ticket:PRC-311",
    ),
    517: dict(
        service="eta-predictor", author="tomas", reviewer="kofi", merged_at=ist("2026-10-20 17:40"),
        title="Reduce eta-predictor model cache TTL to 10s",
        text="Reduces the eta-predictor model cache TTL to 10s so ETA estimates pick up new "
        "model versions faster.",
        mods=[("config.yaml", {"key": "model_cache_ttl_seconds", "new": 10})],
    ),
    518: dict(
        service="notifications", author="tara", reviewer="noor", merged_at=ist("2026-10-20 23:30"),
        title="Fix typo in push template",
        text="Fixes a typo in the order-ready push notification template. Text only.",
        mods=[("templates/push.json", {})],
    ),
}  # fmt: skip

# Planted deploys: number -> (service, time, PR numbers). 990 is the red herring for Story A.
STORY_DEPLOYS = {
    991: ("pricing", ist("2026-10-14 01:30"), [482]),
    990: ("checkout", ist("2026-10-14 02:48"), [479]),
    1034: ("eta-predictor", ist("2026-10-21 01:50"), [517]),
    1035: ("notifications", ist("2026-10-21 02:55"), [518]),
}

STORY_ALERTS = {
    "A-3001": dict(
        service="checkout", symptom="checkout p99 latency > 3s", at=ist("2026-10-14 03:00")
    ),
    "A-3002": dict(
        service="dispatch", symptom="dispatch assignment latency > 5s", at=ist("2026-10-21 03:10")
    ),
}

# ------------------------------------------------------------------ planted text
# Each entry: title, text, and `required` = facts that must survive if Gemini rewrites the text
# (text_gen.py validates this; generate.py re-validates). Numbers like 600 rpm are invented.

PLANTED_TEXT: dict[str, dict] = {
    "adr:011": dict(
        title="ADR-011: Pricing cache TTL must stay at 300s or higher",
        summary="Pricing cache TTL must stay at 300s or higher because of the vendor rate limit.",
        text=(
            "ADR-011: Pricing cache TTL must stay at 300s or higher.\n"
            "Status: accepted. Date: 2026-02-10. Author: Marco Bianchi.\n"
            "Context: The pricing service caches computed prices. The vendor tax/price API "
            "enforces a rate limit. In early February a low TTL during a promo test nearly "
            "exhausted that limit (a near-miss).\n"
            "Decision: The pricing cache TTL (cache_ttl_seconds in pricing/config.yaml) must stay "
            "at 300 seconds or higher. Any change below 300s needs a new ADR that supersedes "
            "this one.\n"
            "Consequences: Promo price changes can take up to 5 minutes to show. Faster updates "
            "should use cache invalidation, not a lower TTL.\n"
            "This ADR supersedes the wiki page 'Pricing cache' which said a 60s TTL is fine."
        ),
        required=["300s", "vendor", "rate limit", "supersede"],
    ),
    "thread:pricing-private-0142": dict(
        title="Why the pricing cache TTL cannot go below 300s",
        text=(
            "Marco: Before anyone touches the pricing cache TTL, I want to write down why we "
            "cannot go below 300s.\n"
            "Marco: The vendor tax/price API is limited to 600 requests per minute on our "
            "contract. At a 30s TTL our peak traffic would reach roughly 1,900 requests per "
            "minute, so we would be throttled and pricing would fall over. Last week's "
            "near-miss was exactly that.\n"
            "Rahul: Agreed. Let's make it a decision record: the pricing cache TTL stays at 300s "
            "or higher until the vendor limit is renegotiated.\n"
            "Wei: I can add a comment in config.yaml that points to the ADR.\n"
            "Marco: I'll write ADR-011 tomorrow and link this thread. The contract numbers stay "
            "in this channel."
        ),
        required=["300s", "600 requests per minute", "ADR-011", "vendor"],
    ),
    "thread:pricing-private-0150": dict(
        title="Vendor contract renewal rates",
        text=(
            "Rahul: The vendor sent renewal terms for the tax/price API. Our plan includes 600 "
            "requests per minute. The next tier is 1,500 requests per minute for $4,200 more "
            "per month.\n"
            "Priya: That would allow a lower TTL, but it is a lot of money for faster promo "
            "updates.\n"
            "Rahul: Let's stay on the current tier until finance reviews. Please keep these "
            "rates inside this channel."
        ),
        required=["600 requests per minute", "1,500 requests per minute", "tier"],
    ),
    "thread:sec-incidents-0007": dict(
        title="Leaked payments API key in a public gist",
        text=(
            "Dana: Confirmed: a payments API key was pasted into a public gist by mistake. The "
            "gist was up for about 40 minutes before a scanner flagged it.\n"
            "Amara: The key is revoked and rotated. No suspicious charges in the ledger so far.\n"
            "Dana: Opening INC-0326 as confidential. Details stay in this channel and the "
            "postmortem goes to the security role only.\n"
            "Amara: I'll review the gist access logs and report back tomorrow."
        ),
        required=["gist", "API key", "INC-0326"],
    ),
    "thread:hr-private-0003": dict(
        title="Marco Bianchi: transfer to Data",
        text=(
            "HR: Marco Bianchi's transfer from Pricing to Data is approved, effective "
            "2026-08-01. Compensation band is unchanged. Sign-off from Rahul Verma and Neha "
            "Kapoor is on file. Please do not discuss this outside this channel."
        ),
        required=["Marco", "2026-08-01"],
    ),
    "thread:general-0003": dict(
        title="All-hands moved to Friday",
        text=(
            "Hana: Reminder: the all-hands moves to Friday 17:00 IST this month. Shout-out to "
            "the checkout service team for the smooth launch last week!"
        ),
        required=["all-hands", "Friday"],
    ),
    "ticket:PRC-311": dict(
        title="Promo price changes take 5 minutes to show",
        text=(
            "Support reports that promo price changes take about 5 minutes to appear in the app. "
            "Merchants expect them within seconds. Suspected cause: the pricing cache. "
            "Needs a fix that does not hurt the pricing service."
        ),
        required=["5 minutes"],
    ),
    "wiki:pricing-cache": dict(
        title="Pricing cache: 60s TTL is fine",
        summary="Old wiki page saying a 60s TTL is fine for the pricing cache.",
        text=(
            "Pricing cache: the pricing service caches computed prices. A 60s TTL is fine for "
            "normal traffic. Lower values only matter for promo freshness. The setting is "
            "cache_ttl_seconds in pricing/config.yaml."
        ),
        required=["60s"],
    ),
    "runbook:pricing-oncall": dict(
        title="Pricing on-call runbook",
        summary="Old runbook: page Marco for pricing incidents.",
        text=(
            "Pricing on-call runbook. When pricing latency or error alerts fire: 1. Check the "
            "pricing dashboard. 2. Page Marco Bianchi: he knows pricing best. 3. If checkout is "
            "also slow, post an update in #incidents. 4. Roll back the last pricing deploy if "
            "the dashboard shows it started right after."
        ),
        required=["Page Marco"],
    ),
    "pm:INC-0307": dict(
        title="Postmortem INC-0307: pricing overload after cache TTL lowered to 30s",
        summary="PR #211 lowered the pricing cache TTL to 30s and overloaded the vendor API.",
        text=(
            "Postmortem INC-0307. Summary: PR #211 lowered the pricing cache TTL from 300s to "
            "30s. Request volume to the vendor tax/price API tripled, pricing latency rose and "
            "checkout slowed down. Marco reverted PR #211 and restored 300s. Root cause: the "
            "change ignored ADR-011, which says the TTL must stay at 300s or higher. Actions: "
            "add a CI check that blocks a TTL below 300s; link ADR-011 from config.yaml."
        ),
        required=["INC-0307", "PR #211", "30s", "300s", "ADR-011"],
    ),
    "pm:INC-0326": dict(
        title="Postmortem INC-0326: leaked payments API key",
        summary="A payments API key was exposed in a public gist and rotated.",
        text=(
            "Postmortem INC-0326. A payments API key was pasted into a public gist. A scanner "
            "flagged it after about 40 minutes. The key was revoked and rotated within 25 "
            "minutes of detection. No fraudulent charges found. Actions: add a pre-commit "
            "secret scanner and rotate all payments keys quarterly."
        ),
        required=["INC-0326", "gist"],
    ),
}

# Planted incidents. `cause_pr` / `resolver` None means "pick filler" (see generate.py).
INCIDENTS = [
    # key, start, severity, title, services affected, resolver, cause PR number, special
    ("INC-0268", "2025-11-04 11:20", "P2", "Cart totals wrong for coupon orders",
     ["cart", "checkout"], "omar"),
    ("INC-0279", "2025-12-12 19:05", "P3", "Rider assignment delayed by maps-proxy timeouts",
     ["maps-proxy", "dispatch"], "lucas"),
    ("INC-0288", "2026-01-19 09:40", "P2", "Duplicate refunds after a payment retry",
     ["refunds", "ledger", "payments-gateway"], "ines"),
    ("INC-0297", "2026-02-24 14:15", "P3", "Feature flag evaluation slow for a few minutes",
     ["feature-flags"], "hugo"),
    ("INC-0307", "2026-03-07 02:15", "P1", "Pricing overload after cache TTL lowered to 30s",
     ["pricing", "checkout"], "marco"),
    ("INC-0326", "2026-03-26 14:05", "P1", "Leaked payments API key in a public gist",
     ["payments-gateway"], "dana"),
    ("INC-0341", "2026-04-22 08:30", "P2", "Search results empty after nightly index rebuild",
     ["search"], "pavel"),
    ("INC-0356", "2026-05-30 21:10", "P2", "Dispatch stalls when eta-predictor restarts",
     ["eta-predictor", "dispatch"], "kofi"),
    ("INC-0372", "2026-07-14 12:45", "P3", "Invoice PDFs missing line items",
     ["invoices"], "ravi"),
    ("INC-0389", "2026-09-02 20:00", "P2", "Notification delays during the evening peak",
     ["notifications"], "isha"),
]  # fmt: skip
INCIDENT_CAUSE_PR = {"INC-0307": 211}  # others: a recent filler PR on the first affected service
INCIDENT_ACCESS = {"INC-0326": "confidential"}  # everything else is internal

# Fifteen ADRs. 011 is planted (PLANTED_TEXT); the rest are filler.
# number, date, title, service, author slug
ADRS = [
    (1, "2025-01-14", "Use gRPC between internal services", "api-gateway", "hugo"),
    (2, "2025-03-03", "Risky rollouts go behind feature flags", "feature-flags", "isha"),
    (3, "2025-04-22", "The orders service owns the order state machine", "orders", "omar"),
    (4, "2025-06-10", "Ledger entries are append-only", "ledger", "ines"),
    (5, "2025-07-29", "Rider lookup uses geohash cells", "rider-location", "lucas"),
    (6, "2025-09-08", "The search index is rebuilt nightly", "search", "pavel"),
    (7, "2025-10-21", "Idempotency keys are required on payment calls", "payments-gateway",
     "sofia"),
    (8, "2025-11-26", "Menu images are served through the CDN", "menu", "diego"),
    (9, "2025-12-17", "Standard retry policy: 3 tries with jittered backoff", "api-gateway",
     "sven"),
    (10, "2026-01-21", "Notification templates are versioned", "notifications", "tara"),
    (11, "2026-02-10", "Pricing cache TTL must stay at 300s or higher", "pricing", "marco"),
    (12, "2026-03-31", "Service configuration lives in config-service", "config-service", "hugo"),
    (13, "2026-05-12", "Alerts page the owning team's on-call first", "api-gateway", "isha"),
    (14, "2026-06-30", "Recommendation features come from analytics-ingest", "recommendation",
     "ahmed"),
    (15, "2026-08-18", "Contractors read public channels only", "support-desk", "hugo"),
]  # fmt: skip

# Wiki pages and runbooks (the two planted ones are in PLANTED_TEXT). slug, kind, service, date
EXTRA_DOCS = [
    ("wiki:checkout-flow", "wiki", "checkout", "2025-08-12"),
    ("wiki:dispatch-overview", "wiki", "dispatch", "2025-09-30"),
    ("wiki:ledger-basics", "wiki", "ledger", "2025-10-14"),
    ("wiki:oncall-onboarding", "wiki", "api-gateway", "2026-01-09"),
    ("wiki:feature-flags-guide", "wiki", "feature-flags", "2026-04-02"),
    ("runbook:checkout-oncall", "runbook", "checkout", "2026-05-20"),
    ("runbook:dispatch-oncall", "runbook", "dispatch", "2026-05-22"),
    ("runbook:payments-oncall", "runbook", "payments-gateway", "2026-05-27"),
    ("runbook:platform-oncall", "runbook", "api-gateway", "2026-06-03"),
    ("runbook:data-oncall", "runbook", "search", "2026-06-09"),
]

# Thread numbers used in the planted threads (everything else is filler)
PLANTED_THREADS = {
    "thread:pricing-private-0142": dict(
        at="2026-02-09 16:20", author="marco", services=["pricing"],
        people=["marco", "rahul", "wei"],
    ),
    "thread:pricing-private-0150": dict(
        at="2026-04-02 11:30", author="rahul", services=["pricing"], people=["rahul", "priya"]
    ),
    "thread:sec-incidents-0007": dict(
        at="2026-03-26 14:30", author="dana", services=["payments-gateway"],
        people=["dana", "amara"],
    ),
    "thread:hr-private-0003": dict(
        at="2026-07-02 10:30", author="hr", services=[], people=["marco", "rahul", "neha"]
    ),
    "thread:general-0003": dict(
        at="2025-10-10 09:30", author="hana", services=["checkout"], people=["hana"]
    ),
}  # fmt: skip

# What must be true, kept here so tests and golden questions share one list.
RESTRICTED_THREADS = {
    "pricing-private": "restricted",
    "sec-incidents": "confidential",
    "hr-private": "restricted",
}
