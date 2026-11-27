"""Studio Projects — persistent source trees that Agents edit in place.

The create-project workflows generate a site from nothing and hand back
a ZIP at the end. This module is the counterpart the user asked for
(2026-11-27): import an EXISTING project (ZIP upload or a file list),
keep it as a living source tree in the database, and let several chosen
Agents work on it one after another — each Agent reads the current
files (including whatever the previous Agent just changed), answers
with a JSON edit set, and the edits are applied to the stored files
immediately, with a per-file change log attributing every write to the
Agent (or the user) who made it.

Storage is owner-scoped Mongo collections: ``studio_projects`` (one doc
per project with maintained counters), ``studio_project_files`` (one
doc per file), ``studio_project_runs`` (one doc per coordination run,
steps inline) and ``studio_project_changes`` (the audit log).

Runs are sequential on purpose: two Agents editing the same file at the
same time would silently overwrite each other, so Agent N+1 always sees
Agent N's applied result. A failed Agent (provider error or an answer
that is not a valid edit set) marks only its own step failed — the run
continues, mirroring the collaboration-room rule that one Agent failing
never fails the whole post.

Agent answers must be a single JSON object:
``{"summary": str, "files": [{"path", "action": "upsert"|"delete",
"content"}]}`` — full file contents, never patches, so an edit set can
always be applied without a merge step.
"""

import io
import json
import re
import zipfile
from uuid import UUID, uuid4

from app.models.base import utcnow
from app.schemas.agents import RunRequest
from app.schemas.studio_projects import (
    ChangeList,
    ChangeOut,
    FileContentOut,
    FileMetaOut,
    FileTreeOut,
    ProjectCreate,
    ProjectList,
    ProjectOut,
    ProjectPatch,
    RunCreateIn,
    RunListOut,
    RunOut,
    RunStepOut,
)
from app.services.agents import AgentService
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP

PROJECTS = "studio_projects"
FILES = "studio_project_files"
RUNS = "studio_project_runs"
CHANGES = "studio_project_changes"

MAX_FILES = 200
MAX_TOTAL_BYTES = 5 * 1024 * 1024
MAX_FILE_BYTES = 1 * 1024 * 1024
MAX_ZIP_BYTES = 10 * 1024 * 1024
# Directories that never belong in an editable source tree (dependency
# folders would blow the file cap and are never hand-edited).
SKIP_DIRS = {"node_modules", ".git", "__MACOSX", ".next", ".venv", "__pycache__"}
# How much file content one Agent prompt carries. The Agent Studio
# request budget is byte-based; ~15k chars of mostly-ASCII source plus
# the tree and instruction stays well inside STUDIO_TOKEN_BUDGET, and
# the RunRequest schema caps a prompt at 32k chars regardless.
CONTENT_BUDGET_CHARS = 15000
STUDIO_TOKEN_BUDGET = 65536
STUDIO_MAX_OUTPUT_TOKENS = 8192


def clean_path(raw: str) -> str:
    """Normalise a project-relative path or reject it.

    Backslashes become slashes; absolute paths, drive letters, ``.`` and
    ``..`` segments and control characters are refused so an imported or
    Agent-written file can never escape the project tree.
    """
    if not isinstance(raw, str):
        raise ProviderError("studio_invalid_path")
    text = raw.replace("\\", "/").strip()
    if not text or len(text) > 300 or ":" in text.split("/")[0]:
        raise ProviderError("studio_invalid_path")
    parts: list[str] = []
    for segment in text.split("/"):
        if segment in ("", "."):
            continue
        if segment == ".." or any(ord(ch) < 32 for ch in segment):
            raise ProviderError("studio_invalid_path")
        parts.append(segment)
    if not parts:
        raise ProviderError("studio_invalid_path")
    return "/".join(parts)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "project"


class StudioProjectService:
    def __init__(self, db, settings, chat_http: ChatHTTP | None = None):
        self.db = db
        self.settings = settings
        self.chat_http = chat_http
        self.projects = db[PROJECTS]
        self.files = db[FILES]
        self.runs = db[RUNS]
        self.changes = db[CHANGES]

    # --- helpers -------------------------------------------------------------
    async def _require_project(self, user_id: UUID, project_id: UUID) -> dict:
        doc = await self.projects.find_one({"_id": project_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("studio_project_not_found")
        return doc

    @staticmethod
    def _project_out(doc: dict) -> ProjectOut:
        return ProjectOut(
            id=doc["_id"],
            name=doc["name"],
            file_count=doc.get("file_count", 0),
            total_bytes=doc.get("total_bytes", 0),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    async def _recount(self, project_id: UUID) -> None:
        docs = await self.files.find({"project_id": project_id}).to_list(
            length=MAX_FILES + 1
        )
        await self.projects.update_one(
            {"_id": project_id},
            {
                "$set": {
                    "file_count": len(docs),
                    "total_bytes": sum(d.get("size", 0) for d in docs),
                    "updated_at": utcnow(),
                }
            },
        )

    async def _store_file(
        self,
        project_id: UUID,
        path: str,
        content: str,
        *,
        source: str,
        run_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_name: str | None = None,
    ) -> str:
        """Upsert one file and log the change. Returns the action taken."""
        data = content.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ProviderError("studio_project_too_large")
        existing = await self.files.find_one(
            {"project_id": project_id, "path": path}
        )
        if existing is None:
            count = await self.files.count_documents({"project_id": project_id})
            if count >= MAX_FILES:
                raise ProviderError("studio_project_too_large")
        now = utcnow()
        await self.files.update_one(
            {"project_id": project_id, "path": path},
            {
                "$set": {
                    "content": content,
                    "size": len(data),
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "_id": uuid4(),
                    "project_id": project_id,
                    "path": path,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        action = "updated" if existing is not None else "created"
        await self._log_change(
            project_id, path, action, source,
            run_id=run_id, agent_id=agent_id, agent_name=agent_name,
        )
        return action

    async def _delete_file_doc(
        self,
        project_id: UUID,
        path: str,
        *,
        source: str,
        run_id: UUID | None = None,
        agent_id: UUID | None = None,
        agent_name: str | None = None,
    ) -> bool:
        result = await self.files.delete_one(
            {"project_id": project_id, "path": path}
        )
        if result.deleted_count:
            await self._log_change(
                project_id, path, "deleted", source,
                run_id=run_id, agent_id=agent_id, agent_name=agent_name,
            )
            return True
        return False

    async def _log_change(
        self, project_id, path, action, source, *, run_id=None,
        agent_id=None, agent_name=None,
    ) -> None:
        await self.changes.insert_one(
            {
                "_id": uuid4(),
                "project_id": project_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "path": path,
                "action": action,
                "source": source,
                "created_at": utcnow(),
            }
        )

    # --- projects --------------------------------------------------------------
    async def create_project(self, user_id: UUID, payload: ProjectCreate) -> ProjectOut:
        cleaned: list[tuple[str, str]] = []
        seen: set[str] = set()
        total = 0
        for item in payload.files:
            path = clean_path(item.path)
            if path in seen:
                continue
            seen.add(path)
            size = len(item.content.encode("utf-8"))
            if size > MAX_FILE_BYTES:
                raise ProviderError("studio_project_too_large")
            total += size
            cleaned.append((path, item.content))
        if len(cleaned) > MAX_FILES or total > MAX_TOTAL_BYTES:
            raise ProviderError("studio_project_too_large")
        now = utcnow()
        project_id = uuid4()
        doc = {
            "_id": project_id,
            "user_id": user_id,
            "name": payload.name,
            "file_count": 0,
            "total_bytes": 0,
            "created_at": now,
            "updated_at": now,
        }
        await self.projects.insert_one(doc)
        for path, content in cleaned:
            await self._store_file(project_id, path, content, source="user")
        await self._recount(project_id)
        return self._project_out(await self._require_project(user_id, project_id))

    async def import_zip(self, user_id: UUID, name: str | None, data: bytes) -> ProjectOut:
        if len(data) > MAX_ZIP_BYTES:
            raise ProviderError("studio_project_too_large")
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise ProviderError("studio_zip_invalid") from None
        files: list[tuple[str, str]] = []
        total = 0
        for info in archive.infolist():
            if info.is_dir():
                continue
            raw_path = info.filename
            segments = [s for s in raw_path.replace("\\", "/").split("/") if s]
            if any(seg in SKIP_DIRS for seg in segments[:-1]):
                continue
            try:
                path = clean_path(raw_path)
            except ProviderError:
                continue
            if len(files) >= MAX_FILES:
                break
            raw = archive.read(info)
            if len(raw) > MAX_FILE_BYTES:
                continue
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue  # binary asset — not editable source
            total += len(raw)
            if total > MAX_TOTAL_BYTES:
                raise ProviderError("studio_project_too_large")
            files.append((path, content))
        if not files:
            raise ProviderError("studio_zip_empty")
        project_name = (name or "").strip()
        if not project_name:
            base = archive.filename or "project"
            project_name = base.rsplit(".", 1)[0].split("/")[-1] or "project"
        return await self.create_project(
            user_id,
            ProjectCreate(
                name=project_name[:120],
                files=[{"path": p, "content": c} for p, c in files],
            ),
        )

    async def list_projects(self, user_id: UUID) -> ProjectList:
        docs = (
            await self.projects.find({"user_id": user_id})
            .sort("updated_at", -1)
            .to_list(length=100)
        )
        return ProjectList(projects=[self._project_out(d) for d in docs])

    async def get_project(self, user_id: UUID, project_id: UUID) -> ProjectOut:
        return self._project_out(await self._require_project(user_id, project_id))

    async def patch_project(
        self, user_id: UUID, project_id: UUID, payload: ProjectPatch
    ) -> ProjectOut:
        await self._require_project(user_id, project_id)
        if payload.name is not None:
            await self.projects.update_one(
                {"_id": project_id},
                {"$set": {"name": payload.name, "updated_at": utcnow()}},
            )
        return self._project_out(await self._require_project(user_id, project_id))

    async def delete_project(self, user_id: UUID, project_id: UUID) -> None:
        await self._require_project(user_id, project_id)
        await self.files.delete_many({"project_id": project_id})
        await self.runs.delete_many({"project_id": project_id})
        await self.changes.delete_many({"project_id": project_id})
        await self.projects.delete_one({"_id": project_id})

    # --- files -----------------------------------------------------------------
    async def list_files(self, user_id: UUID, project_id: UUID) -> FileTreeOut:
        await self._require_project(user_id, project_id)
        docs = (
            await self.files.find({"project_id": project_id})
            .sort("path", 1)
            .to_list(length=MAX_FILES)
        )
        return FileTreeOut(
            files=[
                FileMetaOut(path=d["path"], size=d["size"], updated_at=d["updated_at"])
                for d in docs
            ]
        )

    async def _require_file(self, project_id: UUID, path: str) -> dict:
        doc = await self.files.find_one({"project_id": project_id, "path": path})
        if doc is None:
            raise ProviderError("studio_file_not_found")
        return doc

    async def get_file(
        self, user_id: UUID, project_id: UUID, raw_path: str
    ) -> FileContentOut:
        await self._require_project(user_id, project_id)
        doc = await self._require_file(project_id, clean_path(raw_path))
        return FileContentOut(
            path=doc["path"],
            content=doc["content"],
            size=doc["size"],
            updated_at=doc["updated_at"],
        )

    async def upsert_file(
        self, user_id: UUID, project_id: UUID, raw_path: str, content: str
    ) -> FileContentOut:
        await self._require_project(user_id, project_id)
        path = clean_path(raw_path)
        await self._store_file(project_id, path, content, source="user")
        await self._recount(project_id)
        doc = await self._require_file(project_id, path)
        return FileContentOut(
            path=doc["path"],
            content=doc["content"],
            size=doc["size"],
            updated_at=doc["updated_at"],
        )

    async def delete_file(
        self, user_id: UUID, project_id: UUID, raw_path: str
    ) -> None:
        await self._require_project(user_id, project_id)
        path = clean_path(raw_path)
        await self._require_file(project_id, path)
        await self._delete_file_doc(project_id, path, source="user")
        await self._recount(project_id)

    async def export_zip(self, user_id: UUID, project_id: UUID) -> tuple[bytes, str]:
        project = await self._require_project(user_id, project_id)
        docs = (
            await self.files.find({"project_id": project_id})
            .sort("path", 1)
            .to_list(length=MAX_FILES)
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for doc in docs:
                archive.writestr(doc["path"], doc["content"])
        return buffer.getvalue(), f"{_slug(project['name'])}.zip"

    async def list_changes(
        self, user_id: UUID, project_id: UUID
    ) -> ChangeList:
        await self._require_project(user_id, project_id)
        docs = (
            await self.changes.find({"project_id": project_id})
            .sort("created_at", -1)
            .to_list(length=100)
        )
        return ChangeList(
            changes=[
                ChangeOut(
                    id=d["_id"],
                    run_id=d.get("run_id"),
                    agent_id=d.get("agent_id"),
                    agent_name=d.get("agent_name"),
                    path=d["path"],
                    action=d["action"],
                    source=d["source"],
                    created_at=d["created_at"],
                )
                for d in docs
            ]
        )

    # --- coordination runs -------------------------------------------------------
    async def _run_agent(self, user_id: UUID, agent_id: UUID, prompt: str) -> dict:
        service = AgentService(self.db, self.settings, self.chat_http)
        prepared = await service.prepare_run(
            user_id,
            agent_id,
            RunRequest(prompt=prompt),
            token_budget_override=STUDIO_TOKEN_BUDGET,
            max_output_tokens_override=STUDIO_MAX_OUTPUT_TOKENS,
        )
        result: dict = {}
        async for event in service.stream_prepared(prepared):
            if event["event"] == "done":
                result = event["data"]["execution"]
        return result

    @staticmethod
    def _parse_edit_set(text: str) -> dict:
        """Extract the Agent's JSON edit set, tolerating code fences and
        surrounding prose (same rescue style as the workflow JSON fix)."""
        candidate = (text or "").strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
        if fence:
            candidate = fence.group(1)
        else:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end <= start:
                raise ValueError("no JSON object in agent reply")
            candidate = candidate[start : end + 1]
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict) or not isinstance(
            parsed.get("files", []), list
        ):
            raise ValueError("edit set must be an object with a files list")
        return parsed

    async def _build_prompt(
        self, project: dict, instruction: str, changes_so_far: list[str]
    ) -> str:
        docs = (
            await self.files.find({"project_id": project["_id"]})
            .sort("path", 1)
            .to_list(length=MAX_FILES)
        )
        tree = "\n".join(f"- {d['path']} ({d['size']} bytes)" for d in docs)
        blocks: list[str] = []
        used = 0
        omitted: list[str] = []
        for doc in docs:
            block = f"===== {doc['path']} =====\n{doc['content']}\n"
            if used + len(block) > CONTENT_BUDGET_CHARS:
                omitted.append(doc["path"])
                continue
            blocks.append(block)
            used += len(block)
        parts = [
            f"Bạn đang làm việc TRỰC TIẾP trên source code của project "
            f"\"{project['name']}\". Các Agent khác cùng làm project này; "
            "Agent trước bạn đã sửa xong và bạn đang đọc bản MỚI NHẤT.",
            f"Nhiệm vụ từ người dùng:\n{instruction}",
        ]
        if changes_so_far:
            parts.append(
                "Thay đổi đã áp dụng trong lượt chạy này:\n"
                + "\n".join(f"- {line}" for line in changes_so_far)
            )
        parts.append(f"Cây file hiện tại:\n{tree or '(chưa có file nào)'}")
        if blocks:
            parts.append("Nội dung file hiện tại:\n" + "\n".join(blocks))
        if omitted:
            parts.append(
                "Các file sau KHÔNG kèm nội dung do giới hạn độ dài — đừng sửa "
                "chúng trừ khi tạo mới hoàn toàn: " + ", ".join(omitted)
            )
        parts.append(
            "QUY TẮC TRẢ LỜI — chỉ trả về DUY NHẤT một khối ```json đúng cấu trúc:\n"
            '{"summary": "tóm tắt việc bạn đã làm", "files": [{"path": '
            '"đường/dẫn/file", "action": "upsert", "content": "TOÀN BỘ nội '
            'dung file sau khi sửa"}, {"path": "file/cần/xoá", "action": '
            '"delete"}]}\n'
            "- content phải là toàn bộ nội dung file, không viết tắt, không "
            "placeholder, không dùng patch.\n"
            "- Chỉ liệt kê file bạn thực sự thay đổi; không cần sửa thì để "
            "files là mảng rỗng.\n"
            "- Làm trọn phần việc của mình: Agent sau sẽ dựa trên bản bạn vừa sửa."
        )
        return "\n\n".join(parts)

    async def _apply_edit_set(
        self, project_id: UUID, run_id: UUID, agent, edit_set: dict
    ) -> tuple[list[str], list[str]]:
        """Apply one Agent's edits. Returns (changed paths, notes)."""
        changed: list[str] = []
        notes: list[str] = []
        for entry in edit_set.get("files", []):
            if not isinstance(entry, dict):
                continue
            try:
                path = clean_path(str(entry.get("path", "")))
            except ProviderError:
                notes.append(f"bỏ qua path không hợp lệ: {entry.get('path')!r}")
                continue
            action = entry.get("action", "upsert")
            try:
                if action == "delete":
                    if await self._delete_file_doc(
                        project_id, path, source="agent", run_id=run_id,
                        agent_id=agent.id, agent_name=agent.name,
                    ):
                        changed.append(path)
                else:
                    content = entry.get("content")
                    if not isinstance(content, str):
                        notes.append(f"bỏ qua {path}: thiếu content")
                        continue
                    await self._store_file(
                        project_id, path, content, source="agent",
                        run_id=run_id, agent_id=agent.id, agent_name=agent.name,
                    )
                    changed.append(path)
            except ProviderError as error:
                notes.append(f"bỏ qua {path}: {error.code}")
        return changed, notes

    async def run_agents(
        self, user_id: UUID, project_id: UUID, payload: RunCreateIn
    ) -> RunOut:
        project = await self._require_project(user_id, project_id)
        agent_service = AgentService(self.db, self.settings, self.chat_http)
        agents = []
        for agent_id in dict.fromkeys(payload.agent_ids):
            agents.append(await agent_service.get_agent(user_id, agent_id))

        run_id = uuid4()
        now = utcnow()
        run_doc = {
            "_id": run_id,
            "project_id": project_id,
            "user_id": user_id,
            "instruction": payload.instruction,
            "status": "running",
            "steps": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "created_at": now,
            "finished_at": None,
        }
        await self.runs.insert_one(run_doc)

        steps: list[RunStepOut] = []
        changes_so_far: list[str] = []
        total_in = 0
        total_out = 0
        for agent in agents:
            step = RunStepOut(
                agent_id=agent.id, agent_name=agent.name, status="failed"
            )
            prompt = await self._build_prompt(
                project, payload.instruction, changes_so_far
            )
            try:
                execution = await self._run_agent(user_id, agent.id, prompt)
            except ProviderError as error:
                step.error_code = error.code
                steps.append(step)
                continue
            step.input_tokens = execution.get("input_tokens")
            step.output_tokens = execution.get("output_tokens")
            total_in += execution.get("input_tokens") or 0
            total_out += execution.get("output_tokens") or 0
            if (execution.get("status") or "") != "success":
                step.error_code = execution.get("error_code") or "generation_failed"
                steps.append(step)
                continue
            try:
                edit_set = self._parse_edit_set(execution.get("content") or "")
            except (ValueError, json.JSONDecodeError):
                step.error_code = "studio_invalid_agent_output"
                steps.append(step)
                continue
            changed, notes = await self._apply_edit_set(
                project_id, run_id, agent, edit_set
            )
            summary = str(edit_set.get("summary") or "")[:500]
            if notes:
                summary = (summary + " | " if summary else "") + "; ".join(notes)
            step.status = "completed"
            step.summary = summary[:500]
            step.files_changed = changed
            steps.append(step)
            if changed:
                changes_so_far.append(
                    f"{agent.name} đã sửa: {', '.join(changed)}"
                    + (f" — {summary}" if summary else "")
                )
        await self._recount(project_id)
        finished = utcnow()
        await self.runs.update_one(
            {"_id": run_id},
            {
                "$set": {
                    "status": "completed",
                    "steps": [s.model_dump(mode="json") for s in steps],
                    "total_input_tokens": total_in,
                    "total_output_tokens": total_out,
                    "finished_at": finished,
                }
            },
        )
        run_doc.update(
            {
                "status": "completed",
                "steps": steps,
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "finished_at": finished,
            }
        )
        return self._run_out(run_doc)

    @staticmethod
    def _run_out(doc: dict) -> RunOut:
        steps = [
            s if isinstance(s, RunStepOut) else RunStepOut(**s)
            for s in doc.get("steps", [])
        ]
        return RunOut(
            id=doc["_id"],
            project_id=doc["project_id"],
            instruction=doc["instruction"],
            status=doc["status"],
            steps=steps,
            total_input_tokens=doc.get("total_input_tokens", 0),
            total_output_tokens=doc.get("total_output_tokens", 0),
            created_at=doc["created_at"],
            finished_at=doc.get("finished_at"),
        )

    async def list_runs(self, user_id: UUID, project_id: UUID) -> RunListOut:
        await self._require_project(user_id, project_id)
        docs = (
            await self.runs.find({"project_id": project_id})
            .sort("created_at", -1)
            .to_list(length=50)
        )
        return RunListOut(runs=[self._run_out(d) for d in docs])
