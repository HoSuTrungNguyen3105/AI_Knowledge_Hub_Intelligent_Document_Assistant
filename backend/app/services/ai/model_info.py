"""Static, curated model knowledge the provider listings do not carry.

Provider list APIs never say whether a model bills per token, so the
UI badge data comes from two honest sources, in order:

1. Per-token prices the provider itself publishes in its listing
   (Groq does this) — stored on the model record at sync time.
2. The reference table below: published list prices (USD per 1M
   tokens, input/output) for well-known models, verified against the
   providers' public pricing pages in November 2026. Prices change;
   this table is a dated reference, not a live feed, and the UI says so.

Ollama models run under the account's Ollama Cloud subscription, so
they are marked "subscription" instead of per-token priced.
"""

from app.schemas.providers import ModelPricing, ProviderModel

# (model id prefix, input USD per 1M, output USD per 1M). Longest
# prefixes first so "gpt-4o-mini" wins over "gpt-4o".
REFERENCE_PRICES: dict[str, tuple[tuple[str, float, float], ...]] = {
    "openai": (
        ("gpt-4o-mini", 0.15, 0.60),
        ("gpt-4.1-mini", 0.40, 1.60),
        ("gpt-4o", 2.50, 10.00),
        ("gpt-4.1", 2.00, 8.00),
    ),
    "gemini": (
        ("gemini-2.5-flash-lite", 0.10, 0.40),
        ("gemini-2.0-flash-lite", 0.075, 0.30),
        ("gemini-3.8-flash", 0.75, 3.75),
        ("gemini-3.5-flash", 1.50, 9.00),
        ("gemini-3.1-pro", 2.00, 12.00),
        ("gemini-2.5-flash", 0.30, 2.50),
        ("gemini-2.5-pro", 1.25, 10.00),
        ("gemini-2.0-flash", 0.10, 0.40),
        ("gemini-3-flash", 0.50, 3.00),
    ),
}


def pricing_for(provider: str, model: ProviderModel) -> ModelPricing:
    """Classify one synced model for display; never invents a price."""
    if model.input_price_per_token is not None or model.output_price_per_token is not None:
        return ModelPricing(
            tier="priced",
            input_per_million=(
                model.input_price_per_token * 1_000_000
                if model.input_price_per_token is not None
                else None
            ),
            output_per_million=(
                model.output_price_per_token * 1_000_000
                if model.output_price_per_token is not None
                else None
            ),
            source="provider",
        )
    for prefix, input_price, output_price in REFERENCE_PRICES.get(provider, ()):
        if model.id.startswith(prefix):
            return ModelPricing(
                tier="priced",
                input_per_million=input_price,
                output_per_million=output_price,
                source="reference",
            )
    if provider == "ollama":
        return ModelPricing(tier="subscription", source="provider_plan")
    return ModelPricing(tier="unknown")
