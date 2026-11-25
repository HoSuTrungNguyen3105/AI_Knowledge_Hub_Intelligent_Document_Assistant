"""Codebase Architecture Analyzer storage (PROJECT_SPEC.md).

Two collections: `code_projects` (metadata + the prebuilt diagram
payload, so the UI renders instantly) and `code_project_files` (one
document per analyzed file: static imports, reverse dependencies, and
the AI summary/role filled in by the direct AI pass (the caller's own
provider), by the optional n8n callback, or by the demo seed).
Access is owner-scoped, except projects flagged `is_public_demo`,
which every signed-in user may open read-only.
"""

import asyncio
import logging
import time
from uuid import UUID, uuid4

from app.core.credential_vault import CredentialVault
from app.models.base import utcnow
from app.repositories.chat import ChatRepository
from app.repositories.providers import ProviderRepository
from app.schemas.code_analyzer import (
    CodeCallbackIn,
    CodeCallbackOut,
    CodeFileDetail,
    CodeFileSummary,
    CodeProjectDetail,
    CodeProjectSummary,
    SeedDemoOut,
    UploadOut,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.ai.chat_types import ChatRequest, ChatTurn
from app.services.ai.registry import PROVIDERS
from app.services.code_parser import MAX_ZIP_BYTES, parse_codebase
from app.services.synthesis import require_chat_target

PROJECTS = "code_projects"
FILES = "code_project_files"
CLUSTER_THRESHOLD = 50
AI_EXCERPT_CHARS = 2500
REPORT_FILE_LIMIT = 400
REPORT_EXCERPT_FILES = 20
REPORT_EXCERPT_CHARS = 1800
REPORT_TIMEOUT_SECONDS = 240
# Output-token ladder for the report call: start generous for models
# with large context windows, then step down so small-context models
# (e.g. a 4K-context model asked for 8192 output tokens is rejected
# outright by the provider) still get a report that fits.
REPORT_TOKEN_LADDER = (8192, 4096, 2048, 1024)

logger = logging.getLogger(__name__)


def module_group_of(file_path: str) -> str:
    """The module group of a file is its parent folder (root when none)."""
    if "/" not in file_path:
        return "root"
    return file_path.rsplit("/", 1)[0] or "root"


def build_diagram(files: list[dict]) -> dict:
    """Prebuild the graph payload for the 3-pane UI.

    Small projects render one node per file. Above CLUSTER_THRESHOLD
    files the graph collapses into one node per module group with
    aggregated edges; the UI expands a cluster on demand using the
    file list of the project detail.
    """
    edges = []
    for f in files:
        for imp in f.get("imports", []):
            if imp.get("target_id"):
                edges.append(
                    {
                        "source": str(f["id"]),
                        "target": str(imp["target_id"]),
                        "label": imp.get("relation_label", ""),
                    }
                )
    if len(files) <= CLUSTER_THRESHOLD:
        nodes = [
            {
                "id": str(f["id"]),
                "label": f["file_name"],
                "group": f.get("module_group", ""),
                "role_tag": f.get("role_tag", ""),
                "kind": "file",
            }
            for f in files
        ]
        return {"mode": "files", "nodes": nodes, "edges": edges}
    groups: dict[str, list[dict]] = {}
    for f in files:
        groups.setdefault(f.get("module_group", ""), []).append(f)
    group_of = {str(f["id"]): f.get("module_group", "") for f in files}
    nodes = [
        {
            "id": f"cluster:{group}",
            "label": group,
            "kind": "cluster",
            "file_count": len(members),
            "file_ids": [str(m["id"]) for m in members],
        }
        for group, members in sorted(groups.items())
    ]
    aggregated: dict[tuple[str, str], int] = {}
    for edge in edges:
        key = (group_of.get(edge["source"], ""), group_of.get(edge["target"], ""))
        if key[0] and key[1] and key[0] != key[1]:
            aggregated[key] = aggregated.get(key, 0) + 1
    cluster_edges = [
        {
            "source": f"cluster:{source}",
            "target": f"cluster:{target}",
            "label": f"{count} liên kết",
            "count": count,
        }
        for (source, target), count in sorted(aggregated.items())
    ]
    return {
        "mode": "clusters",
        "nodes": nodes,
        "edges": cluster_edges,
        # Full file-level edges so the UI can expand one cluster without
        # another round trip.
        "file_edges": edges,
    }


# A tiny Express-style codebase so a brand-new user can open the module
# and immediately see a real graph, tree and AI insights (spec section 3).
DEMO_FILES: list[dict] = [
    {
        "file_path": "src/app.js", "language": "javascript",
        "role_tag": "Entry Point",
        "ai_summary": "Điểm khởi động của server: kết nối cơ sở dữ liệu, "
        "gắn các route và lắng nghe cổng HTTP.",
        "imports": [
            ("src/config/db.js", "Kết nối MongoDB khi khởi động"),
            ("src/routes/tasks.js", "Gắn route /tasks"),
            ("src/routes/users.js", "Gắn route /users"),
        ],
    },
    {
        "file_path": "src/config/db.js", "language": "javascript",
        "role_tag": "Config",
        "ai_summary": "Cấu hình kết nối MongoDB dùng chung cho toàn bộ "
        "tầng service.",
        "imports": [],
    },
    {
        "file_path": "src/routes/tasks.js", "language": "javascript",
        "role_tag": "Router",
        "ai_summary": "Khai báo các endpoint REST của tài nguyên task và "
        "chuyển request tới controller sau khi qua middleware xác thực.",
        "imports": [
            ("src/controllers/taskController.js", "Chuyển request tới controller"),
            ("src/middleware/auth.js", "Bảo vệ route bằng JWT"),
        ],
    },
    {
        "file_path": "src/routes/users.js", "language": "javascript",
        "role_tag": "Router",
        "ai_summary": "Khai báo các endpoint đăng ký, đăng nhập và hồ sơ "
        "người dùng.",
        "imports": [
            ("src/controllers/userController.js", "Chuyển request tới controller"),
            ("src/middleware/auth.js", "Bảo vệ route bằng JWT"),
        ],
    },
    {
        "file_path": "src/controllers/taskController.js",
        "language": "javascript", "role_tag": "Controller",
        "ai_summary": "Nhận request, kiểm tra dữ liệu đầu vào rồi gọi "
        "taskService và trả JSON về cho client.",
        "imports": [
            ("src/services/taskService.js", "Gọi logic nghiệp vụ task"),
            ("src/utils/validate.js", "Kiểm tra dữ liệu đầu vào"),
        ],
    },
    {
        "file_path": "src/controllers/userController.js",
        "language": "javascript", "role_tag": "Controller",
        "ai_summary": "Xử lý đăng ký, đăng nhập và hồ sơ người dùng, uỷ "
        "thác nghiệp vụ cho userService.",
        "imports": [
            ("src/services/userService.js", "Gọi logic nghiệp vụ người dùng"),
            ("src/utils/validate.js", "Kiểm tra dữ liệu đầu vào"),
        ],
    },
    {
        "file_path": "src/services/taskService.js", "language": "javascript",
        "role_tag": "Service",
        "ai_summary": "Logic nghiệp vụ của task: tạo, phân công, đổi trạng "
        "thái và truy vấn danh sách theo bộ lọc.",
        "imports": [
            ("src/models/Task.js", "Truy vấn collection tasks"),
            ("src/config/db.js", "Dùng kết nối cơ sở dữ liệu"),
        ],
    },
    {
        "file_path": "src/services/userService.js", "language": "javascript",
        "role_tag": "Service",
        "ai_summary": "Logic nghiệp vụ người dùng: tạo tài khoản, kiểm tra "
        "thông tin đăng nhập và chuẩn hoá hồ sơ.",
        "imports": [
            ("src/models/User.js", "Truy vấn collection users"),
            ("src/utils/validate.js", "Chuẩn hoá email và mật khẩu"),
        ],
    },
    {
        "file_path": "src/models/Task.js", "language": "javascript",
        "role_tag": "Model",
        "ai_summary": "Schema của task: tiêu đề, người phụ trách, trạng "
        "thái và hạn hoàn thành.",
        "imports": [],
    },
    {
        "file_path": "src/models/User.js", "language": "javascript",
        "role_tag": "Model",
        "ai_summary": "Schema của người dùng: email, mật khẩu đã băm và "
        "vai trò.",
        "imports": [],
    },
    {
        "file_path": "src/middleware/auth.js", "language": "javascript",
        "role_tag": "Middleware",
        "ai_summary": "Middleware xác thực JWT: chặn request thiếu hoặc "
        "sai token trước khi vào route được bảo vệ.",
        "imports": [
            ("src/utils/validate.js", "Kiểm tra định dạng token"),
        ],
    },
    {
        "file_path": "src/utils/validate.js", "language": "javascript",
        "role_tag": "Util",
        "ai_summary": "Các hàm kiểm tra dữ liệu dùng chung: email, độ dài "
        "mật khẩu và định dạng token.",
        "imports": [],
    },
]



def _report_prompt(project_name: str, docs: list[dict], contents: dict) -> str:
    # One prompt for the whole project: a compact inventory of every
    # file plus content excerpts of the most-connected ones. The model
    # answers with a single long Markdown document whose centerpiece
    # maps each page / feature to the exact files that build it.
    ranked = sorted(
        docs, key=lambda d: (-len(d.get("imported_by") or []), d["file_path"])
    )
    lines = [
        "Bạn là chuyên gia phân tích kiến trúc phần mềm. Dưới đây là bản "
        "kê toàn bộ file của một codebase kèm trích đoạn nội dung của "
        "các file quan trọng nhất.",
        "Hãy viết MỘT tài liệu Markdown hoàn chỉnh bằng tiếng Việt theo "
        "đúng cấu trúc sau:",
        f"# Báo cáo phân tích codebase: {project_name}",
        "## 1. Tổng quan — mục đích dự án, công nghệ/framework suy ra "
        "từ danh sách file, entry point và cách ứng dụng khởi chạy.",
        "## 2. Cấu trúc thư mục — từng thư mục chứa gì và phụ trách "
        "phần nào của hệ thống.",
        "## 3. Ánh xạ trang & tính năng → file — PHẦN QUAN TRỌNG NHẤT: "
        "với mỗi trang màn hình / tính năng / route tìm được, liệt kê "
        "chính xác các file tạo nên nó (file trang, các component con, "
        "service/API, state, style...), mỗi file kèm một câu mô tả vai "
        "trò của nó trong trang/tính năng đó. Nếu dự án không có khái "
        "niệm trang thì nhóm theo tính năng hoặc module.",
        "## 4. Chi tiết từng file — bảng Markdown 4 cột: File | Vai "
        "trò | Mô tả | File liên quan chính. Liệt kê toàn bộ file trong "
        "bản kê.",
        "## 5. Luồng hoạt động chính — đi từ entry point qua những "
        "file nào để xử lý một yêu cầu điển hình.",
        "## 6. Nhận xét — file trung tâm, điểm đáng chú ý, rủi ro nếu thấy.",
        "Chỉ dựa trên dữ liệu được cung cấp, tuyệt đối không bịa ra "
        "file không có trong bản kê. Trả về DUY NHẤT nội dung Markdown, "
        "không bọc trong khối ```.",
        "",
        "=== BẢN KÊ FILE ===",
    ]
    for doc in ranked[:REPORT_FILE_LIMIT]:
        targets = [imp["target_file"] for imp in doc.get("imports", [])]
        lines.append(
            f"- {doc['file_path']} | {doc['language']} | vai trò tĩnh: "
            f"{doc['role_tag']} | imports: "
            f"{', '.join(targets) if targets else '—'} | được import bởi: "
            f"{len(doc.get('imported_by') or [])} file"
        )
    if len(ranked) > REPORT_FILE_LIMIT:
        lines.append(
            f"- ... và {len(ranked) - REPORT_FILE_LIMIT} file khác "
            "(chỉ nêu trong mục 2/3 nếu liên quan, không liệt kê ở mục 4)"
        )
    lines.append("")
    lines.append("=== TRÍCH ĐOẠN CÁC FILE QUAN TRỌNG NHẤT ===")
    for doc in ranked[:REPORT_EXCERPT_FILES]:
        excerpt = contents.get(doc["file_path"], "")
        if not excerpt:
            continue
        lines.append(f"--- FILE: {doc['file_path']} ---")
        lines.append(excerpt[:REPORT_EXCERPT_CHARS])
        lines.append("")
    return "\n".join(lines)


def _clean_markdown(text: str) -> str:
    # Models sometimes wrap the document in a ``` fence despite being
    # told not to; strip one outer fence so the UI renders it raw.
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()


class CodeAnalyzerService:
    def __init__(self, db, settings, chat_http: ChatHTTP | None = None):
        self.db = db
        self.settings = settings
        self.chat_http = chat_http
        self.providers = ProviderRepository(db)
        self.requests = ChatRepository(db)
        self.vault = CredentialVault(settings.credential_encryption_key)

    # --- mapping helpers ---------------------------------------------------
    @staticmethod
    def _summary(doc: dict) -> CodeProjectSummary:
        return CodeProjectSummary(
            id=doc["_id"],
            name=doc["name"],
            description=doc.get("description", ""),
            is_public_demo=bool(doc.get("is_public_demo")),
            status=doc.get("status", "PROCESSING"),
            has_report=bool(doc.get("report_markdown")),
            stats=doc.get("stats") or {},
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    @staticmethod
    def _file_summary(doc: dict) -> CodeFileSummary:
        return CodeFileSummary(
            id=doc["_id"],
            file_path=doc["file_path"],
            file_name=doc["file_name"],
            module_group=doc.get("module_group", ""),
            language=doc.get("language", ""),
            role_tag=doc.get("role_tag", ""),
            import_count=len(doc.get("imports", [])),
            imported_by_count=len(doc.get("imported_by", [])),
            ai_summary=doc.get("ai_summary", ""),
            imports=doc.get("imports") or [],
            imported_by=doc.get("imported_by") or [],
        )

    async def _require_project(self, user_id: UUID, project_id: UUID) -> dict:
        doc = await self.db[PROJECTS].find_one({"_id": project_id})
        if doc is None or (
            doc.get("user_id") != str(user_id) and not doc.get("is_public_demo")
        ):
            raise ProviderError("code_project_not_found")
        return doc

    # --- reads ----------------------------------------------------------------
    async def list_projects(self, user_id: UUID) -> list[CodeProjectSummary]:
        cursor = (
            self.db[PROJECTS]
            .find(
                {
                    "$or": [
                        {"user_id": str(user_id)},
                        {"is_public_demo": True},
                    ]
                }
            )
            .sort("updated_at", -1)
        )
        return [self._summary(doc) async for doc in cursor]

    async def get_project(
        self, user_id: UUID, project_id: UUID
    ) -> CodeProjectDetail:
        doc = await self._require_project(user_id, project_id)
        cursor = (
            self.db[FILES]
            .find({"project_id": str(project_id)})
            .sort("file_path", 1)
        )
        files = [self._file_summary(f) async for f in cursor]
        summary = self._summary(doc)
        return CodeProjectDetail(
            **summary.model_dump(),
            diagram_data=doc.get("diagram_data") or {},
            files=files,
            report_markdown=doc.get("report_markdown") or "",
        )

    async def get_file(
        self, user_id: UUID, project_id: UUID, file_id: UUID
    ) -> CodeFileDetail:
        await self._require_project(user_id, project_id)
        doc = await self.db[FILES].find_one(
            {"_id": file_id, "project_id": str(project_id)}
        )
        if doc is None:
            raise ProviderError("code_file_not_found")
        return CodeFileDetail(
            id=doc["_id"],
            project_id=project_id,
            file_path=doc["file_path"],
            file_name=doc["file_name"],
            module_group=doc.get("module_group", ""),
            language=doc.get("language", ""),
            ai_summary=doc.get("ai_summary", ""),
            role_tag=doc.get("role_tag", ""),
            imports=doc.get("imports") or [],
            imported_by=doc.get("imported_by") or [],
        )

    # --- demo seed --------------------------------------------------------------
    async def seed_demo(self, user_id: UUID) -> SeedDemoOut:
        if self.settings.app_env not in {"development", "demo"}:
            raise ProviderError("seed_disabled")
        existing = await self.db[PROJECTS].find_one({"is_public_demo": True})
        if existing is not None:
            return SeedDemoOut(created=False, project=self._summary(existing))
        now = utcnow()
        project_id = uuid4()
        ids = {spec["file_path"]: uuid4() for spec in DEMO_FILES}
        docs = []
        for spec in DEMO_FILES:
            imports = [
                {
                    "target_file": target,
                    "target_id": str(ids[target]),
                    "relation_label": label,
                }
                for target, label in spec["imports"]
            ]
            docs.append(
                {
                    "_id": ids[spec["file_path"]],
                    "project_id": str(project_id),
                    "file_path": spec["file_path"],
                    "file_name": spec["file_path"].rsplit("/", 1)[-1],
                    "module_group": module_group_of(spec["file_path"]),
                    "language": spec["language"],
                    "ai_summary": spec["ai_summary"],
                    "role_tag": spec["role_tag"],
                    "imports": imports,
                    "imported_by": [],
                    "created_at": now,
                    "updated_at": now,
                }
            )
        by_path = {d["file_path"]: d for d in docs}
        for doc in docs:
            for imp in doc["imports"]:
                by_path[imp["target_file"]]["imported_by"].append(doc["file_path"])
        diagram = build_diagram(
            [
                {
                    "id": str(d["_id"]),
                    "file_name": d["file_name"],
                    "module_group": d["module_group"],
                    "role_tag": d["role_tag"],
                    "imports": d["imports"],
                }
                for d in docs
            ]
        )
        project = {
            "_id": project_id,
            "user_id": str(user_id),
            "name": "Dự án mẫu — Task API",
            "description": "Codebase mẫu (Express + MongoDB) để xem thử sơ "
            "đồ kiến trúc, cây thư mục và AI Insight ngay khi mới vào.",
            "is_public_demo": True,
            "status": "COMPLETED",
            "stats": {
                "total_raw_files": len(docs),
                "analyzed_files": len(docs),
                "primary_language": "javascript",
            },
            "diagram_data": diagram,
            "created_at": now,
            "updated_at": now,
        }
        await self.db[PROJECTS].insert_one(project)
        if docs:
            await self.db[FILES].insert_many(docs)
        return SeedDemoOut(created=True, project=self._summary(project))

    # --- upload + n8n analysis ------------------------------------------------
    async def ingest_upload(
        self,
        user_id: UUID,
        filename: str,
        data: bytes,
        provider: str | None = None,
        model: str | None = None,
    ) -> UploadOut:
        if len(data) > MAX_ZIP_BYTES:
            raise ProviderError("code_upload_too_large")
        if not data.startswith(b"PK"):
            raise ProviderError("code_upload_invalid")
        parsed = parse_codebase(data)
        if parsed["total_raw_files"] == 0:
            raise ProviderError("code_upload_invalid")
        files = parsed["files"]
        if not files:
            raise ProviderError("code_upload_empty")
        prepared = await self._prepare_ai(user_id, provider, model)
        now = utcnow()
        project_id = uuid4()
        ids = {f["file_path"]: uuid4() for f in files}
        docs = []
        for f in files:
            docs.append(
                {
                    "_id": ids[f["file_path"]],
                    "project_id": str(project_id),
                    "file_path": f["file_path"],
                    "file_name": f["file_path"].rsplit("/", 1)[-1],
                    "module_group": module_group_of(f["file_path"]),
                    "language": f["language"],
                    "ai_summary": "",
                    "content_excerpt": f["content"][:AI_EXCERPT_CHARS],
                    "role_tag": f["role_tag"],
                    "imports": [
                        {
                            "target_file": target,
                            "target_id": str(ids[target]),
                            "relation_label": "",
                        }
                        for target in f["targets"]
                    ],
                    "imported_by": [],
                    "created_at": now,
                    "updated_at": now,
                }
            )
        by_path = {d["file_path"]: d for d in docs}
        for doc in docs:
            for imp in doc["imports"]:
                by_path[imp["target_file"]]["imported_by"].append(doc["file_path"])
        name = (filename or "codebase.zip").removesuffix(".zip") or "Codebase"
        project = {
            "_id": project_id,
            "user_id": str(user_id),
            "name": name[:120],
            "description": "",
            "is_public_demo": False,
            "report_markdown": "",
            "status": "PROCESSING",
            "stats": {
                "total_raw_files": parsed["total_raw_files"],
                "analyzed_files": len(docs),
                "primary_language": parsed["primary_language"],
            },
            "diagram_data": build_diagram(
                [
                    {
                        "id": str(d["_id"]),
                        "file_name": d["file_name"],
                        "module_group": d["module_group"],
                        "role_tag": d["role_tag"],
                        "imports": d["imports"],
                    }
                    for d in docs
                ]
            ),
            "created_at": now,
            "updated_at": now,
        }
        await self.db[PROJECTS].insert_one(project)
        await self.db[FILES].insert_many(docs)
        contents = {f["file_path"]: f["content"] for f in files}
        reported, ai_error = await self._generate_report(
            user_id, project_id, name, docs, contents, prepared
        )
        await self._refresh_diagram(project_id, status="COMPLETED")
        project["status"] = "COMPLETED"
        return UploadOut(
            project=self._summary(project),
            analysis_dispatch="ai" if reported else "static",
            ai_analyzed=len(docs) if reported else 0,
            ai_error=ai_error,
        )

    async def regenerate_report(
        self,
        user_id: UUID,
        project_id: UUID,
        provider: str | None = None,
        model: str | None = None,
    ) -> UploadOut:
        # (Re)write the Markdown report for an existing project, using
        # the content excerpts stored at ingest time (no ZIP needed).
        # Only the owner may regenerate.
        doc = await self._require_project(user_id, project_id)
        if doc.get("user_id") != str(user_id):
            raise ProviderError("code_project_not_found")
        cursor = (
            self.db[FILES]
            .find({"project_id": str(project_id)})
            .sort("file_path", 1)
        )
        docs = [d async for d in cursor]
        contents = {d["file_path"]: d.get("content_excerpt", "") for d in docs}
        prepared = await self._prepare_ai(user_id, provider, model)
        reported, ai_error = await self._generate_report(
            user_id, project_id, doc["name"], docs, contents, prepared
        )
        fresh = await self.db[PROJECTS].find_one({"_id": project_id})
        return UploadOut(
            project=self._summary(fresh or doc),
            analysis_dispatch="ai" if reported else "static",
            ai_analyzed=len(docs) if reported else 0,
            ai_error=ai_error,
        )

    async def _prepare_ai(self, user_id, provider, model_id):
        """Resolve the LLM target for the direct AI pass.

        An explicit provider+model is validated up front so the usual
        provider errors surface to the uploader before anything is
        stored. Without an explicit target, the first configured and
        enabled provider with a chat-capable model wins; None means no
        AI is available and the upload completes statically.
        """
        if provider and model_id:
            credential, _model = await require_chat_target(
                self.providers, user_id, provider, model_id
            )
            key = self.vault.decrypt(
                credential.encrypted_api_key, user_id, provider
            )
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
        return None

    async def _generate_report(
        self, user_id, project_id, project_name, docs, contents, prepared
    ) -> tuple[bool, str]:
        # One LLM call writes the whole-project Markdown report. Any
        # failure degrades to no report (the static data still stands),
        # but the classified error code travels back so the caller can
        # tell the user why — a silent "static" hid a provider rejecting
        # max_tokens=8192 on a 4K-context model behind a misleading
        # "no provider available" message.
        if prepared is None:
            return False, ""
        provider, model_id, key = prepared
        adapter = create_provider(provider, chat_http=self.chat_http)
        prompt = _report_prompt(project_name, docs, contents)
        last_error = ""
        for budget in REPORT_TOKEN_LADDER:
            text, status, in_tok, out_tok, latency, error_code = (
                await self._call_model(
                    adapter, key, model_id, prompt,
                    max_output_tokens=budget,
                    timeout=REPORT_TIMEOUT_SECONDS,
                )
            )
            await self.requests.record_request(
                user_id,
                provider=provider,
                model=model_id,
                status=status,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_ms=latency,
            )
            if status == "success":
                report = _clean_markdown(text)
                if report:
                    await self.db[PROJECTS].update_one(
                        {"_id": project_id},
                        {"$set": {
                            "report_markdown": report,
                            "updated_at": utcnow(),
                        }},
                    )
                    return True, ""
                last_error = "generation_failed"
            else:
                last_error = error_code
            logger.warning(
                "code report attempt failed project=%s model=%s "
                "budget=%s error=%s",
                project_id, model_id, budget, last_error,
            )
        return False, last_error

    async def _call_model(
        self, adapter, key, model_id, prompt,
        max_output_tokens: int = 4096, timeout: int = 120,
    ):
        request = ChatRequest(
            model=model_id,
            turns=(ChatTurn("user", prompt),),
            max_output_tokens=max_output_tokens,
        )
        started = time.monotonic()
        parts: list[str] = []
        input_tokens = output_tokens = None
        status = "success"

        async def collect() -> None:
            nonlocal input_tokens, output_tokens
            async for event in adapter.stream_chat(key, request):
                if event.kind == "delta":
                    parts.append(event.text)
                elif event.kind == "usage":
                    if event.input_tokens is not None:
                        input_tokens = event.input_tokens
                    if event.output_tokens is not None:
                        output_tokens = event.output_tokens

        error_code = ""
        try:
            await asyncio.wait_for(collect(), timeout=timeout)
        except ProviderError as exc:
            status = "error"
            error_code = exc.code
        except Exception:  # timeout or transport failure
            status = "error"
            error_code = "generation_failed"
        latency_ms = int((time.monotonic() - started) * 1000)
        return (
            "".join(parts), status, input_tokens, output_tokens,
            latency_ms, error_code,
        )

    async def _apply_items(self, project_id, items, allowed=None) -> int:
        """Write AI results (summary, role, relation labels) onto file docs."""
        updated = 0
        for item in items:
            if allowed is not None and item["file_path"] not in allowed:
                continue
            query: dict = {"project_id": str(project_id)}
            if item.get("file_id") is not None:
                query["_id"] = item["file_id"]
            else:
                query["file_path"] = item["file_path"]
            doc = await self.db[FILES].find_one(query)
            if doc is None:
                continue
            changes: dict = {"updated_at": utcnow()}
            if item.get("ai_summary"):
                changes["ai_summary"] = item["ai_summary"]
            if item.get("role_tag"):
                changes["role_tag"] = item["role_tag"]
            labels = {
                imp["target_file"]: imp["relation_label"]
                for imp in item.get("imports") or []
                if imp.get("relation_label")
            }
            if labels:
                changes["imports"] = [
                    {
                        **imp,
                        "relation_label": labels.get(
                            imp.get("target_file"), imp.get("relation_label", "")
                        ),
                    }
                    for imp in doc.get("imports", [])
                ]
            await self.db[FILES].update_one(
                {"_id": doc["_id"]}, {"$set": changes}
            )
            updated += 1
        return updated

    async def _refresh_diagram(self, project_id, status: str | None = None):
        cursor = self.db[FILES].find({"project_id": str(project_id)})
        docs = [doc async for doc in cursor]
        changes: dict = {
            "diagram_data": build_diagram(
                [
                    {
                        "id": str(d["_id"]),
                        "file_name": d["file_name"],
                        "module_group": d.get("module_group", ""),
                        "role_tag": d.get("role_tag", ""),
                        "imports": d.get("imports") or [],
                    }
                    for d in docs
                ]
            ),
            "updated_at": utcnow(),
        }
        if status:
            changes["status"] = status
        await self.db[PROJECTS].update_one(
            {"_id": project_id}, {"$set": changes}
        )

    async def apply_callback(
        self, secret: str | None, payload: CodeCallbackIn
    ) -> CodeCallbackOut:
        """Optional external path: an n8n workflow may still POST results.

        The primary analysis path is the direct AI pass in
        ingest_upload; this callback stays for installations that
        prefer orchestrating the LLM calls in n8n.
        """
        expected = self.settings.n8n_code_analyzer_webhook_secret
        if expected and secret != expected:
            raise ProviderError("code_callback_unauthorized")
        project = await self.db[PROJECTS].find_one({"_id": payload.project_id})
        if project is None:
            raise ProviderError("code_project_not_found")
        items = [
            {
                "file_id": item.file_id,
                "file_path": item.file_path,
                "ai_summary": item.ai_summary,
                "role_tag": item.role_tag,
                "imports": [
                    {
                        "target_file": imp.target_file,
                        "relation_label": imp.relation_label,
                    }
                    for imp in item.imports
                ],
            }
            for item in payload.files
        ]
        updated = await self._apply_items(payload.project_id, items)
        status = {"completed": "COMPLETED", "failed": "FAILED"}.get(payload.status)
        if status:
            await self._refresh_diagram(payload.project_id, status=status)
        return CodeCallbackOut(received=True, updated=updated)
