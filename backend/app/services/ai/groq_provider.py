from app.services.ai.openai_provider import OpenAIProvider


class GroqProvider(OpenAIProvider):
    """Groq exposes an OpenAI-compatible model listing.

    Fixed endpoint https://api.groq.com/openai/v1/models with Bearer auth.
    /models returns no capability flags, so capabilities stay unknown and a
    successful listing proves no generation access (same contract as OpenAI).
    """

    provider_id = "groq"