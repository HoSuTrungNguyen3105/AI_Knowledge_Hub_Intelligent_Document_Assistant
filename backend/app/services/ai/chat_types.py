from dataclasses import dataclass


def token_count(value: object) -> int | None:
    """Accept only a non-negative int from untrusted upstream usage metadata."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ChatRequest:
    model: str
    turns: tuple[ChatTurn, ...]
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class ChatEvent:
    """Sanitized generation event. kind is "delta" (text) or "usage" (token counts)."""

    kind: str
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None