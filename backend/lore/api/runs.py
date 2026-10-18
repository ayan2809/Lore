"""In-process registry of investigation runs and their live event streams.

One `Run` per investigation: the full event history, the final report/summary, and one queue per
connected SSE client. A client that connects late first receives the history, then live events.
Everything is in memory: a server restart forgets runs (the graph keeps the Investigation node).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from lore import actions, replay
from lore.config import Settings
from lore.models import Action, Report, RunSummary, StepEvent, Viewer
from lore.observability import log_event

RUN_TIMEOUT_S = 300
MAX_RUNS_KEPT = 200


class Run:
    def __init__(self, viewer_id: str, alert_id: str, mode: str, replay_mode: bool):
        self.id = f"inv:{uuid.uuid4().hex[:10]}"
        self.viewer_id = viewer_id
        self.alert_id = alert_id
        self.mode = mode
        self.replay = replay_mode
        self.events: list[StepEvent] = []
        self.report: Report | None = None
        self.summary: RunSummary | None = None
        self.finished = False
        self.task: asyncio.Task | None = None
        self._subscribers: list[asyncio.Queue[StepEvent | None]] = []

    # -- producing events ------------------------------------------------------------------

    async def emit(self, event: StepEvent) -> None:
        """The `emit` callable handed to the supervisor (and to replay.play)."""
        if event.investigation_id != self.id:
            # Every producer is handed self.id; this only guards one that ignores it.
            event = event.model_copy(update={"investigation_id": self.id})
        if event.type == "report":
            self.report = Report.model_validate(event.payload)
        elif event.type == "done":
            event.payload["investigation_id"] = self.id
            self.summary = RunSummary.model_validate(event.payload)
        elif event.type == "action_proposed":
            self._adopt_action(event.payload.get("id"))
        self.events.append(event)
        for queue in self._subscribers:
            queue.put_nowait(event)

    async def push(self, type_: str, payload: dict[str, Any], agent: str | None = None) -> None:
        """Emit an event created by the API itself (errors, fallback report/done)."""
        await self.emit(
            StepEvent(
                type=type_,
                investigation_id=self.id,
                seq=len(self.events),
                ts=time.time(),
                agent=agent,
                payload=payload,
            )
        )

    def _adopt_action(self, action_id: str | None) -> None:
        try:
            actions.get(action_id or "").investigation_id = self.id
        except actions.ActionNotFound:
            pass

    def finish(self) -> None:
        self.finished = True
        for queue in self._subscribers:
            queue.put_nowait(None)
        self._subscribers.clear()

    # -- consuming events ------------------------------------------------------------------

    async def stream(self) -> AsyncIterator[StepEvent]:
        """History first, then live events, ending after the last one."""
        queue: asyncio.Queue[StepEvent | None] = asyncio.Queue()
        for event in self.events:
            queue.put_nowait(event)
        if self.finished:
            queue.put_nowait(None)
        else:
            self._subscribers.append(queue)
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def actions(self) -> list[Action]:
        return actions.for_investigation(self.id)


class RunRegistry:
    def __init__(self, supervisor=None, replay_speed: float = 1.0):
        self.runs: dict[str, Run] = {}
        self.supervisor = supervisor  # tests inject a fake; default is the real supervisor
        self.replay_speed = replay_speed  # tests use a large value so replays finish at once

    def get(self, run_id: str) -> Run | None:
        return self.runs.get(run_id)

    def create(self, viewer_id: str, alert_id: str, mode: str, replay_mode: bool) -> Run:
        run = Run(viewer_id, alert_id, mode, replay_mode)
        self.runs[run.id] = run
        for old in [r for r in self.runs.values() if r.finished][:-MAX_RUNS_KEPT]:
            del self.runs[old.id]  # forget the oldest finished runs
        return run

    def start_live(self, run: Run, viewer: Viewer, llm, graph, settings: Settings) -> None:
        run.task = asyncio.create_task(self._run_live(run, viewer, llm, graph, settings))

    def start_replay(self, run: Run, path: Path | None) -> None:
        run.task = asyncio.create_task(self._run_replay(run, path, self.replay_speed))

    async def _run_live(self, run: Run, viewer: Viewer, llm, graph, settings: Settings) -> None:
        supervisor = self.supervisor or _real_supervisor
        try:
            report, summary = await asyncio.wait_for(
                supervisor(
                    run.alert_id,
                    viewer,
                    mode=run.mode,
                    llm=llm,
                    graph=graph,
                    emit=run.emit,
                    settings=settings,
                    investigation_id=run.id,
                ),
                RUN_TIMEOUT_S,
            )
            if run.summary is None:  # the supervisor did not emit its own final events
                if run.report is None:
                    await run.push("report", report.model_dump())
                await run.push("done", summary.model_dump())
        except Exception as exc:
            await self._fail(run, exc)
        finally:
            run.finish()

    async def _run_replay(self, run: Run, path: Path | None, speed: float) -> None:
        try:
            if path is None:
                await run.push(
                    "error",
                    {
                        "message": f"No recorded {'Graph OFF ' if run.mode == 'vector' else ''}"
                        f"run for alert {run.alert_id} and this persona.",
                        "recoverable": False,
                    },
                )
            else:
                await replay.play(path, run.emit, speed, investigation_id=run.id)
        except Exception as exc:
            await self._fail(run, exc)
        finally:
            if run.summary is None:  # always end the stream with a `done`
                empty = RunSummary(investigation_id=run.id, replay=True)
                await run.push("done", empty.model_dump())
            run.finish()

    async def _fail(self, run: Run, exc: Exception) -> None:
        log_event(event="run_failed", investigation_id=run.id, error=repr(exc))
        await run.push(
            "error",
            {"message": f"Investigation failed ({type(exc).__name__}).", "recoverable": False},
        )
        if run.summary is None:
            empty = RunSummary(investigation_id=run.id, replay=run.replay)
            await run.push("done", empty.model_dump())


async def _real_supervisor(*args, **kwargs):
    from lore.agents import supervisor  # imported late: this module loads without Gemini set up

    return await supervisor.run_investigation(*args, **kwargs)


_registry = RunRegistry()


def get_registry() -> RunRegistry:
    """FastAPI dependency; tests override it with a registry holding a fake supervisor."""
    return _registry


def sse_message(event: StepEvent) -> dict[str, str]:
    """Shape sse-starlette expects: `event:` is the StepEvent type, `data:` the JSON."""
    return {
        "event": event.type,
        "data": json.dumps(event.model_dump(), default=str),
        "id": str(event.seq),
    }
