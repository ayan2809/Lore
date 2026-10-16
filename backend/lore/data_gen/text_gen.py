"""Write realistic Slack/Jira/ADR/wiki text with Gemini Flash, ONCE.

    uv run python -m lore.data_gen.text_gen             # needs LORE_GEMINI_API_KEY
    uv run python -m lore.data_gen.text_gen --dry-run   # print the prompts, call nothing
    uv run python -m lore.data_gen.text_gen --only threads --limit 8

Output: backend/data/text/{threads,tickets,adrs,docs}.json, each {item id: {title, text, ...}}.
Run `python -m lore.data_gen.generate` afterwards; it uses this text instead of the templates.
Commit the files so the demo data never changes.

Safety net: planted facts (e.g. "300s", "ADR-011", "PR #211") are passed to the model as required
facts. An item whose text lacks any of them is dropped here, and generate.py falls back to the
template text for it. Gemini never touches the graph structure, only the words.
"""

from __future__ import annotations

import argparse
import json
import sys

from pydantic import BaseModel

from lore.config import get_settings
from lore.data_gen.generate import DATA_DIR, TEXT_FILES, TextSlot, text_slots

BATCH_SIZE = 8

STYLE = {
    "thread": "A short Slack conversation of 2-5 messages. Every line is 'FirstName: message'. "
    "Casual, specific, engineer-to-engineer. No emojis. Put the title in `title` (a short "
    "subject) and the messages, one per line, in `text`.",
    "ticket": "A Jira ticket. `title` is one line. `text` is 2-4 sentences: the problem, why it "
    "matters, and what done looks like.",
    "adr": "An architecture decision record. `title` starts with the ADR number. `summary` is one "
    "sentence. `text` has the lines Status, Context, Decision, Consequences.",
    "doc": "An internal wiki page, runbook or postmortem (the context says which). `title` is "
    "short, `summary` is one sentence, `text` is 3-6 sentences.",
}


class Item(BaseModel):
    id: str
    title: str
    text: str
    summary: str = ""


def build_prompt(kind: str, batch: list[TextSlot]) -> str:
    lines = [
        "You write realistic internal text for Kettle, a fictional food-delivery startup.",
        "All people, services and numbers are fictional. Keep each item short and plausible.",
        STYLE[kind],
        "Rules: keep facts consistent with the context; include every REQUIRED fact verbatim "
        "(same spelling, same numbers); do not invent other numbers about caching, TTLs or "
        "rate limits; do not mention real companies. Return one object per item, "
        "using the given id.",
        "",
    ]
    for s in batch:
        lines.append(f"ITEM id={s.id}")
        lines.append(f"  context: {s.context}")
        lines.append(f"  REQUIRED facts: {s.required or 'none'}")
        lines.append(f"  draft to improve: {json.dumps(s.default, ensure_ascii=False)}")
    return "\n".join(lines)


def is_valid(item: Item, slot: TextSlot) -> bool:
    """Non-trivial text that still contains every required fact."""
    blob = f"{item.title} {item.text}".lower()
    return 20 <= len(item.text) <= 2500 and all(f.lower() in blob for f in slot.required)


def call_gemini(client, model: str, prompt: str) -> list[Item]:
    from google.genai import types

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[Item],
            temperature=0.8,
        ),
    )
    return [Item(**row) for row in json.loads(response.text)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="print prompts, call nothing")
    parser.add_argument("--only", choices=sorted(TEXT_FILES.values()), help="one output file")
    parser.add_argument("--limit", type=int, help="max items per kind (for a cheap trial run)")
    args = parser.parse_args(argv)

    settings = get_settings()
    if not args.dry_run and not settings.gemini_api_key:
        print(
            "No Gemini API key found. Set LORE_GEMINI_API_KEY (in backend/.env or the shell) and "
            "run again. Until then `python -m lore.data_gen.generate` uses template text, which "
            "is fine for development.",
            file=sys.stderr,
        )
        return 1

    client = None
    if not args.dry_run:
        from google import genai

        client = genai.Client(api_key=settings.gemini_api_key)

    out_dir = DATA_DIR / "text"
    out_dir.mkdir(parents=True, exist_ok=True)
    slots = text_slots()
    for kind, filename in TEXT_FILES.items():
        if args.only and args.only != filename:
            continue
        mine = [s for s in slots if s.kind == kind][: args.limit]
        path = out_dir / f"{filename}.json"
        saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        todo = [s for s in mine if s.id not in saved]  # resume: skip what is already written
        kept = dropped = 0
        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i : i + BATCH_SIZE]
            prompt = build_prompt(kind, batch)
            if args.dry_run:
                print(f"--- {filename} batch {i // BATCH_SIZE} ---\n{prompt}\n")
                continue
            by_id = {s.id: s for s in batch}
            for item in call_gemini(client, settings.model_flash, prompt):
                slot = by_id.get(item.id)
                if slot and is_valid(item, slot):
                    saved[item.id] = {k: v for k, v in item.model_dump().items() if k != "id" and v}
                    kept += 1
                else:
                    dropped += 1  # template text will be used for it
            path.write_text(
                json.dumps(saved, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if not args.dry_run:
            print(f"{filename}: kept {kept}, dropped {dropped} (fall back to templates)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
