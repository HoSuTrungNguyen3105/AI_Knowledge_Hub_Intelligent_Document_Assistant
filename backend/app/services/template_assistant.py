"""AI Template Assistant (Phase 5 of Project_Workflow_update.md).

Explains a shared workflow template, guides setup, lists the credentials
it needs and proposes customizations. The assistant calls the caller's
own configured provider through the same provider layer as the Code
Analyzer — nothing is answered from canned text. A customization comes
back as a *proposal*: a full workflow JSON the user reviews in the UI;
only the separate apply endpoint installs it (into the user's own n8n,
as their own copy). The shared template is never modified by the
assistant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.repositories.chat import ChatRepository
from app.repositories.providers import ProviderRepository
from app.schemas.workflow_templates import (
    AssistantIn,
    AssistantOut,
    TemplateDetailOut,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.ai.chat_types import ChatRequest, ChatTurn
from app.services.ai.registry import PROVIDERS
from app.services.synthesis import require_chat_target

MAX_CONTEXT_CHARS = 12000
COMPACT_CONTEXT_CHARS = 3000
TIMEOUT_SECONDS = 60
MAX_CANDIDATES = 5

logger = logging.getLogger(__name__)

# Well-known chat model families are tried first; known small-context
# models (allam-2-7b has a 4k window that a full workflow JSON plus a
# useful answer can exceed on input alone) are tried last.
_PREFERRED_MARKERS = (
    "gpt-oss",
    "llama",
    "qwen",
    "gemini",
    "gpt-4",
    "gpt-5",
    "claude",
    "deepseek",
    "kimi",
)
_SMALL_CONTEXT_MARKERS = ("allam",)


def _candidate_rank(model_id: str) -> tuple[int, str]:
    lowered = model_id.lower()
    if any(marker in lowered for marker in _SMALL_CONTEXT_MARKERS):
        return (2, lowered)
    if any(marker in lowered for marker in _PREFERRED_MARKERS):
        return (0, lowered)
    return (1, lowered)

TASK_INSTRUCTIONS = {
    "explain": (
        "Giải thích workflow n8n này làm gì: mục đích tổng thể, luồng dữ liệu "
        "qua từng node theo thứ tự kết nối, đầu vào/đầu ra. Viết tiếng Việt, "
        "rõ ràng, có cấu trúc."
    ),
    "explain_node": (
        "Giải thích chi tiết node được chỉ định trong workflow: vai trò của "
        "nó trong luồng, tham số quan trọng và lưu ý khi cấu hình. Viết "
        "tiếng Việt."
    ),
    "setup_guide": (
        "Viết hướng dẫn cấu hình từng bước để chạy được workflow này trong "
        "n8n: credential cần tạo (đúng loại đã liệt kê), tham số cần điền, "
        "thứ tự bật workflow và cách kiểm tra. Viết tiếng Việt."
    ),
    "api_keys": (
        "Liệt kê mọi API key / credential cần thiết cho workflow này dựa "
        "trên danh sách credential types và node, kèm nơi lấy key và quyền "
        "tối thiểu. Nếu workflow không cần key nào, nói rõ. Viết tiếng Việt."
    ),
    "customize": (
        "Người dùng muốn tùy chỉnh workflow. Hãy trả về DUY NHẤT một khối "
        "JSON workflow n8n hoàn chỉnh đã sửa theo yêu cầu (giữ nguyên các "
        "node không liên quan, giữ định dạng nodes/connections của n8n), "
        "không kèm giải thích ngoài JSON."
    ),
}


def _workflow_context(template: TemplateDetailOut) -> str:
    workflow = template.workflow_json or {}
    slim_nodes = []
    for node in workflow.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        params = node.get("parameters") or {}
        slim_nodes.append(
            {
                "name": node.get("name"),
                "type": node.get("type"),
                "parameters": {
                    key: (str(value)[:200]) for key, value in list(params.items())[:12]
                },
                "credentials": list((node.get("credentials") or {}).keys()),
            }
        )
    context = {
        "name": template.name,
        "category": template.category,
        "credential_types": template.credential_types,
        "nodes": slim_nodes,
        "connections": workflow.get("connections") or {},
    }
    text = json.dumps(context, ensure_ascii=False)
    return text[:MAX_CONTEXT_CHARS]


def parse_proposal(text: str) -> dict | None:
    """Extract a valid n8n workflow JSON from a model reply, if present."""
    candidate = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        return None
    for node in data["nodes"]:
        if not isinstance(node, dict) or not node.get("name") or not node.get("type"):
            return None
    if not isinstance(data.get("connections"), dict):
        data["connections"] = {}
    return data


class TemplateAssistantService:
    def __init__(
        self, db: AsyncIOMotorDatabase, settings: Settings, chat_http: ChatHTTP | None = None
    ):
        self.db = db
        self.settings = settings
        self.chat_http = chat_http
        self.vault = CredentialVault(settings.credential_encryption_key)
        self.providers = ProviderRepository(db)
        self.requests = ChatRepository(db)

    async def _resolve_candidates(
        self, user_id, provider: str | None, model_id: str | None
    ) -> list[tuple[str, str, str]]:
        """Ordered (provider, model, key) candidates to try, best first.

        The assistant must not depend on a single auto-picked model: the
        first synced model of a provider can be a small-context or
        otherwise unsuitable one while another configured model works
        fine. Candidates prefer well-known chat models and deprioritise
        known small-context ones; an explicitly requested provider+model
        is honoured as the only candidate.
        """
        if provider and model_id:
            credential, _model = await require_chat_target(
                self.providers, user_id, provider, model_id
            )
            key = self.vault.decrypt(credential.encrypted_api_key, user_id, provider)
            return [(provider, model_id, key)]
        candidates: list[tuple[str, str, str]] = []
        for provider_id, definition in PROVIDERS.items():
            if not definition.implemented:
                continue
            credential = await self.providers.get(user_id, provider_id)
            if credential is None or not credential.enabled:
                continue
            models = [
                model
                for model in await self.providers.models(user_id, provider_id)
                if model.capabilities.get("chat") is not False
            ]
            if not models:
                continue
            key = self.vault.decrypt(
                credential.encrypted_api_key, user_id, provider_id
            )
            for model in sorted(models, key=lambda item: _candidate_rank(item.id)):
                candidates.append((provider_id, model.id, key))
        if not candidates:
            raise ProviderError("template_assistant_unavailable")
        return candidates[:MAX_CANDIDATES]

    async def ask(
        self, user_id, template: TemplateDetailOut, payload: AssistantIn
    ) -> AssistantOut:
        candidates = await self._resolve_candidates(
            user_id, payload.provider, payload.model
        )
        instruction = TASK_INSTRUCTIONS[payload.task]

        def build_prompt(context: str) -> str:
            parts = [instruction, "", "Thông tin workflow (JSON rút gọn):", context]
            if payload.task == "explain_node" and payload.node_name:
                parts.append(f"Node cần giải thích: {payload.node_name}")
            if payload.prompt:
                parts.append(f"Yêu cầu của người dùng: {payload.prompt}")
            return "\n".join(parts)

        full_context = _workflow_context(template)
        prompts = [build_prompt(full_context)]
        compact_context = full_context[:COMPACT_CONTEXT_CHARS]
        if compact_context != full_context:
            # Second pass with a much smaller prompt for small-context
            # models, whose limit the full workflow JSON alone can fill.
            prompts.append(build_prompt(compact_context))
        budgets = (
            (4096, 2048, 1024) if payload.task == "customize" else (2048, 1024, 512)
        )
        started = time.monotonic()
        text = ""
        input_tokens = output_tokens = None
        status = "error"
        last_error_code: str | None = None
        provider = candidates[0][0]
        model_id = candidates[0][1]
        for prompt in prompts:
            if status == "success":
                break
            for cand_provider, cand_model, cand_key in candidates:
                if status == "success":
                    break
                provider, model_id = cand_provider, cand_model
                adapter = create_provider(cand_provider, chat_http=self.chat_http)
                for budget in budgets:
                    request = ChatRequest(
                        model=cand_model,
                        turns=(ChatTurn("user", prompt),),
                        max_output_tokens=budget,
                    )
                    chunks: list[str] = []
                    attempt_in = attempt_out = None

                    async def collect() -> None:
                        nonlocal attempt_in, attempt_out
                        async for event in adapter.stream_chat(cand_key, request):
                            if event.kind == "delta":
                                chunks.append(event.text)
                            elif event.kind == "usage":
                                if event.input_tokens is not None:
                                    attempt_in = event.input_tokens
                                if event.output_tokens is not None:
                                    attempt_out = event.output_tokens

                    try:
                        await asyncio.wait_for(collect(), timeout=TIMEOUT_SECONDS)
                    except ProviderError as exc:
                        # Keep the provider's real error code instead of
                        # masking it as a generic generation failure.
                        last_error_code = exc.code
                        logger.warning(
                            "template assistant attempt failed: provider=%s "
                            "model=%s budget=%s code=%s",
                            cand_provider,
                            cand_model,
                            budget,
                            exc.code,
                        )
                        continue
                    except Exception as exc:  # noqa: BLE001 - try next budget/model
                        last_error_code = "generation_failed"
                        logger.warning(
                            "template assistant attempt failed: provider=%s "
                            "model=%s budget=%s error=%r",
                            cand_provider,
                            cand_model,
                            budget,
                            exc,
                        )
                        continue
                    candidate_text = "".join(chunks)
                    if candidate_text.strip():
                        text = candidate_text
                        input_tokens, output_tokens = attempt_in, attempt_out
                        status = "success"
                        break
                    last_error_code = "generation_failed"
        latency_ms = int((time.monotonic() - started) * 1000)
        await self.requests.record_request(
            user_id,
            provider=provider,
            model=model_id,
            status=status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        if status != "success":
            raise ProviderError(last_error_code or "generation_failed")
        proposal = parse_proposal(text) if payload.task == "customize" else None
        answer = text
        if proposal is not None:
            answer = (
                "AI đã tạo bản tùy chỉnh. Hãy xem JSON đề xuất bên dưới và bấm "
                "Áp dụng để cài bản này vào tài khoản của bạn (bản gốc trong "
                "thư viện không thay đổi)."
            )
        elif payload.task == "customize":
            answer = (
                "AI không trả về JSON workflow hợp lệ nên chưa có đề xuất để áp "
                "dụng. Nội dung AI trả lời:\n\n" + text
            )
        return AssistantOut(
            answer=answer,
            proposal=proposal,
            provider=provider,
            model=model_id,
            task=payload.task,
        )
