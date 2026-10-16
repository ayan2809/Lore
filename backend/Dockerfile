# Lore API image. Build context is backend/ (see docker-compose.yml).
FROM python:3.12-slim

# uv = the Python package manager this project uses. Copy its binary from the official image.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 1) Dependencies first: this layer is cached until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Then our own code (changes often), and install the project itself.
COPY . .
RUN uv sync --frozen --no-dev

# Run as a normal user, not root.
RUN useradd --create-home lore && chown -R lore /app
USER lore

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/health', timeout=4)" || exit 1

CMD ["uvicorn", "lore.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
