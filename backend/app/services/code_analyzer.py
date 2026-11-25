"""Codebase Architecture Analyzer storage (PROJECT_SPEC.md).

Two collections: `code_projects` (metadata + the prebuilt diagram
payload, so the UI renders instantly) and `code_project_files` (one
document per analyzed file: static imports, reverse dependencies, and
the AI summary/role filled in by the n8n callback or the demo seed).
Access is owner-scoped, except projects flagged `is_public_demo`,
which every signed-in user may open read-only.
"""

from uuid import UUID, uuid4

from app.models.base import utcnow
from app.schemas.code_analyzer import (
    CodeFileDetail,
    CodeFileSummary,
    CodeProjectDetail,
    CodeProjectSummary,
    SeedDemoOut,
)
from app.services.ai.base_provider import ProviderError

PROJECTS = "code_projects"
FILES = "code_project_files"
CLUSTER_THRESHOLD = 50


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
    return {"mode": "clusters", "nodes": nodes, "edges": cluster_edges}


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
