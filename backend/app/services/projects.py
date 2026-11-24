"""Workforce projects + Project Analysis AI (mindflow-workforce-feature
sections 2 + 9, wave 3).

Projects hold the raw requirements. `analyze` runs one bounded LLM pass
with a caller-chosen provider/model (credentials resolved exactly like
Agent runs: the caller's own vault key, model must be synced and
chat-capable), then validates the returned JSON against AnalysisDraft
before storing it in project_analyses — unvalidated LLM output is never
written, per the spec. A successful analysis moves the project to
status "analyzed"; scoring and allocation live in the next wave.
"""

import json
from datetime import datetime, time, timezone
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.models.base import utcnow
from app.repositories.providers import ProviderRepository
from app.schemas.projects import (
    AnalysisDraft,
    AnalysisList,
    AnalysisOut,
    AnalyzeIn,
    ProjectCreate,
    ProjectList,
    ProjectOut,
    ProjectPatch,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.ai.chat_types import ChatRequest, ChatTurn
from app.services.ai.registry import get_provider

ANALYST_SYSTEM_PROMPT = """Bạn là chuyên gia phân tích dự án phần mềm.
Nhiệm vụ: đọc yêu cầu dự án và chia thành các task có thể phân công
cho nhân viên hoặc AI.

Chỉ trả về MỘT object JSON duy nhất, không kèm giải thích, không bọc
markdown, đúng cấu trúc:
{
  "summary": "tóm tắt dự án và cách tiếp cận",
  "tasks": [
    {
      "title": "tên task",
      "description": "mô tả ngắn",
      "skills_required": ["kỹ năng"],
      "scopes": [],
      "estimated_hours": 8,
      "suggested_type": "either"
    }
  ],
  "risks": ["rủi ro"]
}

Quy tắc:
- Chia thành 5-15 task nguyên tử, mỗi task thực hiện độc lập được.
- skills_required: tên kỹ năng/công nghệ ngắn gọn, ví dụ "React",
  "PostgreSQL", "QA".
- scopes: phạm vi nhạy cảm mà task chạm tới, ví dụ "payment-data" cho
  thanh toán, "personal-data" cho dữ liệu cá nhân, "production-access"
  cho hệ thống đang chạy thật; để mảng rỗng nếu không có.
- suggested_type: "ai" nếu AI làm tốt độc lập, "human" nếu cần con
  người quyết định hoặc chịu trách nhiệm, "either" nếu cả hai đều
  phù hợp.
- estimated_hours: giờ công ước tính cho một người hoặc AI có kinh
  nghiệm vừa.
- Viết summary, title, description và risks bằng tiếng Việt."""


def parse_analysis(text: str) -> AnalysisDraft:
    """Tolerantly extract and strictly validate the model's JSON draft."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ProviderError("analysis_invalid_response")
    try:
        raw = json.loads(cleaned[start : end + 1])
        return AnalysisDraft.model_validate(raw)
    except (json.JSONDecodeError, ValidationError):
        raise ProviderError("analysis_invalid_response") from None


class ProjectService:
    def __init__(self, db, settings: Settings, chat_http: ChatHTTP | None = None):
        self.db = db
        self.providers = ProviderRepository(db)
        self.vault = CredentialVault(settings.credential_encryption_key)
        self.chat_http = chat_http

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _out(doc: dict) -> ProjectOut:
        deadline = doc.get("deadline")
        return ProjectOut(
            id=doc["_id"],
            name=doc["name"],
            description=doc["description"],
            tech_stack=doc.get("tech_stack", []),
            deadline=deadline.date() if isinstance(deadline, datetime) else deadline,
            status=doc["status"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    @staticmethod
    def _analysis_out(doc: dict) -> AnalysisOut:
        return AnalysisOut(
            id=doc["_id"],
            project_id=doc["project_id"],
            provider=doc["provider"],
            model=doc["model"],
            summary=doc["summary"],
            tasks=doc.get("tasks", []),
            risks=doc.get("risks", []),
            total_estimated_hours=doc.get("total_estimated_hours"),
            input_tokens=doc.get("input_tokens"),
            output_tokens=doc.get("output_tokens"),
            created_at=doc["created_at"],
        )

    async def _get_owned(self, user_id: UUID, project_id: UUID) -> dict:
        doc = await self.db.projects.find_one({"_id": project_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("project_not_found")
        return doc

    # --- CRUD ------------------------------------------------------------

    async def list(self, user_id: UUID) -> ProjectList:
        cursor = self.db.projects.find({"user_id": user_id}).sort("updated_at", -1)
        return ProjectList(projects=[self._out(doc) async for doc in cursor])

    async def create(self, user_id: UUID, payload: ProjectCreate) -> ProjectOut:
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "name": payload.name,
            "description": payload.description,
            "tech_stack": payload.tech_stack,
            "deadline": (
                datetime.combine(payload.deadline, time.min, tzinfo=timezone.utc)
                if payload.deadline
                else None
            ),
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        await self.db.projects.insert_one(doc)
        return self._out(doc)

    async def get(self, user_id: UUID, project_id: UUID) -> ProjectOut:
        return self._out(await self._get_owned(user_id, project_id))

    async def patch(
        self, user_id: UUID, project_id: UUID, payload: ProjectPatch
    ) -> ProjectOut:
        await self._get_owned(user_id, project_id)
        changes = payload.model_dump(exclude_unset=True)
        if "deadline" in changes:
            value = changes["deadline"]
            changes["deadline"] = (
                datetime.combine(value, time.min, tzinfo=timezone.utc) if value else None
            )
        changes["updated_at"] = utcnow()
        await self.db.projects.update_one(
            {"_id": project_id, "user_id": user_id}, {"$set": changes}
        )
        return self._out(await self._get_owned(user_id, project_id))

    async def delete(self, user_id: UUID, project_id: UUID) -> None:
        result = await self.db.projects.delete_one(
            {"_id": project_id, "user_id": user_id}
        )
        if result.deleted_count == 0:
            raise ProviderError("project_not_found")
        await self.db.project_analyses.delete_many(
            {"project_id": project_id, "user_id": user_id}
        )
        await self.db.allocations.delete_many(
            {"project_id": project_id, "user_id": user_id}
        )

    # --- Analysis ----------------------------------------------------------

    async def list_analyses(self, user_id: UUID, project_id: UUID) -> AnalysisList:
        await self._get_owned(user_id, project_id)
        cursor = self.db.project_analyses.find(
            {"project_id": project_id, "user_id": user_id}
        ).sort("created_at", -1)
        return AnalysisList(analyses=[self._analysis_out(doc) async for doc in cursor])

    async def analyze(
        self, user_id: UUID, project_id: UUID, payload: AnalyzeIn
    ) -> AnalysisOut:
        project = await self._get_owned(user_id, project_id)
        get_provider(payload.provider, require_implemented=True)
        credential = await self.providers.get(user_id, payload.provider)
        if credential is None:
            raise ProviderError("credentials_missing")
        if not credential.enabled:
            raise ProviderError("provider_disabled")
        model = await self.providers.get_model(credential.id, payload.model)
        if model is None:
            raise ProviderError("model_not_synced")
        if model.capabilities.get("chat") is False:
            raise ProviderError("model_not_chat_capable")
        key = self.vault.decrypt(credential.encrypted_api_key, user_id, payload.provider)

        deadline = project.get("deadline")
        deadline_text = (
            deadline.date().isoformat() if isinstance(deadline, datetime) else "chưa xác định"
        )
        stack_text = ", ".join(project.get("tech_stack") or []) or "chưa xác định"
        user_prompt = (
            f"Tên dự án: {project['name']}\n"
            f"Mô tả và yêu cầu:\n{project['description']}\n"
            f"Công nghệ dự kiến: {stack_text}\n"
            f"Deadline: {deadline_text}"
        )
        request = ChatRequest(
            model=payload.model,
            turns=(ChatTurn("user", user_prompt),),
            system_prompt=ANALYST_SYSTEM_PROMPT,
            temperature=0.2,
            max_output_tokens=4096,
        )
        adapter = create_provider(payload.provider, chat_http=self.chat_http)
        parts: list[str] = []
        input_tokens = output_tokens = None
        async for event in adapter.stream_chat(key, request):
            if event.kind == "delta":
                parts.append(event.text)
            elif event.kind == "usage":
                input_tokens = event.input_tokens or input_tokens
                output_tokens = event.output_tokens or output_tokens
        draft = parse_analysis("".join(parts))

        hours = [task.estimated_hours for task in draft.tasks]
        total = round(sum(h for h in hours if h is not None), 2) if any(
            h is not None for h in hours
        ) else None
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "project_id": project_id,
            "provider": payload.provider,
            "model": payload.model,
            "summary": draft.summary,
            "tasks": [task.model_dump() for task in draft.tasks],
            "risks": draft.risks,
            "total_estimated_hours": total,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "created_at": now,
        }
        await self.db.project_analyses.insert_one(doc)
        await self.db.projects.update_one(
            {"_id": project_id, "user_id": user_id},
            {"$set": {"status": "analyzed", "updated_at": now}},
        )
        return self._analysis_out(doc)
