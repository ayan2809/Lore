"""Settings, read from environment variables (or backend/.env)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LORE_", extra="ignore")

    # FalkorDB
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_password: str | None = None
    graph_name: str = "org_kettle"
    query_timeout_ms: int = 2000

    # Gemini. Model ids are placeholders: confirm the exact ids in AI Studio (HUMAN_REVIEW R-04).
    gemini_api_key: str | None = None
    model_pro: str = "gemini-3.8-flash"
    model_flash: str = "gemini-3.5-flash-lite"
    model_embed: str = "gemini-embedding-2"
    embed_dim: int = 768
    # Must match how the graph was loaded: true after `load --fake-embeddings` (offline only).
    fake_embeddings: bool = False

    # Outward actions (only used after a human approves)
    slack_webhook_url: str | None = None
    github_token: str | None = None
    github_repo: str | None = None  # "owner/name"

    # Web
    session_secret: str = "dev-only-change-me"
    cors_origins: list[str] = ["http://localhost:5173"]
    rate_limit_per_minute: int = 20
    # True when the site is served over HTTPS (the cookie then gets the Secure flag). Off by
    # default so http://localhost works. On AWS (CloudFront) it is true.
    cookie_secure: bool = False
    # "if_empty": at startup, if the graph has no :Service nodes, load backend/data in a background
    # thread (used on AWS, where the graph starts empty on a new EFS volume). "never": do nothing.
    load_on_start: Literal["never", "if_empty"] = "never"

    # Replay mode: play back a recorded run instead of calling Gemini
    replay_dir: str = "replays"
    force_replay: bool = False

    # Agent tuning
    investigator_confidence_threshold: float = 0.7
    max_agent_steps: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
