from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import BaseDocument


class User(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    email: str
    name: str
    password_hash: str
    created_at: datetime


class RefreshToken(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    created_at: datetime


class KnowledgeBase(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime


class Document(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    knowledge_base_id: UUID
    original_filename: str
    file_size: int
    mime_type: str
    storage_path: str
    status: str = "queued"
    chunk_count: int = 0
    error_message: str | None = None
    created_at: datetime


class Conversation(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    knowledge_base_id: UUID | None = None
    # Set when the conversation is one pane of a Multi-AI Chat session. Absent
    # (None) for ordinary single-model chats, so existing documents stay valid.
    multi_chat_id: UUID | None = None
    title: str
    provider: str
    model: str
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    created_at: datetime
    updated_at: datetime


class Message(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    conversation_id: UUID
    user_id: UUID
    role: str
    content: str
    status: str = "success"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    created_at: datetime


class AIRequest(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    provider: str
    model: str
    status: str
    conversation_id: UUID | None = None
    message_id: UUID | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    created_at: datetime


class ComparisonRun(BaseModel):
    """One model's answer inside a comparison; embedded, always read with parent."""

    id: UUID
    provider: str
    model: str
    status: str = "pending"
    content: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    estimated_cost: float | None = None


class ComparisonSynthesis(BaseModel):
    provider: str
    model: str
    status: str = "pending"
    content: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    estimated_cost: float | None = None


class Comparison(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    title: str
    prompt: str
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    runs: dict[str, ComparisonRun] = Field(default_factory=dict)
    synthesis: ComparisonSynthesis | None = None
    created_at: datetime
    updated_at: datetime


class SynthesisSource(BaseModel):
    """Which pane answer fed a Multi-AI synthesis; references, not copies."""

    conversation_id: UUID
    message_id: UUID
    provider: str
    model: str


class MultiChatSynthesis(BaseModel):
    id: UUID
    prompt: str
    criteria: list[str] = Field(default_factory=list)
    sources: list[SynthesisSource] = Field(default_factory=list)
    provider: str
    model: str
    status: str = "pending"
    content: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    estimated_cost: float | None = None
    created_at: datetime


class MultiChat(BaseDocument, BaseModel):
    """A Multi-AI Chat session: an ordered group of existing conversations.

    Messages stay in the conversations/messages collections; this document only
    holds pane order, shared defaults for new panes and synthesis results.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    title: str
    conversation_ids: list[UUID] = Field(default_factory=list)
    system_prompt: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    syntheses: list[MultiChatSynthesis] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ActivityLog(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    action: str
    description: str
    created_at: datetime


class AgentToolCall(BaseModel):
    """A tool the model requested inside one agent step; embedded in the trace."""

    id: str
    name: str
    arguments: dict = Field(default_factory=dict)
    status: str = "pending"
    result: dict | None = None
    error_code: str | None = None
    latency_ms: int | None = None


class AgentStep(BaseModel):
    """One model iteration of the bounded agent loop; embedded, read with parent."""

    index: int
    content: str = ""
    tool_calls: list[AgentToolCall] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None


class Agent(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    name: str
    description: str | None = None
    system_prompt: str | None = None
    provider: str
    model: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    # Enabled tool names from the fixed registry; selection lives on the agent so
    # no separate agent_tools collection is needed.
    tools: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AgentExecution(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    agent_id: UUID
    user_id: UUID
    # Snapshot preserves the generation target after the agent is edited.
    provider: str | None = None
    model: str | None = None
    prompt: str
    status: str = "running"
    content: str = ""
    steps: list[AgentStep] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    estimated_cost: float | None = None
    created_at: datetime
    updated_at: datetime


class ToolExecution(BaseDocument, BaseModel):
    """Per-tool-call audit record; separate collection for execution history."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    execution_id: UUID
    agent_id: UUID
    user_id: UUID
    step_index: int
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    result: dict | None = None
    status: str = "success"
    error_code: str | None = None
    latency_ms: int | None = None
    created_at: datetime