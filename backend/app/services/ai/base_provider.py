from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import SecretStr

from app.schemas.providers import ProviderModel
from app.services.ai.chat_types import ChatEvent, ChatRequest

# Only fixed, public messages may cross the API boundary. Never include upstream text.
ERRORS = {
    "provider_not_found": (404, "Unknown provider."),
    "provider_not_implemented": (409, "This provider is not integrated yet."),
    "credentials_missing": (409, "Save an API key before using this provider."),
    "encryption_unavailable": (
        503,
        "Credential encryption is unavailable or the key cannot be read.",
    ),
    "provider_authentication_failed": (400, "The provider rejected the saved API key."),
    "provider_rate_limited": (429, "The provider rate limit was reached. Try again later."),
    "provider_timeout": (504, "The provider connection timed out."),
    "provider_unavailable": (502, "The provider is unavailable. Try again later."),
    "invalid_provider_response": (502, "The provider returned an invalid model listing."),
    "configuration_changed": (409, "Provider configuration changed. Reload and try again."),
    "invalid_default_model": (409, "Select a model from this provider's current synced catalog."),
    "invalid_provider_configuration": (422, "Invalid provider configuration."),
    "model_not_chat_capable": (409, "This model does not support chat generation."),
    "model_not_synced": (409, "Sync this provider's models before starting a chat."),
    "provider_disabled": (409, "This provider is disabled. Enable it in Settings."),
    "conversation_not_found": (404, "Conversation not found."),
    "empty_message": (422, "Message content cannot be empty."),
    "generation_failed": (502, "The provider returned an invalid generation response."),
    "model_tools_unsupported": (400, "The selected model does not support tool calling."),
    "provider_request_rejected": (400, "The provider rejected the generation request."),
    "comparison_not_found": (404, "Comparison not found."),
    "invalid_comparison_targets": (422, "Select 2-4 distinct synced chat models to compare."),
    "no_successful_runs": (409, "Synthesis needs at least one successful answer."),
    "agent_not_found": (404, "Agent not found."),
    "execution_not_found": (404, "Execution not found."),
    "invalid_agent_tools": (422, "Select only available tools for this agent."),
    "model_not_tool_capable": (409, "This model does not support tool calling."),
    "agent_step_limit": (409, "The agent reached its maximum number of steps."),
    "agent_budget_exceeded": (409, "The agent reached its token budget."),
    "agent_timeout": (504, "The agent execution timed out."),
    "team_not_found": (404, "Agent team not found."),
    "workflow_not_found": (404, "Agent workflow not found."),
    "task_not_found": (404, "Agent task not found."),
    "invalid_team_members": (422, "Select only your own existing agents for this team."),
    "coordinator_not_in_team": (422, "The coordinator must be a member of the team."),
    "invalid_team_role": (422, "Select a valid team role."),
    "workflow_not_runnable": (409, "This workflow cannot be started in its current state."),
    "workflow_already_running": (409, "This workflow is already running."),
    "workflow_step_limit": (409, "The workflow reached its maximum number of agent turns."),
    "workflow_revision_limit": (409, "The task reached its maximum number of revisions."),
    "workflow_timeout": (504, "The workflow timed out."),
    "n8n_unreachable": (
        503,
        "n8n is not reachable. Start the local n8n stack (Docker) and try again.",
    ),
    "n8n_run_failed": (
        502,
        "The n8n workflow run failed. Open the execution in n8n for details.",
    ),
    "invalid_factory_roles": (422, "Assign agents only to the seven team roles."),
    "factory_run_not_found": (404, "That AI Factory run does not exist."),
    "invalid_callback_token": (401, "The AI Factory run callback token is invalid."),
    "seed_disabled": (403, "Demo seeding is disabled in the production environment."),
    "seed_provider_required": (
        422,
        "Configure a provider with a synced model before seeding demo data.",
    ),
    "validation_error": (422, "The submitted data is invalid."),
    "artifact_no_files": (422, "The agent did not return any valid website files."),
    "artifact_missing_index": (422, "The generated website is missing index.html."),
    "artifact_missing_entry": (
        422,
        "The generated artifact has no entry point (index.html or package.json).",
    ),
    "artifact_limit_exceeded": (422, "The generated website exceeds the artifact size limits."),
    "artifact_not_ready": (409, "This workflow has no ZIP artifact ready to download."),
}


# Bounded markers used to classify a provider 4xx error object. Upstream error
# text is inspected in memory only to pick one fixed public code; it is never
# copied into an exception, a log line or a response, so a credential echoed
# by the provider cannot leak through this path.
_TOOL_ERROR_MARKERS = ("tool", "function call", "function_call", "function-calling")
_MAX_ERROR_FIELD_CHARS = 512


def classify_provider_error(error: object) -> str:
    """Classify a provider error object into a fixed public code.

    Accepts the OpenAI-style ``{"code", "type", "message"}`` dict (Gemini uses
    ``{"code", "message", "status"}``) or a bare string. Only an error that
    clearly blames tool/function calling maps to ``model_tools_unsupported``;
    everything else is a generic ``provider_request_rejected``.
    """
    fields: list[str] = []
    if isinstance(error, dict):
        for key in ("code", "type", "message", "status"):
            value = error.get(key)
            if isinstance(value, str):
                fields.append(value[:_MAX_ERROR_FIELD_CHARS])
    elif isinstance(error, str):
        fields.append(error[:_MAX_ERROR_FIELD_CHARS])
    text = " ".join(fields).lower()
    if any(marker in text for marker in _TOOL_ERROR_MARKERS):
        return "model_tools_unsupported"
    return "provider_request_rejected"


class ProviderError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.status_code, self.message = ERRORS[code]
        super().__init__(self.message)

    @property
    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class BaseProvider(ABC):
    """Implemented surface: read-only model listing and chat generation/streaming.

    Generation adapters forward tool specs and surface the model's tool-call
    requests as events; actual tool execution is handled by the agent service
    against a fixed allowlist, never by the adapter. Model metadata describes
    upstream capabilities, not adapter functionality. Generation never exposes
    upstream text or credentials in errors; only fixed public messages cross the
    API boundary.
    """

    @abstractmethod
    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        """Return a validated catalog or raise a sanitized ProviderError."""

    @abstractmethod
    def stream_chat(
        self, api_key: SecretStr, request: ChatRequest
    ) -> AsyncIterator[ChatEvent]:
        """Yield sanitized generation events or raise a sanitized ProviderError."""
