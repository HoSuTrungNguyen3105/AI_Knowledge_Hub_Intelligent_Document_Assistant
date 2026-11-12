import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import SecretStr

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.models import AIModel, Comparison
from app.models.entities import ComparisonRun, ComparisonSynthesis
from app.repositories.chat import ChatRepository
from app.repositories.compare import CompareRepository
from app.repositories.providers import ProviderRepository
from app.schemas.compare import (
    DEFAULT_TITLE,
    ComparisonCreate,
    ComparisonDetail,
    ComparisonList,
    ComparisonRunOut,
    ComparisonSummary,
    ComparisonSynthesisOut,
    RunBrief,
    SynthesizeRequest,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ERRORS, BaseProvider, ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.ai.chat_types import ChatRequest, ChatTurn
from app.services.ai.registry import get_provider


@dataclass
class PreparedRun:
    run: ComparisonRun
    adapter: BaseProvider
    api_key: SecretStr
    request: ChatRequest
    model: AIModel


@dataclass
class PreparedCompare:
    user_id: UUID
    comparison: Comparison
    runs: list[PreparedRun]


@dataclass
class PreparedSynthesis:
    user_id: UUID
    comparison: Comparison
    adapter: BaseProvider
    api_key: SecretStr
    request: ChatRequest
    model: AIModel


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _estimate_cost(
    model: AIModel, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """Estimated USD from published per-token pricing; never a confirmed charge."""
    total = 0.0
    has_price = False
    if model.input_price_per_token is not None and input_tokens is not None:
        total += model.input_price_per_token * input_tokens
        has_price = True
    if model.output_price_per_token is not None and output_tokens is not None:
        total += model.output_price_per_token * output_tokens
        has_price = True
    return total if has_price else None


class CompareService:
    """Parallel multi-model comparison with isolated per-run failures.

    Each run streams independently; one provider failing never aborts the others.
    Validation/ownership/capability are checked before the SSE stream opens.
    Synthesis is optional and only consumes successful answers.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        chat_http: ChatHTTP | None = None,
    ):
        self.repo = CompareRepository(db)
        self.providers = ProviderRepository(db)
        self.requests = ChatRepository(db)
        self.vault = CredentialVault(settings.credential_encryption_key)
        self.chat_http = chat_http

    async def create_comparison(
        self, user_id: UUID, payload: ComparisonCreate
    ) -> ComparisonDetail:
        for target in payload.targets:
            await self._require_target(user_id, target.provider, target.model)
        runs = [
            ComparisonRun(id=uuid4(), provider=t.provider, model=t.model)
            for t in payload.targets
        ]
        comparison = await self.repo.create(
            user_id,
            title=payload.title or payload.prompt[:60].strip() or DEFAULT_TITLE,
            prompt=payload.prompt,
            system_prompt=payload.system_prompt,
            temperature=payload.temperature,
            max_output_tokens=payload.max_output_tokens,
            runs=runs,
        )
        return self._detail(comparison)

    async def list_comparisons(self, user_id: UUID) -> ComparisonList:
        return ComparisonList(
            comparisons=[self._summary(c) for c in await self.repo.list(user_id)]
        )

    async def get_comparison(self, user_id: UUID, comparison_id: UUID) -> ComparisonDetail:
        return self._detail(await self._require_comparison(user_id, comparison_id))

    async def delete_comparison(self, user_id: UUID, comparison_id: UUID) -> None:
        if not await self.repo.delete(user_id, comparison_id):
            raise ProviderError("comparison_not_found")

    async def prepare_execute(self, user_id: UUID, comparison_id: UUID) -> PreparedCompare:
        comparison = await self._require_comparison(user_id, comparison_id)
        prepared: list[PreparedRun] = []
        for run in comparison.runs.values():
            credential, model = await self._require_target(user_id, run.provider, run.model)
            key = self.vault.decrypt(credential.encrypted_api_key, user_id, run.provider)
            prepared.append(
                PreparedRun(
                    run=run,
                    adapter=create_provider(run.provider, chat_http=self.chat_http),
                    api_key=key,
                    request=self._request(comparison, run.model),
                    model=model,
                )
            )
        return PreparedCompare(user_id, comparison, prepared)

    async def prepare_synthesize(
        self, user_id: UUID, comparison_id: UUID, payload: SynthesizeRequest
    ) -> PreparedSynthesis:
        comparison = await self._require_comparison(user_id, comparison_id)
        successful = [
            r for r in comparison.runs.values() if r.status == "success" and r.content
        ]
        if not successful:
            raise ProviderError("no_successful_runs")
        credential, model = await self._require_target(user_id, payload.provider, payload.model)
        key = self.vault.decrypt(credential.encrypted_api_key, user_id, payload.provider)
        request = ChatRequest(
            model=payload.model,
            turns=(ChatTurn("user", self._synthesis_prompt(comparison, successful)),),
            system_prompt=comparison.system_prompt,
            temperature=comparison.temperature,
            max_output_tokens=comparison.max_output_tokens,
        )
        return PreparedSynthesis(
            user_id, comparison, create_provider(payload.provider, chat_http=self.chat_http),
            key, request, model,
        )

    def _request(self, comparison: Comparison, model: str) -> ChatRequest:
        return ChatRequest(
            model=model,
            turns=(ChatTurn("user", comparison.prompt),),
            system_prompt=comparison.system_prompt,
            temperature=comparison.temperature,
            max_output_tokens=comparison.max_output_tokens,
        )

    @staticmethod
    def _synthesis_prompt(comparison: Comparison, runs: list[ComparisonRun]) -> str:
        lines = [f"Câu hỏi gốc: {comparison.prompt}", "", "Các câu trả lời từ những model khác:"]
        for run in runs:
            lines.append(f"\n--- {run.provider} / {run.model} ---\n{run.content}")
        lines.append(
            "\nHãy tổng hợp các câu trả lời trên thành một câu trả lời cuối thống nhất, "
            "chính xác và mạch lạc. Chỉ dùng thông tin từ các câu trả lời đã cho, "
            "không bịa thêm nguồn hay trích dẫn."
        )
        return "\n".join(lines)

    async def stream_prepared(self, prepared: PreparedCompare) -> AsyncIterator[dict]:
        user_id = prepared.user_id
        comparison = prepared.comparison
        yield {
            "event": "comparison",
            "data": {"comparison": self._detail(comparison).model_dump(mode="json")},
        }
        queue: asyncio.Queue = asyncio.Queue()

        async def run_one(pr: PreparedRun) -> None:
            started = time.monotonic()
            parts: list[str] = []
            input_tokens: int | None = None
            output_tokens: int | None = None
            status, error_code = "success", None
            try:
                async for event in pr.adapter.stream_chat(pr.api_key, pr.request):
                    if event.kind == "delta":
                        parts.append(event.text)
                        await queue.put(
                            {
                                "event": "run_delta",
                                "data": {"run_id": str(pr.run.id), "text": event.text},
                            }
                        )
                    elif event.kind == "usage":
                        if event.input_tokens is not None:
                            input_tokens = event.input_tokens
                        if event.output_tokens is not None:
                            output_tokens = event.output_tokens
            except ProviderError as error:
                status, error_code = "error", error.code
            except asyncio.CancelledError:
                await self._shielded_run(
                    user_id, comparison, pr, "".join(parts), "stopped", None,
                    input_tokens, output_tokens, started,
                )
                raise
            except Exception:
                # A single run must never hang or abort the whole comparison.
                status, error_code = "error", "generation_failed"
            # Always emit exactly one terminal event, even if persistence fails;
            # otherwise the aggregator loop below would wait on the queue forever.
            try:
                updated = await self._persist_run(
                    user_id, comparison, pr, "".join(parts), status, error_code,
                    input_tokens, output_tokens, started,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                status, error_code = "error", "generation_failed"
                updated = ComparisonRun(
                    **{
                        **pr.run.model_dump(),
                        "content": "".join(parts),
                        "status": status,
                        "error_code": error_code,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "latency_ms": _elapsed_ms(started),
                    }
                )
            await queue.put(
                {
                    "event": "run_error" if status == "error" else "run_done",
                    "data": {"run": self._run_out(updated).model_dump(mode="json")},
                }
            )

        tasks = [asyncio.create_task(run_one(pr)) for pr in prepared.runs]
        try:
            finished = 0
            while finished < len(tasks):
                event = await queue.get()
                yield event
                if event["event"] in ("run_done", "run_error"):
                    finished += 1
            await self.repo.touch(user_id, comparison.id)
            final = await self.repo.get(user_id, comparison.id)
            yield {
                "event": "done",
                "data": {"comparison": self._detail(final).model_dump(mode="json")},
            }
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def stream_synthesis(self, prepared: PreparedSynthesis) -> AsyncIterator[dict]:
        user_id = prepared.user_id
        comparison = prepared.comparison
        started = time.monotonic()
        parts: list[str] = []
        input_tokens: int | None = None
        output_tokens: int | None = None
        status, error_code = "success", None
        try:
            async for event in prepared.adapter.stream_chat(prepared.api_key, prepared.request):
                if event.kind == "delta":
                    parts.append(event.text)
                    yield {"event": "synthesis_delta", "data": {"text": event.text}}
                elif event.kind == "usage":
                    if event.input_tokens is not None:
                        input_tokens = event.input_tokens
                    if event.output_tokens is not None:
                        output_tokens = event.output_tokens
        except ProviderError as error:
            status, error_code = "error", error.code
        except asyncio.CancelledError:
            task = asyncio.create_task(
                self._persist_synthesis(
                    user_id, comparison, prepared, "".join(parts), "stopped", None,
                    input_tokens, output_tokens, started,
                )
            )
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                pass
            raise
        synthesis = await self._persist_synthesis(
            user_id, comparison, prepared, "".join(parts), status, error_code,
            input_tokens, output_tokens, started,
        )
        if status == "error":
            yield {
                "event": "synthesis_error",
                "data": {"code": error_code, "message": ERRORS[error_code][1]},
            }
        else:
            yield {
                "event": "synthesis_done",
                "data": {"synthesis": self._synthesis_out(synthesis).model_dump(mode="json")},
            }
        final = await self.repo.get(user_id, comparison.id)
        yield {"event": "done", "data": {"comparison": self._detail(final).model_dump(mode="json")}}

    async def _shielded_run(self, *args) -> None:
        task = asyncio.create_task(self._persist_run(*args))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            pass

    async def _persist_run(
        self, user_id, comparison, pr, content, status, error_code,
        input_tokens, output_tokens, started,
    ) -> ComparisonRun:
        values = {
            "content": content,
            "status": status,
            "error_code": error_code,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": _elapsed_ms(started),
            "estimated_cost": _estimate_cost(pr.model, input_tokens, output_tokens),
        }
        await self.repo.update_run(user_id, comparison.id, str(pr.run.id), values)
        await self.requests.record_request(
            user_id, provider=pr.run.provider, model=pr.run.model, status=status,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=values["latency_ms"],
        )
        return ComparisonRun(**{**pr.run.model_dump(), **values})

    async def _persist_synthesis(
        self, user_id, comparison, prepared, content, status, error_code,
        input_tokens, output_tokens, started,
    ) -> ComparisonSynthesis:
        synthesis = ComparisonSynthesis(
            provider=prepared.adapter.provider_id,
            model=prepared.request.model,
            status=status,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=_elapsed_ms(started),
            error_code=error_code,
            estimated_cost=_estimate_cost(prepared.model, input_tokens, output_tokens),
        )
        await self.repo.set_synthesis(user_id, comparison.id, synthesis.model_dump())
        await self.requests.record_request(
            user_id, provider=synthesis.provider, model=synthesis.model, status=status,
            input_tokens=input_tokens, output_tokens=output_tokens,
            latency_ms=synthesis.latency_ms,
        )
        return synthesis

    async def _require_comparison(self, user_id: UUID, comparison_id: UUID) -> Comparison:
        comparison = await self.repo.get(user_id, comparison_id)
        if comparison is None:
            raise ProviderError("comparison_not_found")
        return comparison

    async def _require_target(self, user_id: UUID, provider: str, model_id: str):
        get_provider(provider, require_implemented=True)
        credential = await self.providers.get(user_id, provider)
        if credential is None:
            raise ProviderError("credentials_missing")
        if not credential.enabled:
            raise ProviderError("provider_disabled")
        model = await self.providers.get_model(credential.id, model_id)
        if model is None:
            raise ProviderError("model_not_synced")
        if model.capabilities.get("chat") is False:
            raise ProviderError("model_not_chat_capable")
        return credential, model

    def _summary(self, comparison: Comparison) -> ComparisonSummary:
        return ComparisonSummary(
            id=comparison.id,
            title=comparison.title,
            targets=[
                RunBrief(provider=r.provider, model=r.model, status=r.status)
                for r in comparison.runs.values()
            ],
            has_synthesis=comparison.synthesis is not None,
            created_at=comparison.created_at,
            updated_at=comparison.updated_at,
        )

    def _detail(self, comparison: Comparison) -> ComparisonDetail:
        return ComparisonDetail(
            **self._summary(comparison).model_dump(),
            prompt=comparison.prompt,
            system_prompt=comparison.system_prompt,
            temperature=comparison.temperature,
            max_output_tokens=comparison.max_output_tokens,
            runs=[self._run_out(r) for r in comparison.runs.values()],
            synthesis=self._synthesis_out(comparison.synthesis) if comparison.synthesis else None,
        )

    @staticmethod
    def _run_out(run: ComparisonRun) -> ComparisonRunOut:
        return ComparisonRunOut(
            id=run.id, provider=run.provider, model=run.model, status=run.status,
            content=run.content, input_tokens=run.input_tokens, output_tokens=run.output_tokens,
            latency_ms=run.latency_ms, error_code=run.error_code, estimated_cost=run.estimated_cost,
        )

    @staticmethod
    def _synthesis_out(synthesis: ComparisonSynthesis) -> ComparisonSynthesisOut:
        return ComparisonSynthesisOut(
            provider=synthesis.provider, model=synthesis.model, status=synthesis.status,
            content=synthesis.content, input_tokens=synthesis.input_tokens,
            output_tokens=synthesis.output_tokens, latency_ms=synthesis.latency_ms,
            error_code=synthesis.error_code, estimated_cost=synthesis.estimated_cost,
        )