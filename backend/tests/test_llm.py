"""lore.llm without network: declarations, FakeLLM, retry/backoff, get_llm."""

from __future__ import annotations

import math
from typing import Literal

import pytest
from google.genai import errors
from pydantic import BaseModel, Field

from lore import llm as llm_mod
from lore.config import Settings
from lore.llm import FakeLLM, GeminiLLM, fake_embedding, get_llm, tool_declarations, user_text
from lore.tools import ToolArgs, ToolSpec


class Window(BaseModel):
    hours: int = 24


class SampleArgs(ToolArgs):
    service: str = Field(description="A service")
    kind: Literal["a", "b"] = "a"
    window: Window = Field(default_factory=Window)


def _spec(args_model) -> ToolSpec:
    return ToolSpec("sample", "A sample tool.", args_model, fn=lambda ctx, a: None)


def test_tool_declarations_inline_refs_and_drop_titles():
    [decl] = tool_declarations([_spec(SampleArgs)])
    schema = decl.parameters_json_schema
    text = str(schema)
    assert decl.name == "sample"
    assert "title" not in text and "$defs" not in text and "$ref" not in text
    assert set(schema["properties"]) == {"reason", "service", "kind", "window"}
    assert "reason" in schema["required"]
    assert schema["properties"]["window"]["properties"]["hours"]["type"] == "integer"


def test_tool_declarations_refuse_a_viewer_argument():
    class Leaky(ToolArgs):
        viewer: str

    with pytest.raises(AssertionError):
        tool_declarations([_spec(Leaky)])


async def test_fake_llm_plays_script_in_order_and_parses_structured():
    class Out(BaseModel):
        answer: str

    fake = FakeLLM(
        [
            FakeLLM.call("find_entity", reason="r", name="pricing"),
            FakeLLM.structured({"answer": "42"}),
        ]
    )
    first = await fake.generate("m", "sys", [user_text("hi")])
    assert first.function_calls == [("find_entity", {"reason": "r", "name": "pricing"})]
    assert first.content.role == "model"  # history-ready
    second = await fake.generate("m", "sys", [user_text("hi")], response_schema=Out)
    assert isinstance(second.parsed, Out) and second.parsed.answer == "42"
    assert len(fake.calls) == 2
    with pytest.raises(RuntimeError, match="exhausted"):
        await fake.generate("m", "sys", [])


async def test_fake_embeddings_are_deterministic_normalised_and_meaningful():
    fake = FakeLLM(dim=64)
    a, b, c = await fake.embed(
        ["pricing cache ttl", "pricing cache ttl lowered", "weather"], "query"
    )
    assert a == fake_embedding("pricing cache ttl", 64)
    assert math.isclose(sum(v * v for v in a), 1.0, rel_tol=1e-9)

    def cos(x, y):
        return sum(i * j for i, j in zip(x, y, strict=True))

    assert cos(a, b) > cos(a, c)


async def test_gemini_retries_on_429_then_succeeds(monkeypatch):
    sleeps: list[float] = []

    async def no_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr(llm_mod.asyncio, "sleep", no_sleep)
    g = GeminiLLM(Settings(gemini_api_key="test-key"))
    attempts = {"n": 0}

    async def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE"}})
        return "ok"

    assert await g._with_retry(flaky) == "ok"
    assert attempts["n"] == 3
    assert sleeps == [1, 2]  # exponential backoff


async def test_gemini_does_not_retry_a_bad_request(monkeypatch):
    g = GeminiLLM(Settings(gemini_api_key="test-key"))
    attempts = {"n": 0}

    async def bad():
        attempts["n"] += 1
        raise errors.ClientError(400, {"error": {"message": "bad", "status": "INVALID"}})

    with pytest.raises(errors.ClientError):
        await g._with_retry(bad)
    assert attempts["n"] == 1


def test_get_llm_needs_a_key():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        get_llm(Settings(gemini_api_key=None))
    assert isinstance(get_llm(Settings(gemini_api_key="k")), GeminiLLM)
