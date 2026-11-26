"""Provider-reported rate limits (``x-ratelimit-*`` response headers).

Some providers (notably Groq) attach their real remaining quota to
every chat response. There is no usage endpoint to poll, so the chat
HTTP facade hands the response headers here: the newest snapshot per
(provider, model) is kept in-process and later persisted against the
user whose recorded call produced it (see ``app.services.rate_limits``).

Nothing here is estimated or fabricated: a provider that sends no
such headers simply never produces a snapshot.
"""

import time

_HEADER_NAMES = {
    "limit_requests": "x-ratelimit-limit-requests",
    "remaining_requests": "x-ratelimit-remaining-requests",
    "reset_requests": "x-ratelimit-reset-requests",
    "limit_tokens": "x-ratelimit-limit-tokens",
    "remaining_tokens": "x-ratelimit-remaining-tokens",
    "reset_tokens": "x-ratelimit-reset-tokens",
    "limit_requests_day": "x-ratelimit-limit-requests-day",
    "remaining_requests_day": "x-ratelimit-remaining-requests-day",
    "reset_requests_day": "x-ratelimit-reset-requests-day",
    "limit_tokens_day": "x-ratelimit-limit-tokens-day",
    "remaining_tokens_day": "x-ratelimit-remaining-tokens-day",
    "reset_tokens_day": "x-ratelimit-reset-tokens-day",
}

_LATEST: dict[tuple[str, str], tuple[float, dict]] = {}


def _as_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_rate_limit_headers(headers) -> dict | None:
    """Extract the known ``x-ratelimit-*`` fields, or None if absent.

    Limit/remaining values are counts and must parse as integers;
    reset values are provider-specific duration strings and are kept
    verbatim. Unparseable counts are skipped, never guessed.
    """
    if headers is None:
        return None
    snapshot: dict = {}
    for field, header in _HEADER_NAMES.items():
        raw = headers.get(header)
        if raw is None:
            continue
        if field.startswith("reset"):
            snapshot[field] = str(raw)
        else:
            parsed = _as_int(raw)
            if parsed is not None:
                snapshot[field] = parsed
    return snapshot or None


def note_rate_limit(provider: str, model: str | None, headers) -> None:
    """Remember the newest snapshot for (provider, model)."""
    if not provider or not model:
        return
    snapshot = parse_rate_limit_headers(headers)
    if snapshot is None:
        return
    _LATEST[(provider, model)] = (time.time(), snapshot)


def latest_rate_limit(
    provider: str, model: str, *, max_age_seconds: float = 300.0
) -> dict | None:
    """The snapshot captured during the caller's just-finished call.

    The age bound keeps a stale in-process entry from being attributed
    to a much later request for the same provider and model.
    """
    entry = _LATEST.get((provider, model))
    if entry is None:
        return None
    captured, snapshot = entry
    if time.time() - captured > max_age_seconds:
        return None
    return snapshot
