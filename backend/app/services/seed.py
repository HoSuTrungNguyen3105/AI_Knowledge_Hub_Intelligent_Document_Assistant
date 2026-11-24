"""Idempotent demo seeding for the caller's own account (NEXORA Part 5).

Safety rules, mirroring the spec:
- Only runs when APP_ENV is development or demo; production is refused
  with `seed_disabled`. Nothing here ever runs automatically at startup.
- Only ever touches the caller's own records. Agents/teams that already
  exist (matched by name) are reused, never overwritten and never
  relabelled as demo — only records this service creates get
  `is_demo: True`.
- Removal deletes only `is_demo` records, and keeps a demo agent that a
  remaining (real) team still references.
- No usage/execution history is fabricated: seeded agents and teams are
  configuration records, clearly flagged, and analytics can exclude them.

The seven agent definitions mirror STARTER_AGENTS in
`frontend/utils/workflows.js` (the Phase 6 starter kit) so a seeded
account and a starter-kit account look identical; the three teams follow
the examples in Module 05 of the NEXORA spec.
"""

import re
from uuid import UUID

from app.models.base import utcnow
from app.schemas.agents import AgentCreate
from app.schemas.seed import SeedApplyOut, SeedApplyRequest, SeedRemoveOut, SeedStatusOut
from app.schemas.workflows import TeamCreate, TeamMemberIn
from app.services.agents import AgentService
from app.services.ai.base_provider import ProviderError
from app.services.workflows import WorkflowService

SEED_VERSION = 1

DEMO_AGENTS = [
    {
        "name": "AI Leader",
        "tools": ["data_analyzer"],
        "description": (
            "Coordinator/Leader — điều phối workflow, giao việc và tổng hợp "
            "kết quả cuối cùng."
        ),
        "system_prompt": (
            "Bạn là AI Leader, Coordinator của một nhóm Agent trong MindFlow AI. Nhiệm vụ: hiểu "
            "mục tiêu chung, giao nhiệm vụ rõ ràng cho từng Agent phù hợp, theo dõi tiến độ, "
            "quyết định bước tiếp theo và tổng hợp kết quả cuối cùng cho người dùng bằng tiếng "
            "Việt. Không tự làm thay phần việc chuyên môn của Agent khác khi có thể giao việc."
        ),
    },
    {
        "name": "AI Planner",
        "tools": ["data_analyzer"],
        "description": "Planner — chia mục tiêu thành các task có thứ tự và phụ thuộc rõ ràng.",
        "system_prompt": (
            "Bạn là AI Planner trong MindFlow AI. Nhiệm vụ: phân tích mục tiêu, chia thành các "
            "task nhỏ có thứ tự thực hiện và phụ thuộc rõ ràng, nêu tiêu chí hoàn thành cho từng "
            "task. Trả lời bằng tiếng Việt, ngắn gọn, dạng danh sách đánh số."
        ),
    },
    {
        "name": "AI Architect",
        "tools": ["data_analyzer"],
        "description": "Architect — phân tích kiến trúc hiện tại và thiết kế giải pháp.",
        "system_prompt": (
            "Bạn là AI Architect trong MindFlow AI. Nhiệm vụ: phân tích kiến trúc hệ thống hiện "
            "tại dựa trên thông tin được cung cấp, chỉ ra ảnh hưởng/rủi ro và đề xuất thiết kế "
            "giải pháp khả thi. Không giả vờ đã đọc code hay sửa file nếu không có dữ liệu. Trả "
            "lời bằng tiếng Việt."
        ),
    },
    {
        "name": "AI Developer",
        "tools": ["calculator", "data_analyzer"],
        "description": "Developer — thực hiện nhiệm vụ kỹ thuật, đề xuất hướng dẫn/patch khi cần.",
        "system_prompt": (
            "Bạn là AI Developer trong MindFlow AI. Nhiệm vụ: thực hiện nhiệm vụ kỹ thuật được "
            "giao trong phạm vi context được cấp, trình bày giải pháp/hướng dẫn/patch đề xuất rõ "
            "ràng. Không giả vờ đã sửa file trên máy chủ. Trả lời bằng tiếng Việt, kèm ví dụ cụ "
            "thể khi hữu ích."
        ),
    },
    {
        "name": "AI Tester",
        "tools": ["calculator", "data_analyzer"],
        "description": "Tester — kiểm tra kết quả, tìm lỗi và gửi yêu cầu sửa khi chưa đạt.",
        "system_prompt": (
            "Bạn là AI Tester trong MindFlow AI. Nhiệm vụ: kiểm tra kết quả của Agent khác theo "
            "tiêu chí của task, liệt kê lỗi/thiếu sót cụ thể nếu có và yêu cầu sửa "
            "(REVISION_REQUEST) khi chưa đạt; xác nhận đạt khi kết quả đúng. Trả lời bằng tiếng "
            "Việt."
        ),
    },
    {
        "name": "AI Reviewer",
        "tools": ["data_analyzer"],
        "description": "Reviewer — phản biện, phê duyệt hoặc yêu cầu chỉnh sửa kết quả.",
        "system_prompt": (
            "Bạn là AI Reviewer trong MindFlow AI. Nhiệm vụ: đánh giá chất lượng kế hoạch/kết quả "
            "được gửi, phê duyệt (APPROVAL) khi đạt hoặc yêu cầu chỉnh sửa (REVISION_REQUEST) kèm "
            "lý do cụ thể khi chưa đạt. Trả lời bằng tiếng Việt, thẳng thắn và có căn cứ."
        ),
    },
    {
        "name": "AI Researcher",
        "tools": ["datetime", "data_analyzer"],
        "description": "Researcher — thu thập và tóm tắt thông tin phục vụ nhiệm vụ chung.",
        "system_prompt": (
            "Bạn là AI Researcher trong MindFlow AI. Nhiệm vụ: thu thập, so sánh và tóm tắt thông "
            "tin liên quan tới nhiệm vụ từ context/công cụ được cấp, phân biệt rõ dữ kiện và suy "
            "luận, không bịa nguồn. Trả lời bằng tiếng Việt."
        ),
    },
]

# (agent name, team role) — AI Leader coordinates every demo team.
DEMO_TEAMS = [
    {
        "name": "Nhóm Kỹ thuật (Demo)",
        "description": (
            "Đội mẫu NEXORA — Engineering: Leader điều phối, Planner, "
            "Developer, Reviewer."
        ),
        "members": [
            ("AI Leader", "coordinator"),
            ("AI Planner", "planner"),
            ("AI Developer", "developer"),
            ("AI Reviewer", "reviewer"),
        ],
    },
    {
        "name": "Nhóm Nghiên cứu (Demo)",
        "description": (
            "Đội mẫu NEXORA — Research: Leader điều phối, Researcher, "
            "Architect, Tester."
        ),
        "members": [
            ("AI Leader", "coordinator"),
            ("AI Researcher", "researcher"),
            ("AI Architect", "architect"),
            ("AI Tester", "tester"),
        ],
    },
    {
        "name": "Nhóm Vận hành (Demo)",
        "description": (
            "Đội mẫu NEXORA — Operations: Leader điều phối, Planner, "
            "Researcher, Developer."
        ),
        "members": [
            ("AI Leader", "coordinator"),
            ("AI Planner", "planner"),
            ("AI Researcher", "researcher"),
            ("AI Developer", "developer"),
        ],
    },
]


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


class SeedService:
    def __init__(self, db, settings, http):
        self.db = db
        self.settings = settings
        self.agents = AgentService(db, settings)
        self.workflows = WorkflowService(db, settings, http)

    @property
    def enabled(self) -> bool:
        return self.settings.app_env in {"development", "demo"}

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ProviderError("seed_disabled")

    def _registry_key(self, user_id: UUID) -> str:
        return f"demo_seed_v{SEED_VERSION}:{user_id}"

    async def _resolve_target(self, user_id: UUID, payload: SeedApplyRequest) -> tuple[str, str]:
        if payload.provider and payload.model:
            return payload.provider, payload.model
        credential = await self.db.user_provider_credentials.find_one(
            {"user_id": user_id, "enabled": True, "connection_status": "connected"}
        )
        if credential is None:
            raise ProviderError("seed_provider_required")
        model = credential.get("default_model")
        if not model:
            async for doc in self.db.ai_models.find({"credential_id": credential["_id"]}):
                capabilities = doc.get("capabilities") or {}
                if capabilities.get("chat") is not False:
                    model = doc["model_id"]
                    break
        if not model:
            raise ProviderError("seed_provider_required")
        return credential["provider"], model

    async def status(self, user_id: UUID) -> SeedStatusOut:
        demo_agents = await self.db.agents.count_documents(
            {"user_id": user_id, "is_demo": True}
        )
        demo_teams = await self.db.agent_teams.count_documents(
            {"user_id": user_id, "is_demo": True}
        )
        return SeedStatusOut(
            enabled=self.enabled,
            app_env=self.settings.app_env,
            seeded=demo_agents > 0 or demo_teams > 0,
            demo_agents=demo_agents,
            demo_teams=demo_teams,
        )

    async def _create_agent(self, user_id: UUID, spec: dict, provider: str, model: str):
        payload = AgentCreate(
            name=spec["name"],
            description=spec["description"],
            system_prompt=spec["system_prompt"],
            provider=provider,
            model=model,
            tools=list(spec["tools"]),
        )
        try:
            return await self.agents.create_agent(user_id, payload)
        except ProviderError as exc:
            # A model that explicitly cannot call tools still gets its
            # agent — just without tools, like the starter kit does.
            if exc.code != "model_not_tool_capable" or not spec["tools"]:
                raise
            payload.tools = []
            return await self.agents.create_agent(user_id, payload)

    async def apply(self, user_id: UUID, payload: SeedApplyRequest) -> SeedApplyOut:
        self._require_enabled()
        provider, model = await self._resolve_target(user_id, payload)

        existing = {
            _norm(a.name): a for a in (await self.agents.list_agents(user_id)).agents
        }
        by_name: dict[str, UUID] = {}
        created: list[str] = []
        reused: list[str] = []
        for spec in DEMO_AGENTS:
            found = existing.get(_norm(spec["name"]))
            if found is not None:
                by_name[spec["name"]] = found.id
                reused.append(spec["name"])
                continue
            agent = await self._create_agent(user_id, spec, provider, model)
            await self.db.agents.update_one(
                {"_id": agent.id}, {"$set": {"is_demo": True}}
            )
            by_name[spec["name"]] = agent.id
            created.append(spec["name"])

        teams = {_norm(t.name): t for t in (await self.workflows.list_teams(user_id)).teams}
        created_teams: list[str] = []
        skipped_teams: list[str] = []
        for spec in DEMO_TEAMS:
            if _norm(spec["name"]) in teams:
                skipped_teams.append(spec["name"])
                continue
            members = [
                TeamMemberIn(agent_id=by_name[name], role=role)
                for name, role in spec["members"]
            ]
            team = await self.workflows.create_team(
                user_id,
                TeamCreate(
                    name=spec["name"],
                    description=spec["description"],
                    coordinator_agent_id=by_name["AI Leader"],
                    members=members,
                ),
            )
            await self.db.agent_teams.update_one(
                {"_id": team.id}, {"$set": {"is_demo": True}}
            )
            created_teams.append(spec["name"])

        await self.db.seed_registry.update_one(
            {"key": self._registry_key(user_id)},
            {
                "$set": {
                    "version": SEED_VERSION,
                    "user_id": user_id,
                    "applied_at": utcnow(),
                    "agents": len(created) + len(reused),
                    "teams": len(created_teams) + len(skipped_teams),
                }
            },
            upsert=True,
        )
        return SeedApplyOut(
            created_agents=created,
            reused_agents=reused,
            created_teams=created_teams,
            skipped_teams=skipped_teams,
        )

    async def remove(self, user_id: UUID) -> SeedRemoveOut:
        self._require_enabled()

        removed_teams = 0
        demo_teams = await self.db.agent_teams.find(
            {"user_id": user_id, "is_demo": True}
        ).to_list(length=100)
        for team in demo_teams:
            await self.workflows.delete_team(user_id, team["_id"])
            removed_teams += 1

        # A demo agent still referenced by a remaining (real) team is kept:
        # deleting it would break that team's membership.
        referenced: set[UUID] = set()
        async for team in self.db.agent_teams.find({"user_id": user_id}):
            referenced.add(team["coordinator_agent_id"])
            for member in team.get("members", []):
                referenced.add(member["agent_id"])

        removed_agents = 0
        kept: list[str] = []
        demo_agents = await self.db.agents.find(
            {"user_id": user_id, "is_demo": True}
        ).to_list(length=100)
        for agent in demo_agents:
            if agent["_id"] in referenced:
                kept.append(agent["name"])
                continue
            await self.agents.delete_agent(user_id, agent["_id"])
            removed_agents += 1

        await self.db.seed_registry.delete_one({"key": self._registry_key(user_id)})
        return SeedRemoveOut(
            removed_agents=removed_agents,
            removed_teams=removed_teams,
            kept_agents=kept,
        )
