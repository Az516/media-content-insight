"""Application configuration loaded from environment variables.

This module centralises all runtime configuration of the backend. It
deliberately enforces a small number of compliance invariants at load time:

* ``HOST`` MUST be ``127.0.0.1``. The system is only ever expected to run on
  the developer's local machine; binding to any non-loopback address would
  violate requirement 19.11 / 20.1.
* ``MEDIA_CRAWLER_ROOT`` is resolved relative to the repository root when it
  is not given as an absolute path, so that relative defaults such as
  ``third_party/MediaCrawler`` work regardless of the current working
  directory of the process.
* ``MEDIA_CRAWLER_PYTHON`` falls back to the current Python interpreter
  (``sys.executable``) when not explicitly configured.
* ``JSON_ARCHIVE_DIR`` is resolved to an absolute :class:`pathlib.Path` and
  defaults to ``<repo_root>/data/json`` (requirement 20.2).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Repository root = backend/app/core/config.py -> parents[3]
#   parents[0] = backend/app/core
#   parents[1] = backend/app
#   parents[2] = backend
#   parents[3] = <repo root>
REPO_ROOT: Path = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration values.

    Values are loaded from environment variables and from a ``.env`` file
    located in the ``backend/`` directory when present. Environment variables
    always take precedence over values written to ``.env``.
    """

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- HTTP listener ----
    # Only the loopback address is allowed by the compliance baseline.
    HOST: str = Field(default="127.0.0.1")
    PORT: int = Field(default=8000, ge=1, le=65535)

    # ---- MediaCrawler integration ----
    MEDIA_CRAWLER_ROOT: Path = Field(default=Path("third_party/MediaCrawler"))
    MEDIA_CRAWLER_PYTHON: str = Field(default="")
    MEDIA_CRAWLER_LOGIN_TYPE: str = Field(default="cookie")
    MEDIA_CRAWLER_COOKIES: str = Field(default="")

    # ---- Crawl behaviour ----
    CRAWL_TIMEOUT_SECONDS: int = Field(default=600, ge=1)
    HOT_COMMENT_TOP_N: int = Field(default=5, ge=1, le=20)
    MOCK_CRAWLER: bool = Field(default=False)

    # ---- AI provider ----
    AI_PROVIDER: str = Field(default="openai")
    LLM_API_TIMEOUT_SECONDS: int = Field(default=120, ge=1)
    MODEL_CONTEXT_LIMIT: int = Field(default=8000, ge=1)
    MOCK_AI_REPORT: bool = Field(default=False)

    # Optional credentials for individual providers; intentionally untyped
    # beyond plain strings so that absent / empty values do not break startup.
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_BASE_URL: str = Field(default="")
    DEEPSEEK_API_KEY: str = Field(default="")
    DEEPSEEK_BASE_URL: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")

    # ---- Local storage ----
    JSON_ARCHIVE_DIR: Path = Field(default=Path("data/json"))

    # ---- Validators ----

    @field_validator("HOST")
    @classmethod
    def _validate_host(cls, value: str) -> str:
        # Compliance: requirement 20.1 hard-codes the listener to the
        # loopback address. Anything else is rejected at load time.
        if value.strip() != "127.0.0.1":
            raise ValueError(
                "HOST must be 127.0.0.1; binding to any other address "
                "violates the compliance baseline (requirement 20.1)."
            )
        return "127.0.0.1"

    @field_validator("AI_PROVIDER")
    @classmethod
    def _normalise_provider(cls, value: str) -> str:
        # The provider string is matched case-insensitively elsewhere; we
        # normalise it here so downstream code can safely compare against
        # lower-case literals.
        return (value or "openai").strip().lower()

    @field_validator("MEDIA_CRAWLER_LOGIN_TYPE")
    @classmethod
    def _normalise_media_crawler_login_type(cls, value: str) -> str:
        login_type = (value or "cookie").strip().lower()
        if login_type not in {"cookie", "qrcode", "phone"}:
            raise ValueError(
                "MEDIA_CRAWLER_LOGIN_TYPE must be one of: cookie, qrcode, phone."
            )
        return login_type

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        # Resolve MEDIA_CRAWLER_ROOT relative to the repository root when a
        # relative path is provided. We keep the value as a Path object so
        # downstream callers can safely use ``/`` / ``.exists()`` etc.
        if not self.MEDIA_CRAWLER_ROOT.is_absolute():
            object.__setattr__(
                self,
                "MEDIA_CRAWLER_ROOT",
                (REPO_ROOT / self.MEDIA_CRAWLER_ROOT).resolve(),
            )

        # Prefer MediaCrawler's own virtualenv when it exists. The backend's
        # Python environment intentionally stays small, while MediaCrawler
        # needs browser/runtime packages such as playwright.
        if not self.MEDIA_CRAWLER_PYTHON.strip():
            if sys.platform == "win32":
                mc_python = self.MEDIA_CRAWLER_ROOT / ".venv" / "Scripts" / "python.exe"
            else:
                mc_python = self.MEDIA_CRAWLER_ROOT / ".venv" / "bin" / "python"
            object.__setattr__(
                self,
                "MEDIA_CRAWLER_PYTHON",
                str(mc_python) if mc_python.exists() else sys.executable,
            )

        # Resolve JSON archive directory relative to repo root unless an
        # absolute path was given. We deliberately do NOT create the
        # directory here to keep configuration loading side-effect free; the
        # DataStore is responsible for ensuring the directory exists.
        if not self.JSON_ARCHIVE_DIR.is_absolute():
            object.__setattr__(
                self,
                "JSON_ARCHIVE_DIR",
                (REPO_ROOT / self.JSON_ARCHIVE_DIR).resolve(),
            )

        return self

    # ---- Convenience helpers ----

    @property
    def repo_root(self) -> Path:
        """Absolute path of the repository root."""
        return REPO_ROOT

    @property
    def cors_allow_origins(self) -> list[str]:
        """Allowed origins for CORS.

        Only loopback origins are returned so that browsers cannot make
        authenticated requests from any non-local origin.
        """
        return [
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]

    @property
    def cors_allow_origin_regex(self) -> str:
        """Allow browser requests from any loopback dev-server port.

        Vite automatically falls forward to 5174, 5175, etc. when the
        default port is occupied. This regex keeps the compliance boundary
        local-only while preventing those legitimate dev ports from failing
        CORS preflight.
        """
        return r"^http://(127\.0\.0\.1|localhost):\d+$"

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a copy of the settings safe to log (no secrets).

        Any attribute whose name ends with ``API_KEY`` is masked.
        """
        masked: dict[str, Any] = {}
        for name, value in self.model_dump().items():
            if (name.endswith("API_KEY") or name.endswith("COOKIES")) and value:
                masked[name] = "***"
            elif isinstance(value, Path):
                masked[name] = str(value)
            else:
                masked[name] = value
        return masked


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    Using a cache means tests can clear it via ``get_settings.cache_clear()``
    when they need to inject different environment variables.
    """
    return Settings()


# Module-level singleton convenient for ``from app.core.config import settings``.
settings: Settings = get_settings()
