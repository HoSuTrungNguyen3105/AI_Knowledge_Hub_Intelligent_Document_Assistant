from app.schemas.providers import ModelCapabilities, ProviderModel
from app.services.ai.openai_provider import OpenAIModel, OpenAIProvider


def _price(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


class GroqProvider(OpenAIProvider):
    """Groq exposes an OpenAI-compatible model listing.

    Fixed endpoint https://api.groq.com/openai/v1/models with Bearer auth. The
    listing mixes chat models with audio and classification models and proves no
    generation access, so chat capability stays unknown for ordinary models.

    Two kinds of model are explicitly marked non-chat from listing metadata so
    they never reach the chat picker (a streaming chat request to them fails):
      * output_modalities without "text" — whisper (transcription) and orpheus
        (speech) cannot produce chat text.
      * the Llama Prompt Guard family — a text classifier that rejects streaming
        chat (verified: HTTP 400 "text classification models do not support
        streaming"), identified by its model id.

    Groq also publishes per-token USD pricing; it is captured for ESTIMATED cost
    only and never treated as a provider-confirmed charge.
    """

    provider_id = "groq"
    _non_chat_family = "prompt-guard"

    def _provider_model(self, model: OpenAIModel) -> ProviderModel:
        outputs = model.output_modalities
        non_text_output = outputs is not None and "text" not in outputs
        pricing = model.pricing
        prices = {
            "input_price_per_token": _price(pricing.prompt if pricing else None),
            "output_price_per_token": _price(pricing.completion if pricing else None),
        }
        if non_text_output or self._non_chat_family in model.id.lower():
            return ProviderModel(
                id=model.id,
                display_name=model.id,
                capabilities=ModelCapabilities(chat=False),
                capability_source="provider_metadata",
                **prices,
            )
        return ProviderModel(id=model.id, display_name=model.id, **prices)