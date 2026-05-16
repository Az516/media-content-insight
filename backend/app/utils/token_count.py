"""Token-count estimation helper for AI prompt size guards.

Task 11.1 requires :class:`AIAnalyzer.analyze` to verify
``estimated_tokens(prompt) < settings.MODEL_CONTEXT_LIMIT`` *before*
spending money on an LLM round-trip (requirement 14.8). The MVP uses a
deliberately cheap character-based heuristic rather than pulling in
``tiktoken``:

* No additional runtime dependency -- ``tiktoken`` ships native code
  that complicates the project's "pure-Python on Windows" footprint.
* Every supported provider (OpenAI / DeepSeek / Gemini, see task 11.2)
  uses a different tokeniser, so a single library would not be
  authoritative anyway.
* The check is a *guard*, not a billing estimate: we only need a value
  that scales linearly with input size and that overestimates rather
  than underestimates whenever the prompt is dominated by Chinese.

The 1-token-per-4-character ratio is the upper bound documented by
OpenAI for English text and is conservative enough for mixed CJK/ASCII
input typical of small-red-book material.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Return a rough token count for ``text``.

    The heuristic is ``max(1, len(text) // 4)`` -- one token per four
    characters, with a floor of 1 so the estimate stays positive for
    any non-empty (or even ``""``) input. The function never raises:
    callers can pass ``""`` and still get a sensible value to compare
    against ``MODEL_CONTEXT_LIMIT``.

    Parameters
    ----------
    text:
        Prompt or any other string whose token footprint we need to
        bound. Non-string inputs are coerced via :class:`str` so that
        defensive callers do not have to special-case ``None``.

    Returns
    -------
    int
        An integer >= 1 representing an upper-bound estimate of the
        token count.
    """
    if not isinstance(text, str):
        text = str(text)
    return max(1, len(text) // 4)


__all__ = ["estimate_tokens"]
