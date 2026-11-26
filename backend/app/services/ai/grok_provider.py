from app.services.ai.openai_provider import OpenAIProvider


class GrokProvider(OpenAIProvider):
    """xAI Grok exposes an OpenAI-compatible API at api.x.ai.

    Both the model listing (id/object/created/owned_by, the strict OpenAI
    shape) and streaming chat completions match the OpenAI adapter, so
    only the fixed endpoints differ (registered under the "grok" key in
    the listing and chat endpoint maps).
    """

    provider_id = "grok"
