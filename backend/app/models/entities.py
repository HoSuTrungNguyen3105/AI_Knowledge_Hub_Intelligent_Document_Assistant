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
    agent_ids: list[UUID] = Field(default_factory=list)  # collaboration room members (Module 03)
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


# --- Phase 6: Multi-Agent Collaboration -------------------------------------


class AgentTeamMember(BaseModel):
    agent_id: UUID
    role: str = "member"
    enabled: bool = True


class AgentTeam(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    name: str
    description: str | None = None
    coordinator_agent_id: UUID
    members: list[AgentTeamMember] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AgentWorkflow(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    team_id: UUID
    title: str
    goal: str
    status: str = "queued"  # queued|running|waiting(paused)|completed|failed|cancelled
    output_type: str = "text"  # text|website_zip
    design_brief: str | None = None  # user design options for website artifacts
    requires_approval: bool = False  # human gate before completion (Module 10)
    approval_status: str = "none"  # none|pending|approved|rejected|changes_requested
    artifact_status: str = "none"  # none|ready|failed (website_zip workflows only)
    artifact_file_count: int = 0
    artifact_total_bytes: int = 0
    artifact_error_code: str | None = None
    current_step: int = 0
    max_steps: int = 12
    budget: dict = Field(default_factory=dict)
    usage: dict = Field(default_factory=dict)
    final_result: str | None = None
    error_code: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class AgentTask(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    workflow_id: UUID
    parent_task_id: UUID | None = None
    title: str
    description: str = ""
    assigned_agent_id: UUID | None = None
    created_by_agent_id: UUID | None = None
    depends_on: list[UUID] = Field(default_factory=list)
    status: str = "pending"  # pending|in_progress|review|completed|failed|cancelled
    priority: str = "normal"
    result: str | None = None
    revision_count: int = 0
    created_at: datetime
    updated_at: datetime


class AgentMessage(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    workflow_id: UUID
    task_id: UUID | None = None
    from_agent_id: str = "user"
    to_agent_id: str = "coordinator"
    message_type: str = "MESSAGE"
    content: str = ""
    context_refs: list[str] = Field(default_factory=list)
    status: str = "PENDING"  # PENDING|PROCESSING|DELIVERED|COMPLETED|FAILED
    created_at: datetime
    processed_at: datetime | None = None
    error_code: str | None = None


class AgentWorkflowFile(BaseDocument, BaseModel):
    """One extracted website file of a website_zip workflow artifact."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    workflow_id: UUID
    path: str
    content: str
    size_bytes: int
    created_at: datetime


class AgentWorkflowEvent(BaseDocument, BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(alias="_id")
    user_id: UUID
    workflow_id: UUID
    event_type: str
    actor_id: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime
