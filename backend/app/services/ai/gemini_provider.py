import json
from collections.abc import AsyncIterator
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.providers import ModelCapabilities, ProviderModel
from app.services.ai.base_provider import BaseProvider, ProviderError, classify_provider_error
from app.services.ai.chat import ChatHTTP, SecretRedactor
from app.services.ai.chat_types import ChatEvent, ChatRequest, ToolCall, token_count
from app.services.ai.http import ListingSession, ModelListingHTTP


class GeminiModel(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=8, max_length=519, pattern=r"^models/[!-~]+$")
    displayName: str | None = Field(default=None, max_length=1024)
    description: str | None = Field(default=None, max_length=32768)
    supportedGenerationMethods: list[Annotated[str, Field(max_length=128)]] | None = Field(
        default=None, max_length=100
    )
    inputTokenLimit: int | None = Field(default=None, ge=0, le=2**31 - 1)
    outputTokenLimit: int | None = Field(default=None, ge=0, le=2**31 - 1)


class GeminiListing(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    # Google omits repeated fields when empty.
    models: list[GeminiModel] = Field(default_factory=list, max_length=1000)
    nextPageToken: str | None = Field(default=None, max_length=4096)


class GeminiProvider(BaseProvider):
    def __init__(
        self,
        http: ModelListingHTTP | None = None,
        chat_http: ChatHTTP | None = None,
    ):
        self.http = http or ModelListingHTTP()
        self.chat_http = chat_http or ChatHTTP()

    def list_models(self, api_key: SecretStr) -> list[ProviderModel]:
        async def listing(session: ListingSession) -> list[ProviderModel]:
            models: list[ProviderModel] = []
            seen_ids: set[str] = set()
            seen_tokens: set[str] = set()
            token = None
            for _ in range(session.limits.max_pages):
                params = {"pageSize": 1000}
                if token:
                    params["pageToken"] = token
                payload = GeminiListing.model_validate(await session.get("gemini", params))
                for model in payload.models:
                    model_id = model.name.removeprefix("models/")
                    if model_id in seen_ids or len(models) >= session.limits.max_models:
                        raise ProviderError("invalid_provider_response")
                    seen_ids.add(model_id)
                    methods = model.supportedGenerationMethods
                    capabilities = ModelCapabilities()
                    if methods is not None:
                        capabilities.chat = bool(
                            {"generateContent", "generateMessage"} & set(methods)
                        )
                        capabilities.embeddings = bool(
                            {"embedContent", "batchEmbedContents"} & set(methods)
                        )
                        # Absence of stream methods is not evidence of no streaming.
                        if {"streamGenerateContent", "streamGenerateMessage"} & set(methods):
                            capabilities.streaming = True
                    models.append(
                        ProviderModel(
                            id=model_id,
                            display_name=model.displayName or model_id,
                            description=model.description,
                            capabilities=capabilities,
                            input_token_limit=model.inputTokenLimit,
                            output_token_limit=model.outputTokenLimit,
                            capability_source="provider_metadata",
                        )
                    )
                token = payload.nextPageToken
                if not token:
                    return models
                if token in seen_tokens:
                    raise ProviderError("invalid_provider_response")
                seen_tokens.add(token)
            raise ProviderError("invalid_provider_response")

        return self.http.run(listing, api_key)

    @staticmethod
    def _contents(request: ChatRequest) -> list[dict]:
        contents: list[dict] = []
        real_ids = {
            call.id for turn in request.turns for call in turn.tool_calls
            if call.replay_metadata.get("id")
        }
        for turn in request.turns:
            if turn.role == "tool":
                # Gemini expects the function result as a JSON object under
                # functionResponse.response; tool content is the serialized dict.
                response: dict = {}
                raw = turn.content.strip()
                if raw:
                    try:
                        parsed = json.loads(raw)
                    except (ValueError, RecursionError):
                        parsed = None
                    if isinstance(parsed, dict):
                        response = parsed
                    else:
                        response = {"result": turn.content}
                function_response = {"name": turn.tool_name or "", "response": response}
                if turn.tool_call_id in real_ids:
                    function_response["id"] = turn.tool_call_id
                part = {"functionResponse": function_response}
                # All responses to a parallel model turn must stay in one Content,
                # in call order (including repeated calls to the same function).
                if contents and contents[-1]["role"] == "function":
                    contents[-1]["parts"].append(part)
                else:
                    contents.append({"role": "function", "parts": [part]})
            elif turn.role == "assistant" and turn.tool_calls:
                parts: list[dict] = []
                if turn.content:
                    parts.append({"text": turn.content})
                for call in turn.tool_calls:
                    function_call = {"name": call.name, "args": call.arguments}
                    if call.replay_metadata.get("id"):
                        function_call["id"] = call.id
                    part = {"functionCall": function_call}
                    if "thoughtSignature" in call.replay_metadata:
                        part["thoughtSignature"] = call.replay_metadata["thoughtSignature"]
                    parts.append(part)
                contents.append({"role": "model", "parts": parts})
            else:
                contents.append(
                    {
                        "role": "user" if turn.role == "user" else "model",
                        "parts": [{"text": turn.content}],
                    }
                )
        return contents

    async def stream_chat(
        self, api_key: SecretStr, request: ChatRequest
    ) -> AsyncIterator[ChatEvent]:
        payload: dict = {"contents": self._contents(request)}
        if request.system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
        generation: dict = {}
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            generation["maxOutputTokens"] = request.max_output_tokens
        if generation:
            payload["generationConfig"] = generation
        if request.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in request.tools
                    ]
                }
            ]
        redactor = SecretRedactor(api_key.get_secret_value())
        call_index = 0
        async for event in self.chat_http.stream(
            "gemini", api_key, payload, params={"alt": "sse"}, model=request.model
        ):
            if "error" in event:
                # Same mid-stream error shape as the OpenAI-compatible
                # adapters: classify it instead of silently dropping it.
                raise ProviderError(classify_provider_error(event.get("error")))
            candidates = event.get("candidates")
            if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
                content = candidates[0].get("content")
                if isinstance(content, dict):
                    parts = content.get("parts")
                    if isinstance(parts, list):
                        for part in parts:
                            if not isinstance(part, dict):
                                continue
                            text = part.get("text")
                            if isinstance(text, str) and text:
                                redactor.feed(text)
                                yield ChatEvent("delta", text=text)
                            function_call = part.get("functionCall")
                            if isinstance(function_call, dict):
                                name = function_call.get("name")
                                args = function_call.get("args")
                                if isinstance(name, str) and name:
                                    arguments = args if isinstance(args, dict) else {}
                                    encoded = json.dumps(arguments, ensure_ascii=False)
                                    if call_index >= 16 or len(name) > 64 or len(encoded) > 65536:
                                        raise ProviderError("generation_failed")
                                    redactor.feed(name)
                                    redactor.feed(encoded)
                                    call_index += 1
                                    replay: dict = {}
                                    call_id = function_call.get("id")
                                    if isinstance(call_id, str) and call_id:
                                        if len(call_id) > 512:
                                            raise ProviderError("generation_failed")
                                        redactor.feed(call_id)
                                        replay["id"] = True
                                    else:
                                        call_id = f"gemini_{name}_{call_index}"
                                    signature = part.get("thoughtSignature")
                                    if signature is not None:
                                        if not isinstance(signature, str) or len(signature) > 32768:
                                            raise ProviderError("generation_failed")
                                        redactor.feed(signature)
                                        replay["thoughtSignature"] = signature
                                    yield ChatEvent(
                                        "tool_call",
                                        tool_call=ToolCall(
                                            id=call_id, name=name, arguments=arguments,
                                            replay_metadata=replay,
                                        ),
                                    )
            usage = event.get("usageMetadata")
            if isinstance(usage, dict):
                yield ChatEvent(
                    "usage",
                    input_tokens=token_count(usage.get("promptTokenCount")),
                    output_tokens=token_count(usage.get("candidatesTokenCount")),
                )
