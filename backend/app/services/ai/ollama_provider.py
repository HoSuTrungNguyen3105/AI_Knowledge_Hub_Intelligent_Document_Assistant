from app.schemas.providers import ModelCapabilities, ProviderModel
from app.services.ai.openai_provider import OpenAIModel, OpenAIProvider


class OllamaProvider(OpenAIProvider):
    """Ollama Cloud exposes an OpenAI-compatible API.

    Fixed endpoints https://ollama.com/v1/models and
    https://ollama.com/v1/chat/completions with Bearer <redacted>, so the OpenAI
    adapter (model listing and streaming chat) is reused unchanged. Only
    Ollama Cloud is supported: the endpoint is fixed by design, so keys are
    never sent to a caller-supplied host such as a local Ollama instance.

    The listing mixes chat models with dedicated embedding models and proves
    no generation access, so chat capability stays unknown for ordinary
    models. Embedding-only models are explicitly marked non-chat from their
    model id (the "embed" family, e.g. nomic-embed-text, mxbai-embed-large)
    so they never reach the chat picker — a chat request to them fails.
    """

    provider_id = "ollama"
    _non_chat_family = "embed"

    def _provider_model(self, model: OpenAIModel) -> ProviderModel:
        if self._non_chat_family in model.id.lower():
            return ProviderModel(
                id=model.id,
                display_name=model.id,
                capabilities=ModelCapabilities(chat=False),
                capability_source="provider_metadata",
            )
        return ProviderModel(id=model.id, display_name=model.id)
