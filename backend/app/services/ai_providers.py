"""Concrete LLM provider implementations for the AI report pipeline.

This module owns the *concrete* half of the AI report pipeline. The
abstract orchestration lives in :mod:`app.services.ai_analyzer`; here
we only fill in the ``_call_llm`` hook for each supported provider and
wire them together through the :func:`make_analyzer` factory.

The supported provider tags are locked down to the literal set
``{"openai", "deepseek", "gemini"}`` by:

* the ``ai_reports.provider`` CHECK constraint (see
  :mod:`app.models.ai_report` -- ``AI_PROVIDERS``);
* the request-time validation inside ``POST /api/tasks/{id}/ai-report``;
* and the factory below, which rejects any other value with
  :class:`ValueError` so a typo can never reach the database layer.

Read-only invariant
-------------------

All three providers inherit :class:`AIAnalyzer` which funnels reads
through :meth:`DataStore.load_for_ai` and writes through
:meth:`DataStore.save_ai_report`. Concrete providers therefore have
**no** direct database access; they only translate a prompt string
into a response string, which keeps requirement 15.x trivially
satisfied no matter how a provider is implemented.

Error handling contract
-----------------------

Every transport-level failure (timeout, network error, authentication
error, rate-limit error, content filter, empty response) is converted
into :class:`LLMError`. The API layer maps this single exception to
``HTTP 502 AI_FAILED`` (requirement 14.10), so route handlers never
need to know about provider-specific exception hierarchies.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any, ClassVar

from app.core.config import settings
from app.core.logger import logger
from app.services.ai_analyzer import AIAnalyzer, LLMError

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from app.services.data_store import DataStore


# ---------------------------------------------------------------------------
# OpenAI-compatible providers (OpenAI + DeepSeek)
# ---------------------------------------------------------------------------


class _OpenAICompatibleAnalyzer(AIAnalyzer):
    """Base class for any provider speaking the OpenAI chat-completion wire.

    OpenAI and DeepSeek share the same JSON contract -- the only
    differences are the ``base_url`` and the credential -- so we
    centralise the actual call here and let subclasses inject the
    right config. Subclasses MUST override :data:`provider`,
    :meth:`_api_key` and :meth:`_base_url`.
    """

    #: Default value forwarded to the SDK's ``base_url`` when the
    #: environment override is empty. ``None`` lets the SDK pick its
    #: own factory default (api.openai.com for the upstream package).
    _default_base_url: ClassVar[str | None] = None

    def _api_key(self) -> str:
        raise NotImplementedError

    def _base_url(self) -> str | None:
        raise NotImplementedError

    def _provider_label(self) -> str:
        return self.provider

    async def _call_llm(self, prompt: str) -> str:
        # Lazy import so a missing ``openai`` install does not break
        # module import for users who never invoke an analyzer.
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - environment
            raise LLMError(
                f"{self._provider_label()} SDK missing: install `openai` "
                f"to enable this provider"
            ) from exc

        api_key = self._api_key()
        if not api_key.strip():
            raise LLMError(
                f"{self._provider_label()}: missing API key; set the "
                f"matching ``*_API_KEY`` environment variable"
            )

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self._base_url(),
            timeout=self.timeout_s,
        )

        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                ),
                timeout=self.timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise LLMError(
                f"{self._provider_label()}: LLM call timed out after "
                f"{self.timeout_s}s"
            ) from exc
        except Exception as exc:  # noqa: BLE001 -- translate to LLMError
            # ``openai.APIError`` and friends all inherit ``Exception``;
            # we collapse them onto a single failure mode by design.
            raise LLMError(
                f"{self._provider_label()}: LLM call failed: {exc}"
            ) from exc
        finally:
            # ``AsyncOpenAI`` keeps an underlying ``httpx.AsyncClient``
            # open until ``.close()`` is called. Closing it here avoids
            # a ResourceWarning when the analyzer is short-lived (which
            # is always the case under ``BackgroundTasks``).
            try:
                await client.close()
            except Exception:  # pragma: no cover - defensive
                pass

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise LLMError(
                f"{self._provider_label()}: unexpected response shape"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                f"{self._provider_label()}: empty response from model "
                f"{self.model!r}"
            )

        return content


class OpenAIAnalyzer(_OpenAICompatibleAnalyzer):
    """LLM provider backed by the official OpenAI API."""

    provider: ClassVar[str] = "openai"

    def _api_key(self) -> str:
        return settings.OPENAI_API_KEY

    def _base_url(self) -> str | None:
        base = settings.OPENAI_BASE_URL.strip()
        return base or None


class DeepSeekAnalyzer(_OpenAICompatibleAnalyzer):
    """LLM provider backed by the DeepSeek API (OpenAI-compatible)."""

    provider: ClassVar[str] = "deepseek"

    def _api_key(self) -> str:
        return settings.DEEPSEEK_API_KEY

    def _base_url(self) -> str | None:
        base = (settings.DEEPSEEK_BASE_URL or "https://api.deepseek.com").strip()
        return base or "https://api.deepseek.com"


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------


class GeminiAnalyzer(AIAnalyzer):
    """LLM provider backed by Google Gemini via the official SDK.

    ``google-generativeai`` is an optional dependency declared under
    the ``gemini`` extra in ``pyproject.toml``; we import it lazily so
    the rest of the system stays usable without the package installed.
    """

    provider: ClassVar[str] = "gemini"

    async def _call_llm(self, prompt: str) -> str:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment
            raise LLMError(
                "gemini SDK missing: install `google-generativeai` to "
                "enable this provider"
            ) from exc

        api_key = settings.GEMINI_API_KEY
        if not api_key.strip():
            raise LLMError(
                "gemini: missing API key; set GEMINI_API_KEY in your env"
            )

        # ``genai.configure`` is process-global. That's fine for an
        # MVP since we only ever call one provider at a time inside a
        # background task; if multi-tenant key rotation becomes
        # important the SDK exposes a ``client_options`` route.
        genai.configure(api_key=api_key)

        def _sync_call() -> str:
            # The SDK is synchronous, so we marshal it through a
            # thread to keep the event loop responsive.
            model_obj = genai.GenerativeModel(self.model)
            resp = model_obj.generate_content(prompt)
            # The SDK exposes ``.text`` on the response for the common
            # single-candidate case; fall back to parsing candidates
            # if the SDK returns nothing usable up there.
            text = getattr(resp, "text", None)
            if isinstance(text, str) and text.strip():
                return text
            candidates = getattr(resp, "candidates", None) or []
            for cand in candidates:
                content = getattr(cand, "content", None)
                if content is None:
                    continue
                parts = getattr(content, "parts", None) or []
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if isinstance(part_text, str) and part_text.strip():
                        return part_text
            raise LLMError(
                f"gemini: empty response from model {self.model!r}"
            )

        try:
            content = await asyncio.wait_for(
                asyncio.to_thread(_sync_call),
                timeout=self.timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise LLMError(
                f"gemini: LLM call timed out after {self.timeout_s}s"
            ) from exc
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 -- translate to LLMError
            raise LLMError(f"gemini: LLM call failed: {exc}") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMError(
                f"gemini: empty response from model {self.model!r}"
            )
        return content


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


#: Mapping of provider tags to their concrete analyzer classes. Kept
#: as a module-level constant so :func:`make_analyzer` does not have
#: to rebuild it on every call, and so test code can introspect the
#: registry without poking at the function body.
_PROVIDER_REGISTRY: dict[str, type[AIAnalyzer]] = {
    "openai": OpenAIAnalyzer,
    "deepseek": DeepSeekAnalyzer,
    "gemini": GeminiAnalyzer,
}


def supported_providers() -> tuple[str, ...]:
    """Return the supported provider tags in registration order.

    Useful both for API validation (``POST /api/tasks/{id}/ai-report``
    rejects any value not in this tuple with 422 ``INVALID_PROVIDER``)
    and for test parametrisation.
    """
    return tuple(_PROVIDER_REGISTRY.keys())


def make_analyzer(
    provider: str | None,
    model: str,
    store: "DataStore",
) -> AIAnalyzer:
    """Construct an :class:`AIAnalyzer` for ``provider`` / ``model``.

    Parameters
    ----------
    provider:
        Either ``"openai"``, ``"deepseek"``, ``"gemini"`` (case
        insensitive), or ``None`` to fall back to the
        ``AI_PROVIDER`` environment variable / settings default.
    model:
        Model identifier passed verbatim to the provider SDK. Validated
        upstream by the API layer (length ``[1, 100]``).
    store:
        :class:`DataStore` instance the analyzer should funnel its
        reads / writes through.

    Returns
    -------
    AIAnalyzer
        Concrete analyzer ready to ``await analyzer.analyze(task_id)``.

    Raises
    ------
    ValueError
        If ``provider`` is not in ``{"openai", "deepseek", "gemini"}``
        after case normalisation.
    """
    raw = provider if provider is not None else os.getenv(
        "AI_PROVIDER", settings.AI_PROVIDER
    )
    tag = (raw or "openai").strip().lower()
    cls = _PROVIDER_REGISTRY.get(tag)
    if cls is None:
        raise ValueError(
            f"unsupported provider {raw!r}; must be one of "
            f"{sorted(_PROVIDER_REGISTRY.keys())}"
        )

    logger.info(
        "ai_analyzer_make",
        extra={
            "event": "ai_analyzer_make",
            "provider": tag,
            "model": model,
        },
    )
    return cls(store=store, model=model)


__all__ = [
    "DeepSeekAnalyzer",
    "GeminiAnalyzer",
    "OpenAIAnalyzer",
    "make_analyzer",
    "supported_providers",
]
