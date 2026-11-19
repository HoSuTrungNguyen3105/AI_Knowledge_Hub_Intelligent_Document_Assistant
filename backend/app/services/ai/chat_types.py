from dataclasses import dataclass, field


def token_count(value: object) -> int | None:
    """Accept only a non-negative int from untrusted upstream usage metadata."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


@dataclass(frozen=True)
class ToolSpec:
    """A function the model may call. parameters is a JSON-schema object."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    """A complete tool call requested by the model (arguments already parsed)."""

    id: str
    name: str
    arguments: dict
    # Opaque provider replay metadata stays in the backend, not public traces.
    replay_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" | "assistant" | "tool"
    content: str
    # Tool-calling fields are additive; ordinary chat turns leave them empty.
    # OpenAI uses tool_call_id; Gemini's functionResponse needs tool_name.
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ChatRequest:
    model: str
    turns: tuple[ChatTurn, ...]
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    tools: tuple[ToolSpec, ...] = ()


@dataclass(frozen=True)
class ChatEvent:
    """Sanitized generation event.

    kind is "delta" (text), "usage" (token counts) or "tool_call" (a complete
    function call requested by the model).
    """

    kind: str
    text: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    tool_call: ToolCall | None = None