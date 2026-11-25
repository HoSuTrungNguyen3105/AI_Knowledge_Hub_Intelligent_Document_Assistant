"""Codebase Architecture Analyzer storage (PROJECT_SPEC.md).

Two collections: `code_projects` (metadata + the prebuilt diagram
payload, so the UI renders instantly) and `code_project_files` (one
document per analyzed file: static imports, reverse dependencies, and
the AI summary/role filled in by the n8n callback or the demo seed).
Access is owner-scoped, except projects flagged `is_public_demo`,
which every signed-in user may open read-only.
"""

from uuid import UUID, uuid4

import httpx

from app.models.base import utcnow
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
from app.services.ai.base_provider import ProviderError
from app.services.code_parser import MAX_ZIP_BYTES, parse_codebase

PROJECTS = "code_projects"
FILES = "code_project_files"
CLUSTER_THRESHOLD = 50
BATCH_SIZE = 12
CONTENT_EXCERPT_CHARS = 6000


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


class CodeAnalyzerService:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    # --- mapping helpers ---------------------------------------------------
    @staticmethod
    def _summary(doc: dict) -> CodeProjectSummary:
        return CodeProjectSummary(
            id=doc["_id"],
            name=doc["name"],
            description=doc.get("description", ""),
            is_public_demo=bool(doc.get("is_public_demo")),
            status=doc.get("status", "PROCESSING"),
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
        transport: httpx.BaseTransport | None = None,
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
        dispatch = await self._dispatch_batches(project_id, files, ids, transport)
        if dispatch != "sent":
            # Without the AI pass the static result is still complete and
            # usable; the project must not spin in PROCESSING forever.
            await self.db[PROJECTS].update_one(
                {"_id": project_id},
                {"$set": {"status": "COMPLETED", "updated_at": utcnow()}},
            )
            project["status"] = "COMPLETED"
        return UploadOut(
            project=self._summary(project), analysis_dispatch=dispatch
        )

    async def _dispatch_batches(
        self, project_id: UUID, files: list[dict], ids: dict, transport
    ) -> str:
        url = self.settings.n8n_code_analyzer_webhook_url
        if not url:
            return "skipped"
        hook_secret = self.settings.n8n_code_analyzer_webhook_secret
        headers = {"Content-Type": "application/json"}
        if hook_secret:
            headers["x-mindflow-secret"] = hook_secret
        batches = [
            files[i : i + BATCH_SIZE] for i in range(0, len(files), BATCH_SIZE)
        ]
        all_ok = True
        async with httpx.AsyncClient(timeout=30.0, transport=transport) as client:
            for index, batch in enumerate(batches):
                payload = {
                    "event": "code_analysis.batch",
                    "project_id": str(project_id),
                    "batch_index": index,
                    "batch_count": len(batches),
                    "files": [
                        {
                            "file_id": str(ids[f["file_path"]]),
                            "file_path": f["file_path"],
                            "language": f["language"],
                            "imports": f["targets"],
                            "content_excerpt": f["content"][:CONTENT_EXCERPT_CHARS],
                        }
                        for f in batch
                    ],
                }
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    ok = (
                        response.status_code == 200
                        and response.json().get("received") is True
                    )
                except (httpx.HTTPError, ValueError):
                    ok = False
                all_ok = all_ok and ok
        return "sent" if all_ok else "failed"

    async def apply_callback(
        self, secret: str | None, payload: CodeCallbackIn
    ) -> CodeCallbackOut:
        expected = self.settings.n8n_code_analyzer_webhook_secret
        if expected and secret != expected:
            raise ProviderError("code_callback_unauthorized")
        project = await self.db[PROJECTS].find_one({"_id": payload.project_id})
        if project is None:
            raise ProviderError("code_project_not_found")
        updated = 0
        for item in payload.files:
            query: dict = {"project_id": str(payload.project_id)}
            if item.file_id is not None:
                query["_id"] = item.file_id
            else:
                query["file_path"] = item.file_path
            doc = await self.db[FILES].find_one(query)
            if doc is None:
                continue
            changes: dict = {"updated_at": utcnow()}
            if item.ai_summary:
                changes["ai_summary"] = item.ai_summary
            if item.role_tag:
                changes["role_tag"] = item.role_tag
            labels = {
                i.target_file: i.relation_label
                for i in item.imports
                if i.relation_label
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
        status = {"completed": "COMPLETED", "failed": "FAILED"}.get(payload.status)
        if status:
            cursor = self.db[FILES].find({"project_id": str(payload.project_id)})
            docs = [doc async for doc in cursor]
            diagram = build_diagram(
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
            )
            await self.db[PROJECTS].update_one(
                {"_id": payload.project_id},
                {
                    "$set": {
                        "status": status,
                        "diagram_data": diagram,
                        "updated_at": utcnow(),
                    }
                },
            )
        return CodeCallbackOut(received=True, updated=updated)
