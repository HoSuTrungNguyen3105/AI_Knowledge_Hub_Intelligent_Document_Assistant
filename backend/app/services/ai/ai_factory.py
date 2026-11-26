from app.services.ai.base_provider import BaseProvider
from app.services.ai.chat import ChatHTTP
from app.services.ai.deepseek_provider import DeepSeekProvider
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.groq_provider import GroqProvider
from app.services.ai.grok_provider import GrokProvider
from app.services.ai.http import ModelListingHTTP
from app.services.ai.ollama_provider import OllamaProvider
from app.services.ai.openai_provider import OpenAIProvider
from app.services.ai.registry import get_provider


def create_provider(
    provider: str,
    http: ModelListingHTTP | None = None,
    chat_http: ChatHTTP | None = None,
) -> BaseProvider:
    get_provider(provider, require_implemented=True)
    adapters = {"openai": OpenAIProvider, "gemini": GeminiProvider, "groq": GroqProvider, "deepseek": DeepSeekProvider, "grok": GrokProvider, "ollama": OllamaProvider}
    return adapters[provider](http, chat_http)
