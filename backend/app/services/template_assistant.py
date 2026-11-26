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
TIMEOUT_SECONDS = 120

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

    async def _resolve_target(self, user_id, provider: str | None, model_id: str | None):
        if provider and model_id:
            credential, _model = await require_chat_target(
                self.providers, user_id, provider, model_id
            )
            key = self.vault.decrypt(credential.encrypted_api_key, user_id, provider)
            return provider, model_id, key
        for provider_id, definition in PROVIDERS.items():
            if not definition.implemented:
                continue
            credential = await self.providers.get(user_id, provider_id)
            if credential is None or not credential.enabled:
                continue
            for model in await self.providers.models(user_id, provider_id):
                if model.capabilities.get("chat") is False:
                    continue
                key = self.vault.decrypt(
                    credential.encrypted_api_key, user_id, provider_id
                )
                return provider_id, model.id, key
        raise ProviderError("template_assistant_unavailable")

    async def ask(
        self, user_id, template: TemplateDetailOut, payload: AssistantIn
    ) -> AssistantOut:
        provider, model_id, key = await self._resolve_target(
            user_id, payload.provider, payload.model
        )
        instruction = TASK_INSTRUCTIONS[payload.task]
        parts = [
            instruction,
            "",
            "Thông tin workflow (JSON rút gọn):",
            _workflow_context(template),
        ]
        if payload.task == "explain_node" and payload.node_name:
            parts.append(f"Node cần giải thích: {payload.node_name}")
        if payload.prompt:
            parts.append(f"Yêu cầu của người dùng: {payload.prompt}")
        prompt = "\n".join(parts)
        adapter = create_provider(provider, chat_http=self.chat_http)
        request = ChatRequest(
            model=model_id,
            turns=(ChatTurn("user", prompt),),
            max_output_tokens=8192 if payload.task == "customize" else 4096,
        )
        started = time.monotonic()
        chunks: list[str] = []
        input_tokens = output_tokens = None
        status = "success"

        async def collect() -> None:
            nonlocal input_tokens, output_tokens
            async for event in adapter.stream_chat(key, request):
                if event.kind == "delta":
                    chunks.append(event.text)
                elif event.kind == "usage":
                    if event.input_tokens is not None:
                        input_tokens = event.input_tokens
                    if event.output_tokens is not None:
                        output_tokens = event.output_tokens

        try:
            await asyncio.wait_for(collect(), timeout=TIMEOUT_SECONDS)
        except Exception:
            status = "error"
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
        text = "".join(chunks)
        if status != "success" or not text.strip():
            raise ProviderError("generation_failed")
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
