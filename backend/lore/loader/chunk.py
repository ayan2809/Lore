"""Split source text into small chunks for vector search.

A Chunk is a ~500 character piece of a source (PR, Thread, Ticket, Doc, Decision, Incident).
Its id is `<source id>#<n>` (e.g. `adr:011#0`). Each chunk copies the source's access properties,
so a permission check can be done on the chunk itself and on the source it is PART_OF.
"""

from __future__ import annotations

import re

TARGET_CHARS = 500
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Node labels that carry text. Alerts, deploys and org nodes have none.
SOURCE_LABELS = ("PR", "Thread", "Ticket", "Doc", "Decision", "Incident")
# Access properties copied from the source onto each chunk
ACCESS_PROPS = ("source", "team", "service", "updated_at", "access_level")


def _pieces(text: str, target: int) -> list[str]:
    """Break text into units no longer than `target`: lines, then sentences, then words."""
    out: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) <= target:
            out.append(line)
            continue
        for sentence in SENTENCE_END.split(line):
            while len(sentence) > target:  # a very long sentence: cut at a space
                cut = sentence.rfind(" ", 0, target)
                if cut <= 0:
                    cut = target
                out.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                out.append(sentence)
    return out


def chunk_text(text: str, target: int = TARGET_CHARS) -> list[str]:
    """Pack consecutive pieces into chunks of about `target` characters (never empty)."""
    chunks: list[str] = []
    current = ""
    for piece in _pieces(text, target):
        if current and len(current) + 1 + len(piece) > target:
            chunks.append(current)
            current = piece
        else:
            current = f"{current}\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks


def source_text(props: dict) -> str:
    """The text of a source node: its title (if the text does not already start with it) + body."""
    title = (props.get("title") or "").strip()
    body = (props.get("text") or "").strip()
    if title and title.lower() not in body[: len(title) + 40].lower():
        return f"{title}\n{body}"
    return body


def make_chunks(node: dict) -> list[dict]:
    """Chunks for one node from nodes.json: [{"id", "src", "props"}, ...]. Empty if no text."""
    if node["label"] not in SOURCE_LABELS:
        return []
    props = node["props"]
    access = {k: props[k] for k in ACCESS_PROPS if k in props}
    return [
        {"id": f"{node['id']}#{i}", "src": node["id"], "src_label": node["label"],
         "props": {**access, "text": text, "chunk_index": i}}
        for i, text in enumerate(chunk_text(source_text(props)))
    ]  # fmt: skip
