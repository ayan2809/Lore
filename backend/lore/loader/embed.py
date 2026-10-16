"""Turn text into vectors.

- Real path: Gemini embeddings (`google.genai`), `embed_dim` numbers per text, batched.
- Fake path (`fake=True`): FAKE, OFFLINE-ONLY vectors made by hashing words. Same text gives the
  same vector, texts that share words get similar vectors, but they carry NO real meaning. They
  exist so the whole pipeline (index, vector search, permissions) can run without an API key.
  Never mix fake and real vectors in one graph: reload with --reset when you switch.
"""

from __future__ import annotations

import hashlib
import math
import re
import time

from lore.config import get_settings

BATCH_SIZE = 50  # texts per Gemini request (the API accepts up to 100)


def _normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def fake_embedding(text: str, dim: int) -> list[float]:
    """FAKE embedding: hash each word into 3 vector slots (+1 or -1), then scale to length 1."""
    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()) or [text]:
        digest = hashlib.sha256(word.encode()).digest()
        for k in range(3):
            slot = int.from_bytes(digest[4 * k : 4 * k + 4], "big") % dim
            vec[slot] += 1.0 if digest[12 + k] & 1 else -1.0
    if not any(vec):  # words cancelled out (very rare): fall back to one slot from the whole text
        vec[int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big") % dim] = 1.0
    return _normalise(vec)


def embed_texts(
    texts: list[str], fake: bool = False, task: str = "RETRIEVAL_DOCUMENT"
) -> list[list[float]]:
    """One unit-length vector per text. Use task="RETRIEVAL_QUERY" for search questions."""
    settings = get_settings()
    if fake:
        return [fake_embedding(t, settings.embed_dim) for t in texts]
    if not settings.gemini_api_key:
        raise RuntimeError("No Gemini key: set LORE_GEMINI_API_KEY or use fake embeddings.")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    config = types.EmbedContentConfig(task_type=task, output_dimensionality=settings.embed_dim)
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        for attempt in range(3):  # a few retries for rate limits
            try:
                response = client.models.embed_content(
                    model=settings.model_embed, contents=batch, config=config
                )
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
        # Gemini does not scale shortened vectors to length 1, so do it here
        out.extend(_normalise(list(e.values)) for e in response.embeddings)
    return out
