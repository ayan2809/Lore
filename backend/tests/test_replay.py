import json
import time

from lore import actions, replay
from lore.config import Settings
from lore.models import StepEvent


def settings_for(tmp_path):
    return Settings(_env_file=None, replay_dir=str(tmp_path))


def make_events(inv="inv:orig"):
    def ev(type_, seq, ts, payload):
        return StepEvent(type=type_, investigation_id=inv, seq=seq, ts=ts, payload=payload)

    return [
        ev("investigation_started", 0, 100.0, {"alert_id": "A-3001", "replay": False}),
        ev("action_proposed", 1, 100.2, {
            "id": "action:orig", "investigation_id": inv, "kind": "slack_post",
            "target": "#incidents", "text": "hi", "cited_ids": ["pr:482"], "status": "proposed"}),
        ev("done", 2, 100.4, {"investigation_id": inv, "steps": 2, "replay": False}),
    ]


async def test_recorder_writes_jsonl_and_forwards(tmp_path):
    seen = []

    async def emit(event):
        seen.append(event)

    recorder = replay.Recorder("story_a_arjun", emit, settings_for(tmp_path))
    for event in make_events():
        await recorder(event)
    lines = (tmp_path / "story_a_arjun.jsonl").read_text().splitlines()
    assert len(lines) == 3 and len(seen) == 3
    assert json.loads(lines[0])["type"] == "investigation_started"


async def test_play_rewrites_id_marks_replay_and_registers_action(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(e.model_dump_json() for e in make_events()) + "\n")
    out = []

    async def emit(event):
        out.append(event)

    new_id = await replay.play(path, emit, speed=1000, investigation_id="inv:new")
    assert new_id == "inv:new"
    assert [e.investigation_id for e in out] == ["inv:new"] * 3
    assert out[0].payload["replay"] is True and out[2].payload["replay"] is True
    assert out[2].payload["investigation_id"] == "inv:new"
    action_id = out[1].payload["id"]
    assert action_id != "action:orig"
    assert actions.get(action_id).investigation_id == "inv:new"
    assert out[0].ts > 1_000_000  # timestamps are rewritten to "now"


async def test_play_keeps_relative_timing_scaled_by_speed(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(e.model_dump_json() for e in make_events()) + "\n")
    stamps = []

    async def emit(event):
        stamps.append(time.monotonic())

    await replay.play(path, emit, speed=1.0)  # gaps are 0.2s + 0.2s
    assert 0.35 <= stamps[-1] - stamps[0] <= 1.0
    stamps.clear()
    await replay.play(path, emit, speed=100.0)
    assert stamps[-1] - stamps[0] < 0.2


def test_both_file_formats_load_and_list(tmp_path):
    events = [e.model_dump() for e in make_events()]
    (tmp_path / "a.replay.json").write_text(json.dumps(events))
    (tmp_path / "b.replay.json").write_text(json.dumps({"note": "x", "events": events}))
    (tmp_path / "c.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    for name in ["a.replay.json", "b.replay.json", "c.jsonl"]:
        assert len(replay.load_events(tmp_path / name)) == 3
    assert replay.list_replays(settings_for(tmp_path)) == ["a", "b", "c"]


def test_find_replay_by_alert_and_persona(tmp_path):
    s = settings_for(tmp_path)
    (tmp_path / "story_a_dana.jsonl").write_text("")
    assert replay.find_replay("A-3001", "dana", s).name == "story_a_dana.jsonl"
    assert replay.find_replay("alert:A-3001", "dana", s).name == "story_a_dana.jsonl"
    assert replay.find_replay("A-3001", "sam", s) is None
    assert replay.find_replay("A-9999", "dana", s) is None


def test_committed_sample_replay_is_valid_and_found_for_arjun():
    path = replay.find_replay("A-3001", "arjun")
    assert path is not None and path.name == "sample_story_a.replay.json"
    events = replay.load_events(path)
    types = [e.type for e in events]
    assert types[0] == "investigation_started" and types[-1] == "done"
    assert "report" in types and "action_proposed" in types
    assert [e.seq for e in events] == list(range(len(events)))
