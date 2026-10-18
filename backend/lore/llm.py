"""The only module that talks to Gemini (plan sections 8, 11, 17).

- `LLM` is the small interface the agents and `ask` use: `generate()` and `embed()`.
- `GeminiLLM` calls the google-genai SDK with a timeout and retries with exponential backoff
  on rate limits (429) and server errors (5xx).
- `FakeLLM` replays a scripted list of responses and makes deterministic fake embeddings. Tests
  and the offline demo use it. It is never chosen automatically.

Conversation history is a list of `google.genai.types.Content`. We keep the model's own content
object in the history (not a copy of its text) because Gemini 3 attaches "thought signatures" to
function calls and expects them back on the next turn.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from lore.config import Settings
from lore.observability import estimate_cost, log_event
from lore.tools import ToolSpec

EmbedTask = Literal["query", "document"]


@dataclass
class LLMResponse:
    """One model reply, reduced to what the agent loop needs."""

    text: str = ""
    function_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    parsed: Any = None  # a Pydantic object when a response_schema was given and the JSON was valid
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    content: types.Content | None = None  # the model's own turn, appended to history as-is

    @property
    def cost_usd(self) -> float:
        return estimate_cost(self.model, self.tokens_in, self.tokens_out)


class LLM(Protocol):
    async def generate(
        self,
        model: str,
        system: str,
        contents: list[types.Content],
        tools: list[types.FunctionDeclaration] | None = None,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse: ...

    async def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]: ...


# ------------------------------------------------------------------ building history messages


def user_text(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part.from_text(text=text)])


def tool_responses(results: list[tuple[str, dict[str, Any]]]) -> types.Content:
    """Function results go back to Gemini as one user turn with one part per call, in order."""
    parts = [types.Part.from_function_response(name=n, response=r) for n, r in results]
    return types.Content(role="user", parts=parts)


# ------------------------------------------------------------------ tool declarations


def tool_declarations(specs: list[ToolSpec]) -> list[types.FunctionDeclaration]:
    """Turn each tool's Pydantic args model into a Gemini function declaration."""
    decls = []
    for spec in specs:
        schema = _clean_schema(spec.args_model.model_json_schema())
        # Rule 3 of PROJECT_CONTEXT: the model must never be able to choose the viewer.
        assert "viewer" not in schema.get("properties", {}), f"{spec.name} exposes viewer"
        decls.append(
            types.FunctionDeclaration(
                name=spec.name, description=spec.description, parameters_json_schema=schema
            )
        )
    return decls


def _clean_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline `$defs` references and drop `title` keys: Gemini does not need them."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:  # "#/$defs/Name"
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in ("title", "$defs")}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


# ------------------------------------------------------------------ the real client


class GeminiLLM:
    """google-genai wrapper with a timeout and retry/backoff (plan section 11)."""

    RETRY_CODES = {429, 500, 502, 503, 504}

    def __init__(self, settings: Settings, timeout_s: float = 60.0, attempts: int = 3):
        self.settings = settings
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.timeout_s = timeout_s
        self.attempts = attempts

    async def generate(self, model, system, contents, tools=None, response_schema=None):
        config = types.GenerateContentConfig(
            system_instruction=system,
            # We run the tool loop ourselves (agents/base.py), so the SDK must not.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if tools:
            config.tools = [types.Tool(function_declarations=tools)]
        if response_schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = response_schema

        resp = await self._with_retry(
            lambda: self.client.aio.models.generate_content(
                model=model, contents=contents, config=config
            )
        )
        usage = resp.usage_metadata
        out = LLMResponse(
            text=_safe_text(resp),
            function_calls=[(fc.name, dict(fc.args or {})) for fc in (resp.function_calls or [])],
            parsed=_parse(resp, response_schema),
            tokens_in=(usage.prompt_token_count or 0) if usage else 0,
            tokens_out=(usage.candidates_token_count or 0) if usage else 0,
            model=model,
            content=resp.candidates[0].content if resp.candidates else None,
        )
        log_event(
            event="llm_call",
            model=model,
            tokens_in=out.tokens_in,
            tokens_out=out.tokens_out,
            cost_usd=round(out.cost_usd, 6),
            function_calls=[name for name, _ in out.function_calls],
        )
        return out

    async def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        if self.settings.fake_embeddings:  # graph was loaded with --fake-embeddings
            return [fake_embedding(t, self.settings.embed_dim) for t in texts]
        task_type = "RETRIEVAL_QUERY" if task == "query" else "RETRIEVAL_DOCUMENT"
        config = types.EmbedContentConfig(
            output_dimensionality=self.settings.embed_dim, task_type=task_type
        )
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 100):  # the API takes at most 100 texts per call
            batch = texts[start : start + 100]
            # One Content per text: gemini-embedding-2 merges a plain list of strings into a
            # single embedding (FIX_LOG F-02).
            contents = [types.Content(parts=[types.Part.from_text(text=t)]) for t in batch]
            resp = await self._with_retry(
                lambda c=contents: self.client.aio.models.embed_content(
                    model=self.settings.model_embed, contents=c, config=config
                )
            )
            if len(resp.embeddings) != len(batch):
                raise RuntimeError(f"asked for {len(batch)} embeddings, got {len(resp.embeddings)}")
            vectors.extend(list(e.values) for e in resp.embeddings)
        return vectors

    async def _with_retry(self, make_call: Callable[[], Any]) -> Any:
        """Run `make_call()` with a timeout; on 429/5xx/timeout wait 1s, 2s, 4s... and retry."""
        for attempt in range(self.attempts):
            try:
                return await asyncio.wait_for(make_call(), timeout=self.timeout_s)
            except (errors.APIError, TimeoutError) as exc:
                code = getattr(exc, "code", None)
                retryable = isinstance(exc, TimeoutError) or code in self.RETRY_CODES
                if not retryable or attempt == self.attempts - 1:
                    raise
                wait = 2**attempt
                log_event(event="llm_retry", attempt=attempt + 1, code=code, wait_s=wait)
                await asyncio.sleep(wait)


def _safe_text(resp: Any) -> str:
    """Join the text parts ourselves: `resp.text` warns on every reply that also holds a
    function call, which flooded the logs during live runs."""
    try:
        parts = resp.candidates[0].content.parts or []
    except (AttributeError, IndexError, TypeError):
        return ""
    texts = [p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)]
    return "".join(texts)


def _parse(resp: Any, schema: type[BaseModel] | None) -> Any:
    """Return the structured object, or None if the model's JSON did not match the schema."""
    if schema is None:
        return None
    if isinstance(resp.parsed, schema):
        return resp.parsed
    try:
        return schema.model_validate_json(_safe_text(resp))
    except Exception:
        return None


def get_llm(settings: Settings) -> LLM:
    """The real Gemini client. Fails loudly without a key; FakeLLM must be chosen on purpose."""
    if not settings.gemini_api_key:
        raise RuntimeError(
            "LORE_GEMINI_API_KEY is not set. Set it, or use replay mode (LORE_FORCE_REPLAY=1)."
        )
    return GeminiLLM(settings)


# ------------------------------------------------------------------ the fake client

Script = LLMResponse | Callable[..., LLMResponse]


class FakeLLM:
    """Plays back scripted responses in order. Records every request in `self.calls`.

    A script item is either an `LLMResponse` or a function `(model, system, contents, tools,
    response_schema) -> LLMResponse` for replies that depend on the request. When the script
    runs out, `default` is used (or an error is raised if there is none).
    """

    def __init__(self, script: list[Script] | None = None, default: Script | None = None, dim=768):
        self.script = list(script or [])
        self.default = default
        self.dim = dim
        self.calls: list[dict[str, Any]] = []

    async def generate(self, model, system, contents, tools=None, response_schema=None):
        self.calls.append(
            dict(
                model=model,
                system=system,
                contents=list(contents),
                tools=tools,
                response_schema=response_schema,
            )
        )
        item = self.script.pop(0) if self.script else self.default
        if item is None:
            raise RuntimeError("FakeLLM script exhausted")
        resp = item(model, system, contents, tools, response_schema) if callable(item) else item
        if response_schema is not None and isinstance(resp.parsed, dict):
            resp.parsed = response_schema.model_validate(resp.parsed)
        resp.model = resp.model or model
        if resp.content is None:
            resp.content = _fake_content(resp)
        return resp

    async def embed(self, texts: list[str], task: EmbedTask) -> list[list[float]]:
        return [fake_embedding(t, self.dim) for t in texts]

    # Small helpers so tests read like a conversation.
    @staticmethod
    def call(tool: str, /, **args: Any) -> LLMResponse:
        return LLMResponse(function_calls=[(tool, args)], tokens_in=100, tokens_out=20)

    @staticmethod
    def answer(text: str) -> LLMResponse:
        return LLMResponse(text=text, tokens_in=100, tokens_out=40)

    @staticmethod
    def structured(data: dict[str, Any]) -> LLMResponse:
        return LLMResponse(parsed=data, tokens_in=200, tokens_out=80)


def _fake_content(resp: LLMResponse) -> types.Content:
    parts = [types.Part.from_function_call(name=n, args=a) for n, a in resp.function_calls]
    if resp.text or not parts:
        parts.append(types.Part.from_text(text=resp.text))
    return types.Content(role="model", parts=parts)


def fake_embedding(text: str, dim: int = 768) -> list[float]:
    """The loader's fake vectors, so a graph loaded with --fake-embeddings matches fake queries.
    One function for both sides: mixing two fake schemes would make vector search meaningless."""
    from lore.loader.embed import fake_embedding as loader_fake

    return loader_fake(text, dim)
