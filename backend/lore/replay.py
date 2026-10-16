"""Record and play back investigations (plan section 11: "Gemini is down or out of quota").

- `Recorder` wraps an `emit` function and writes every StepEvent to replays/<name>.jsonl.
- `play()` re-emits a saved run with its original relative timing, as a NEW investigation id,
  and marks `replay=True` in the start and done events so the UI can label it clearly.
- Two file formats are accepted:
    *.jsonl         one StepEvent JSON object per line (what Recorder writes; git-ignored)
    *.replay.json   a JSON array of StepEvents, or {"note": ..., "events": [...]} (committable,
                    used for the hand-written sample)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from lore import actions
from lore.config import Settings, get_settings
from lore.models import Action, StepEvent

Emit = Callable[[StepEvent], Awaitable[None]]

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALERT_STORY = {"A-3001": "story_a", "A-3002": "story_b"}  # which recording belongs to which alert
MAX_GAP_S = 3.0  # recorded runs include slow model calls; never make the viewer wait longer
SUFFIXES = (".jsonl", ".replay.json")


def replay_dir(settings: Settings | None = None) -> Path:
    path = Path((settings or get_settings()).replay_dir)
    return path if path.is_absolute() else BACKEND_DIR / path


class Recorder:
    """`emit = Recorder("story_a_arjun", emit)` then use `emit` as usual."""

    def __init__(self, name: str, emit: Emit, settings: Settings | None = None):
        directory = replay_dir(settings)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{name}.jsonl"
        self.path.write_text("")  # start a fresh file
        self._emit = emit

    async def __call__(self, event: StepEvent) -> None:
        with self.path.open("a") as f:
            f.write(event.model_dump_json() + "\n")
        await self._emit(event)


def load_events(path: Path) -> list[StepEvent]:
    text = path.read_text()
    if path.name.endswith(".jsonl"):
        raw = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        data = json.loads(text)
        raw = data["events"] if isinstance(data, dict) else data
    return [StepEvent.model_validate(item) for item in raw]


def list_replays(settings: Settings | None = None) -> list[str]:
    """Names (without suffix) of every replay file available."""
    directory = replay_dir(settings)
    names = {
        p.name.removesuffix(s)
        for p in directory.glob("*")
        for s in SUFFIXES
        if p.name.endswith(s)
    }
    return sorted(names)


def find_replay(alert_id: str, persona_id: str, settings: Settings | None = None) -> Path | None:
    """Replay file for this alert and persona, e.g. story_a_arjun. None if nothing is recorded.

    `sample_story_a` (hand-written) is the fallback for Arjun so the UI can be demoed offline.
    """
    story = ALERT_STORY.get(alert_id.removeprefix("alert:"))
    if story is None:
        return None
    names = [f"{story}_{persona_id}"]
    if story == "story_a" and persona_id == "arjun":
        names.append("sample_story_a")
    directory = replay_dir(settings)
    for name in names:
        for suffix in SUFFIXES:
            if (directory / f"{name}{suffix}").exists():
                return directory / f"{name}{suffix}"
    return None


async def play(
    path: Path,
    emit: Emit,
    speed: float = 1.0,
    investigation_id: str | None = None,
) -> str:
    """Re-emit a recorded run. Returns the new investigation id."""
    events = load_events(path)
    new_id = investigation_id or f"inv:{uuid.uuid4().hex[:10]}"
    previous_ts = events[0].ts if events else 0.0
    for event in events:
        gap = min(max(event.ts - previous_ts, 0.0), MAX_GAP_S)
        previous_ts = event.ts
        if gap and speed > 0:
            await asyncio.sleep(gap / speed)
        await emit(_rewrite(event, new_id))
    return new_id


def _rewrite(event: StepEvent, new_id: str) -> StepEvent:
    """Copy of the event for the new run: new id, new timestamp, replay flags set."""
    out = event.model_copy(update={"investigation_id": new_id, "ts": time.time()})
    payload = dict(event.payload)
    if event.type in ("investigation_started", "done"):
        payload["replay"] = True
    if event.type == "done":
        payload["investigation_id"] = new_id
    if event.type == "action_proposed":
        # Give the replayed action a fresh id and register it, so approve/edit/reject work.
        action = Action.model_validate(payload).model_copy(
            update={
                "id": f"action:{uuid.uuid4().hex[:12]}",
                "investigation_id": new_id,
                "status": "proposed",
                "blocked_reason": None,
            }
        )
        actions.register(action)
        payload = action.model_dump()
    out.payload = payload
    return out
