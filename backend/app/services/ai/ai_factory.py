from app.services.ai.base_provider import BaseProvider
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.http import ModelListingHTTP
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.registry import get_provider


def create_provider(provider: str, http: ModelListingHTTP | None = None) -> BaseProvider:
    get_provider(provider, require_implemented=True)
    adapters = {"openai": OpenAIProvider, "gemini": GeminiProvider}
    return adapters[provider](http)
