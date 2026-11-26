from dataclasses import dataclass
from types import MappingProxyType

from app.services.ai.base_provider import ProviderError


@dataclass(frozen=True)
class ProviderDefinition:
    id: str
    name: str
    implemented: bool


PROVIDERS = MappingProxyType(
    {
        item.id: item
        for item in (
            ProviderDefinition("openai", "OpenAI", True),
            ProviderDefinition("gemini", "Google Gemini", True),
            ProviderDefinition("groq", "Groq", True),
            ProviderDefinition("anthropic", "Anthropic Claude", False),
            ProviderDefinition("deepseek", "DeepSeek", True),
            ProviderDefinition("grok", "xAI Grok", True),
            ProviderDefinition("ollama", "Ollama", True),
        )
    }
)


def get_provider(provider: str, *, require_implemented: bool = False) -> ProviderDefinition:
    definition = PROVIDERS.get(provider)
    if definition is None:
        raise ProviderError("provider_not_found")
    if require_implemented and not definition.implemented:
        raise ProviderError("provider_not_implemented")
    return definition
