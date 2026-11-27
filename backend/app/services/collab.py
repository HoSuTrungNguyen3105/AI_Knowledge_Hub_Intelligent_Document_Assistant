"""Collaboration rooms (NEXORA Module 03).

The ``multi_chats`` collection was scaffolded for Multi-AI Chat but
never got an API; this module builds collaboration rooms on it: a room
has member Agents (``agent_ids``), a shared message log
(``collab_messages``), and @mentions — mentioning a member runs that
Agent through the exact Phase 5 execution path (AgentService) and
stores the reply in the room. Replies are independent: one Agent
failing records an error message in the room instead of failing the
whole post.

Agent-to-Agent context (Collaboration Room update): the context for
each Agent is rebuilt from the database immediately before that Agent
runs, so an Agent mentioned later in the same post reads the replies
the earlier Agents have just stored — the previous implementation
froze one transcript before the mention loop, so a second mentioned
Agent never saw the first Agent's answer. Messages carry a per-room
``sequence`` and a ``reply_to_message_id`` link; each Agent reply
records the ``context_message_ids`` it was actually given, so what an
Agent saw is auditable. The transcript keeps the NEWEST messages when
it has to be trimmed, and the run uses a larger token budget than the
Agent Studio default because a room transcript is long by design.

Generation is non-streaming at this layer: the post returns when every
mentioned Agent has answered. The client may stop *waiting* (abort),
but a started Agent run still finishes and its reply lands in the
room — the UI says so honestly.
"""

import base64
import hashlib
import io
import json
import zipfile
from uuid import UUID, uuid4

from app.models.base import utcnow
from app.schemas.agents import RunRequest
from app.schemas.collab import (
    ArtifactList,
    ArtifactOut,
    CollabMessageOut,
    ExportIn,
    ExportResult,
    MessageIn,
    PostResult,
    RoomAgentOut,
    RoomCreate,
    RoomList,
    RoomOut,
    RoomPatch,
    RunDetail,
    SnapshotMemberOut,
    TeamSnapshotOut,
    RunList,
    RunOut,
    SummarizeIn,
    TaskOut,
    RoleUsageOut,
    RoomUsageOut,
    RunUsageOut,
)
from app.repositories.workflows import WorkflowRepository
from app.services.agents import AgentService
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP

ROOMS = "multi_chats"
MESSAGES = "collab_messages"
RUNS = "collab_runs"
TASKS = "collab_tasks"
ARTIFACTS = "collab_artifacts"
TRANSCRIPT_LIMIT = 20
TRANSCRIPT_CHARS = 12000
CONCLUSION_MARKER = "[KẾT LUẬN]"
# Auto-discussion router: role keywords matched against the agent's
# NAME (the fleet uses names like "AI Architect"); the topic words are
# matched against the latest room content. Deterministic on purpose —
# the same discussion always routes the same way, and tests can rely
# on it. When nothing matches, the first eligible member speaks.
ROLE_KEYWORDS = {
    "architect": ["kiến trúc", "architect", "thiết kế hệ thống", "schema", "cấu trúc"],
    "developer": ["code", "lập trình", "implement", "bug", "sửa lỗi", "developer", "hàm"],
    "tester": ["test", "kiểm thử", "kiểm tra", "qa", "testcase"],
    "reviewer": ["review", "phản biện", "đánh giá", "reviewer", "nhận xét"],
    "researcher": ["nghiên cứu", "tìm hiểu", "research", "so sánh", "tra cứu"],
    "planner": ["kế hoạch", "plan", "phân rã", "roadmap", "lộ trình"],
    "leader": ["tổng hợp", "điều phối", "leader", "kết luận"],
}
AUTO_INSTRUCTION = (
    "Đây là lượt của bạn trong một cuộc thảo luận TỰ ĐỘNG. Hãy tiếp nối thảo luận "
    "dựa trên toàn bộ lịch sử ở trên: bổ sung, phản biện hoặc đẩy vấn đề về phía "
    "kết luận, đừng lặp lại ý đã có. Nếu bạn thấy vấn đề đã đủ rõ để kết luận, "
    f"hãy bắt đầu câu trả lời bằng {CONCLUSION_MARKER}."
)
SUMMARY_INSTRUCTION = (
    "Bạn là Moderator của phòng. Hãy tổng hợp toàn bộ thảo luận ở trên thành kết "
    "luận cuối cùng với đúng 4 phần: 1) Điều đã được xác nhận, 2) Đề xuất/ý kiến, "
    "3) Điểm còn bất đồng, 4) Rủi ro và việc cần người dùng quyết định. Chỉ dựa "
    "vào nội dung thật trong phòng, không bịa thêm kết quả của Agent chưa nói."
)
RETRY_INSTRUCTION = (
    "Lượt trả lời trước của bạn trong phòng đã thất bại. Hãy trả lời lại yêu cầu "
    "gần nhất của người dùng, dựa trên toàn bộ lịch sử phòng ở trên."
)
# Room transcripts are long by design (up to TRANSCRIPT_CHARS of mostly
# Vietnamese text ≈ 30 KB of UTF-8), so the Agent Studio default byte
# budget (8000) would reject nearly every roomy prompt. Same value the
# project Discussion feature uses for the same reason.
COLLAB_TOKEN_BUDGET = 32768


class CollabService:
    def __init__(self, db, settings, chat_http: ChatHTTP | None = None):
        self.db = db
        self.settings = settings
        self.chat_http = chat_http
        self.rooms = db[ROOMS]
        self.messages = db[MESSAGES]
        self.runs = db[RUNS]
        self.tasks = db[TASKS]
        self.artifacts = db[ARTIFACTS]

    # --- helpers -------------------------------------------------------------
    def _agent_service(self) -> AgentService:
        return AgentService(self.db, self.settings, self.chat_http)

    async def _validate_agents(self, user_id: UUID, agent_ids: list[UUID]) -> None:
        service = self._agent_service()
        for agent_id in dict.fromkeys(agent_ids):
            await service.get_agent(user_id, agent_id)  # 404 when not the owner's

    async def _require_room(self, user_id: UUID, room_id: UUID) -> dict:
        doc = await self.rooms.find_one({"_id": room_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("collab_room_not_found")
        return doc

    async def _room_out(self, user_id: UUID, doc) -> RoomOut:
        snapshot = doc.get("team_snapshot") or None
        team_snapshot_out = None
        if snapshot:
            # Team rooms render from the frozen snapshot: later edits to
            # the team or the Agents must not rewrite this session.
            agents = [
                RoomAgentOut(
                    id=m["agent_id"],
                    name=m.get("agent_name") or str(m["agent_id"]),
                    provider=m.get("provider"),
                    model=m.get("model"),
                    role=m.get("role"),
                )
                for m in snapshot.get("members") or []
            ]
            team_snapshot_out = TeamSnapshotOut(
                team_id=snapshot["team_id"],
                team_name=snapshot.get("team_name") or "",
                coordinator_agent_id=snapshot["coordinator_agent_id"],
                members=[
                    SnapshotMemberOut(
                        agent_id=m["agent_id"],
                        agent_name=m.get("agent_name"),
                        role=m.get("role") or "member",
                        enabled=m.get("enabled", True),
                        execution_order=m.get("execution_order"),
                        priority=m.get("priority") or 0,
                        instructions=m.get("instructions"),
                        responsibility=m.get("responsibility"),
                        description=m.get("description"),
                        provider=m.get("provider"),
                        model=m.get("model"),
                        provider_override=m.get("provider_override"),
                        model_override=m.get("model_override"),
                    )
                    for m in snapshot.get("members") or []
                ],
            )
        else:
            summaries = {a.id: a for a in (await self._agent_service().list_agents(user_id)).agents}
            agents = [
                RoomAgentOut(id=a.id, name=a.name, provider=a.provider, model=a.model)
                for agent_id in doc.get("agent_ids") or []
                if (a := summaries.get(agent_id)) is not None
            ]
        total_in = 0
        total_out = 0
        count = 0
        cursor = self.messages.find(
            {"room_id": doc["_id"]},
            {"input_tokens": 1, "output_tokens": 1},
        )
        async for message in cursor:
            count += 1
            total_in += message.get("input_tokens") or 0
            total_out += message.get("output_tokens") or 0
        return RoomOut(
            id=doc["_id"],
            title=doc["title"],
            team_id=doc.get("team_id"),
            team_snapshot=team_snapshot_out,
            agent_ids=list(doc.get("agent_ids") or []),
            agents=agents,
            mode=doc.get("mode") or "directed",
            moderator_agent_id=doc.get("moderator_agent_id"),
            max_turns=doc.get("max_turns") or 4,
            allow_handoff=doc.get("allow_handoff", True),
            message_count=count,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    @staticmethod
    def _message_out(doc) -> CollabMessageOut:
        return CollabMessageOut(
            id=doc["_id"],
            room_id=doc["room_id"],
            sender_type=doc["sender_type"],
            agent_id=doc.get("agent_id"),
            agent_name=doc.get("agent_name"),
            provider=doc.get("provider"),
            model=doc.get("model"),
            content=doc["content"],
            mentions=doc.get("mentions") or [],
            sequence=doc.get("sequence") or 0,
            reply_to_message_id=doc.get("reply_to_message_id"),
            context_message_ids=doc.get("context_message_ids") or [],
            run_id=doc.get("run_id"),
            is_summary=bool(doc.get("is_summary")),
            input_tokens=doc.get("input_tokens"),
            output_tokens=doc.get("output_tokens"),
            status=doc.get("status") or "done",
            error_code=doc.get("error_code"),
            created_at=doc["created_at"],
        )

    async def _store_message(self, user_id: UUID, room_id: UUID, **fields) -> dict:
        doc = {"_id": uuid4(), "user_id": user_id, "room_id": room_id, **fields}
        await self.messages.insert_one(doc)
        await self.rooms.update_one({"_id": room_id}, {"$set": {"updated_at": utcnow()}})
        return doc

    # --- rooms ---------------------------------------------------------------
    @staticmethod
    def _snapshot_member(room: dict, agent_id) -> dict | None:
        snapshot = room.get("team_snapshot") or {}
        for member in snapshot.get("members") or []:
            if member.get("agent_id") == agent_id:
                return member
        return None

    async def _build_team_snapshot(self, user_id: UUID, team) -> dict:
        """Freeze the team's assignment configuration into a room.

        Everything the engine needs — role, execution order,
        instructions and the EFFECTIVE provider/model (team override
        when set, otherwise the Agent's own) — is copied at room
        creation time, so later edits to the team or to the Agents
        never rewrite a running or finished session.
        """
        summaries = {a.id: a for a in (await self._agent_service().list_agents(user_id)).agents}
        members = []
        for m in team.members:
            agent = summaries.get(m.agent_id)
            members.append(
                {
                    "agent_id": m.agent_id,
                    "agent_name": agent.name if agent else None,
                    "role": m.role,
                    "enabled": m.enabled,
                    "execution_order": getattr(m, "execution_order", None),
                    "priority": getattr(m, "priority", 0) or 0,
                    "instructions": getattr(m, "instructions", None),
                    "responsibility": getattr(m, "responsibility", None),
                    "description": getattr(m, "description", None),
                    "provider_override": getattr(m, "provider_override", None),
                    "model_override": getattr(m, "model_override", None),
                    "system_prompt_override": getattr(m, "system_prompt_override", None),
                    "provider": getattr(m, "provider_override", None)
                    or (agent.provider if agent else None),
                    "model": getattr(m, "model_override", None)
                    or (agent.model if agent else None),
                }
            )
        return {
            "team_id": team.id,
            "team_name": team.name,
            "coordinator_agent_id": team.coordinator_agent_id,
            "members": members,
        }

    async def create_room(self, user_id: UUID, payload: RoomCreate) -> RoomOut:
        team_snapshot = None
        if payload.team_id is not None:
            team = await WorkflowRepository(self.db).get_team(user_id, payload.team_id)
            if team is None:
                raise ProviderError("team_not_found")
            team_snapshot = await self._build_team_snapshot(user_id, team)
            member_ids = [m["agent_id"] for m in team_snapshot["members"] if m["enabled"]]
            if not member_ids:
                raise ProviderError("collab_team_empty")
            coordinator = self._snapshot_member(
                {"team_snapshot": team_snapshot}, team_snapshot["coordinator_agent_id"]
            )
            if coordinator is None or not coordinator["enabled"]:
                raise ProviderError("collab_team_no_leader")
            moderator_id = team_snapshot["coordinator_agent_id"]
        else:
            await self._validate_agents(user_id, payload.agent_ids)
            member_ids = list(dict.fromkeys(payload.agent_ids))
            moderator_id = payload.moderator_agent_id
            if moderator_id is not None:
                await self._validate_agents(user_id, [moderator_id])
                if moderator_id not in member_ids:
                    raise ProviderError("collab_moderator_not_member")
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "title": payload.title,
            "conversation_ids": [],
            "agent_ids": member_ids,
            "mode": payload.mode,
            "team_id": payload.team_id,
            "team_snapshot": team_snapshot,
            "moderator_agent_id": moderator_id,
            "max_turns": payload.max_turns,
            "allow_handoff": payload.allow_handoff,
            "system_prompt": None,
            "temperature": None,
            "max_output_tokens": None,
            "syntheses": [],
            "created_at": now,
            "updated_at": now,
        }
        await self.rooms.insert_one(doc)
        return await self._room_out(user_id, doc)

    async def list_rooms(self, user_id: UUID) -> RoomList:
        docs = (
            await self.rooms.find({"user_id": user_id})
            .sort("updated_at", -1)
            .limit(100)
            .to_list(length=100)
        )
        return RoomList(rooms=[await self._room_out(user_id, doc) for doc in docs])

    async def get_room(self, user_id: UUID, room_id: UUID) -> RoomOut:
        return await self._room_out(user_id, await self._require_room(user_id, room_id))

    async def patch_room(self, user_id: UUID, room_id: UUID, payload: RoomPatch) -> RoomOut:
        doc = await self._require_room(user_id, room_id)
        if doc.get("team_snapshot") and (
            payload.agent_ids is not None or "moderator_agent_id" in payload.model_fields_set
        ):
            # A team room's membership IS its snapshot; letting a patch
            # change members without the snapshot would desync the two.
            raise ProviderError("collab_team_room_frozen")
        updates: dict = {"updated_at": utcnow()}
        if payload.title is not None:
            updates["title"] = payload.title
        if payload.agent_ids is not None:
            await self._validate_agents(user_id, payload.agent_ids)
            updates["agent_ids"] = list(dict.fromkeys(payload.agent_ids))
        if payload.mode is not None:
            updates["mode"] = payload.mode
        if payload.max_turns is not None:
            updates["max_turns"] = payload.max_turns
        if payload.allow_handoff is not None:
            updates["allow_handoff"] = payload.allow_handoff
        if "moderator_agent_id" in payload.model_fields_set:
            if payload.moderator_agent_id is not None:
                await self._validate_agents(user_id, [payload.moderator_agent_id])
                members = updates.get("agent_ids", list(doc.get("agent_ids") or []))
                if payload.moderator_agent_id not in members:
                    raise ProviderError("collab_moderator_not_member")
            updates["moderator_agent_id"] = payload.moderator_agent_id
        await self.rooms.update_one({"_id": room_id}, {"$set": updates})
        doc.update(updates)
        return await self._room_out(user_id, doc)

    async def delete_room(self, user_id: UUID, room_id: UUID) -> None:
        await self._require_room(user_id, room_id)
        await self.rooms.delete_one({"_id": room_id, "user_id": user_id})
        await self.messages.delete_many({"room_id": room_id, "user_id": user_id})
        await self.runs.delete_many({"room_id": room_id, "user_id": user_id})
        await self.tasks.delete_many({"room_id": room_id, "user_id": user_id})
        await self.artifacts.delete_many({"room_id": room_id, "user_id": user_id})

    # --- messages --------------------------------------------------------------
    async def room_usage(self, user_id: UUID, room_id: UUID) -> RoomUsageOut:
        """Real per-room usage: tokens by Agent/role and by run.

        Aggregated from the stored Agent replies (the same records the
        room transcript shows) — a reply only counts when the provider
        actually reported token usage for it. Cost is estimated with
        the user's own synced model prices (the AI Usage pricing map);
        replies whose model has no price are counted as unpriced and
        contribute no cost, never an invented number.
        """
        room = await self._require_room(user_id, room_id)
        from app.services.analytics import AnalyticsService

        prices = await AnalyticsService(self.db)._price_map(user_id)
        snapshot_roles = {
            m.get("agent_id"): m.get("role")
            for m in (room.get("team_snapshot") or {}).get("members") or []
        }
        run_docs = {
            doc["_id"]: doc
            async for doc in self.runs.find({"room_id": room_id})
        }
        totals = {"requests": 0, "input": 0, "output": 0, "cost": 0.0, "priced": 0, "unpriced": 0}
        role_buckets: dict = {}
        run_buckets: dict = {}

        def accumulate(bucket, doc, cost):
            bucket["requests"] += 1
            bucket["input"] += doc.get("input_tokens") or 0
            bucket["output"] += doc.get("output_tokens") or 0
            if cost is not None:
                bucket["cost"] += cost
                bucket["priced"] += 1

        cursor = self.messages.find(
            {"room_id": room_id, "sender_type": "agent"},
            {
                "agent_id": 1, "agent_name": 1, "provider": 1, "model": 1,
                "input_tokens": 1, "output_tokens": 1, "run_id": 1,
            },
        )
        async for doc in cursor:
            if doc.get("input_tokens") is None and doc.get("output_tokens") is None:
                continue  # no usage reported for this reply — do not guess
            price = prices.get((doc.get("provider"), doc.get("model")))
            cost = None
            if price is not None and (price[0] is not None or price[1] is not None):
                cost = (doc.get("input_tokens") or 0) * (price[0] or 0.0) + (
                    doc.get("output_tokens") or 0
                ) * (price[1] or 0.0)
            if cost is None:
                totals["unpriced"] += 1
            accumulate(totals, doc, cost)
            agent_id = doc.get("agent_id")
            role_bucket = role_buckets.setdefault(
                agent_id,
                {
                    "requests": 0, "input": 0, "output": 0, "cost": 0.0, "priced": 0,
                    "agent_name": doc.get("agent_name"),
                    "provider": doc.get("provider"),
                    "model": doc.get("model"),
                },
            )
            accumulate(role_bucket, doc, cost)
            run_id = doc.get("run_id")
            if run_id is not None:
                run_bucket = run_buckets.setdefault(
                    run_id, {"requests": 0, "input": 0, "output": 0, "cost": 0.0, "priced": 0}
                )
                accumulate(run_bucket, doc, cost)

        def bucket_out(bucket):
            return {
                "requests": bucket["requests"],
                "input_tokens": bucket["input"],
                "output_tokens": bucket["output"],
                "estimated_cost": bucket["cost"] if bucket["priced"] else None,
            }

        by_role = [
            RoleUsageOut(
                role=snapshot_roles.get(agent_id),
                agent_id=agent_id,
                agent_name=bucket["agent_name"],
                provider=bucket["provider"],
                model=bucket["model"],
                **bucket_out(bucket),
            )
            for agent_id, bucket in role_buckets.items()
        ]
        by_role.sort(key=lambda b: -(b.input_tokens + b.output_tokens))
        by_run = [
            RunUsageOut(
                run_id=run_id,
                mode=(run_docs.get(run_id) or {}).get("mode") or "directed",
                status=(run_docs.get(run_id) or {}).get("status") or "completed",
                **bucket_out(bucket),
            )
            for run_id, bucket in run_buckets.items()
        ]
        return RoomUsageOut(
            room_id=room_id,
            unpriced_requests=totals["unpriced"],
            by_role=by_role,
            by_run=by_run,
            **bucket_out(totals),
        )

    async def list_messages(self, user_id: UUID, room_id: UUID) -> list[CollabMessageOut]:
        await self._require_room(user_id, room_id)
        docs = (
            await self.messages.find({"room_id": room_id, "user_id": user_id})
            .sort("created_at", 1)
            .limit(500)
            .to_list(length=500)
        )
        return [self._message_out(doc) for doc in docs]

    async def _next_sequence(self, room_id: UUID) -> int:
        doc = await self.messages.find_one(
            {"room_id": room_id}, sort=[("sequence", -1)], projection={"sequence": 1}
        )
        if doc is None:
            return 1
        return (doc.get("sequence") or 0) + 1

    async def _context(self, room_id: UUID) -> tuple[str, list[str]]:
        """Structured room context, re-read from the database.

        Returns the labelled transcript (oldest first) and the ids of
        the messages included, so a reply can record exactly what its
        Agent was given. Error replies are skipped — they carry no
        content — and when the transcript exceeds the character budget
        the NEWEST lines survive (the previous implementation kept the
        oldest and silently cut the latest results).
        """
        docs = (
            await self.messages.find({"room_id": room_id})
            .sort("created_at", -1)
            .limit(TRANSCRIPT_LIMIT)
            .to_list(length=TRANSCRIPT_LIMIT)
        )
        lines: list[str] = []
        ids: list[str] = []
        for doc in reversed(docs):
            if doc.get("status") == "error":
                continue
            ids.append(str(doc["_id"]))
            seq = doc.get("sequence") or "?"
            if doc["sender_type"] == "agent":
                speaker = doc.get("agent_name") or "Agent"
                provider = doc.get("provider")
                model = doc.get("model")
                if provider or model:
                    speaker = f"{speaker} ({provider or '?'}/{model or '?'})"
                lines.append(f"[#{seq}] {speaker}: {doc['content']}")
            else:
                lines.append(f"[#{seq}] Người dùng: {doc['content']}")
        text = "\n".join(lines)
        if len(text) > TRANSCRIPT_CHARS:
            text = text[-TRANSCRIPT_CHARS:]
        return text, ids

    async def _run_agent(
        self, user_id: UUID, agent_id: UUID, prompt: str, member: dict | None = None
    ) -> dict:
        service = self._agent_service()
        overrides: dict = {}
        if member:
            if member.get("provider_override"):
                overrides["provider_override"] = member["provider_override"]
            if member.get("model_override"):
                overrides["model_override"] = member["model_override"]
            if member.get("system_prompt_override"):
                overrides["system_prompt_override"] = member["system_prompt_override"]
        prepared = await service.prepare_run(
            user_id,
            agent_id,
            RunRequest(prompt=prompt),
            token_budget_override=COLLAB_TOKEN_BUDGET,
            **overrides,
        )
        result: dict = {}
        async for event in service.stream_prepared(prepared):
            if event["event"] == "done":
                result = event["data"]["execution"]
        return result

    @staticmethod
    def _prompt(context: str, instruction: str) -> str:
        return (
            "Bạn đang ở trong một phòng hợp tác cùng người dùng và các Agent khác. "
            "Toàn bộ lịch sử phòng dưới đây là nội dung bạn ĐỌC ĐƯỢC — khi cần, hãy "
            "dựa vào kết quả của Agent khác, nhắc tới tin nhắn bằng mã [#số] của nó, "
            "và đừng nói rằng bạn không nhìn thấy nội dung phòng.\n\n"
            f"Lịch sử phòng (cũ → mới):\n{context}\n\n"
            f"{instruction}"
        )

    @staticmethod
    def _directed_instruction(content: str, reply_target: dict | None) -> str:
        instruction = f"Tin nhắn mới của người dùng:\n{content}"
        if reply_target is not None:
            author = reply_target.get("agent_name") or "Người dùng"
            seq = reply_target.get("sequence") or "?"
            instruction += (
                f"\n\nTin nhắn bạn cần trả lời trực tiếp là [#{seq}] của {author}:\n"
                f"{reply_target['content']}\n"
                "Hãy phản hồi trực tiếp nội dung đó."
            )
        return instruction

    # --- runs & tasks ----------------------------------------------------------
    @staticmethod
    def _run_out(doc) -> RunOut:
        return RunOut(
            id=doc["_id"],
            room_id=doc["room_id"],
            trigger_message_id=doc["trigger_message_id"],
            mode=doc["mode"],
            status=doc["status"],
            turn_count=doc.get("turn_count") or 0,
            max_turns=doc.get("max_turns") or 0,
            total_input_tokens=doc.get("total_input_tokens") or 0,
            total_output_tokens=doc.get("total_output_tokens") or 0,
            stop_reason=doc.get("stop_reason"),
            final_message_id=doc.get("final_message_id"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    @staticmethod
    def _task_out(doc) -> TaskOut:
        return TaskOut(
            id=doc["_id"],
            run_id=doc["run_id"],
            room_id=doc["room_id"],
            agent_id=doc["agent_id"],
            agent_name=doc.get("agent_name"),
            assigned_by=doc["assigned_by"],
            status=doc["status"],
            output_message_id=doc.get("output_message_id"),
            error_code=doc.get("error_code"),
            attempt=doc.get("attempt") or 1,
            input_tokens=doc.get("input_tokens"),
            output_tokens=doc.get("output_tokens"),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    async def _create_run(
        self, user_id: UUID, room_id: UUID, trigger_id: UUID, mode: str, max_turns: int
    ) -> dict:
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "room_id": room_id,
            "trigger_message_id": trigger_id,
            "mode": mode,
            "status": "running",
            "turn_count": 0,
            "max_turns": max_turns,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "stop_reason": None,
            "final_message_id": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.runs.insert_one(doc)
        return doc

    async def _create_task(
        self, user_id: UUID, run_id: UUID, room_id: UUID, agent, assigned_by: str
    ) -> dict:
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "run_id": run_id,
            "room_id": room_id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "assigned_by": assigned_by,
            "status": "running",
            "output_message_id": None,
            "error_code": None,
            "attempt": 1,
            "input_tokens": None,
            "output_tokens": None,
            "created_at": now,
            "updated_at": now,
        }
        await self.tasks.insert_one(doc)
        return doc

    async def _finish_task(self, task: dict, reply: dict) -> None:
        ok = reply.get("status") == "done"
        updates = {
            "status": "completed" if ok else "failed",
            "output_message_id": reply["_id"],
            "error_code": reply.get("error_code"),
            "input_tokens": reply.get("input_tokens"),
            "output_tokens": reply.get("output_tokens"),
            "updated_at": utcnow(),
        }
        await self.tasks.update_one({"_id": task["_id"]}, {"$set": updates})
        task.update(updates)

    async def _close_run(
        self, run: dict, *, status: str, stop_reason: str | None, final_message_id=None
    ) -> dict:
        tasks = await self.tasks.find({"run_id": run["_id"]}).to_list(length=200)
        done = [t for t in tasks if t["status"] in ("completed", "failed")]
        updates = {
            "status": status,
            "stop_reason": stop_reason,
            "turn_count": len(done),
            "total_input_tokens": sum(t.get("input_tokens") or 0 for t in done),
            "total_output_tokens": sum(t.get("output_tokens") or 0 for t in done),
            "updated_at": utcnow(),
        }
        if final_message_id is not None:
            updates["final_message_id"] = final_message_id
        await self.runs.update_one({"_id": run["_id"]}, {"$set": updates})
        run.update(updates)
        return run

    async def _require_run(self, user_id: UUID, run_id: UUID) -> dict:
        doc = await self.runs.find_one({"_id": run_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("collab_run_not_found")
        return doc

    async def _agent_turn(
        self,
        user_id: UUID,
        room_id: UUID,
        agent,
        *,
        run_id: UUID | None,
        assigned_by: str,
        instruction: str,
        reply_link: UUID | None,
        is_summary: bool = False,
        task: dict | None = None,
        member: dict | None = None,
    ) -> dict:
        """One Agent speaking turn: fresh DB context, run, store reply.

        Returns the stored reply doc; ``reply['concluded']`` is set on
        the in-memory copy when the Agent opened with the conclusion
        marker (the marker itself is stripped from the stored text).
        """
        if run_id is not None and task is None:
            task = await self._create_task(user_id, run_id, room_id, agent, assigned_by)
        if member:
            role_bits = [f"Vai trò của bạn trong nhóm: {member.get('role') or 'member'}."]
            if member.get("responsibility"):
                role_bits.append(f"Trách nhiệm: {member['responsibility']}")
            if member.get("instructions"):
                role_bits.append(f"Chỉ dẫn riêng: {member['instructions']}")
            instruction = " ".join(role_bits) + "\n\n" + instruction
        context, context_ids = await self._context(room_id)
        prompt = self._prompt(context, instruction)
        try:
            execution = await self._run_agent(user_id, agent.id, prompt, member=member)
            status = execution.get("status") or "error"
            ok = status == "success"
            content = execution.get("content") or ""
            concluded = ok and content.startswith(CONCLUSION_MARKER)
            if concluded:
                content = content[len(CONCLUSION_MARKER) :].lstrip()
            reply = await self._store_message(
                user_id,
                room_id,
                sender_type="agent",
                agent_id=agent.id,
                agent_name=agent.name,
                provider=execution.get("provider") or agent.provider,
                model=execution.get("model") or agent.model,
                content=content,
                mentions=[],
                sequence=await self._next_sequence(room_id),
                reply_to_message_id=reply_link,
                context_message_ids=context_ids,
                run_id=run_id,
                is_summary=is_summary,
                input_tokens=execution.get("input_tokens"),
                output_tokens=execution.get("output_tokens"),
                status="done" if ok else "error",
                error_code=None if ok else execution.get("error_code"),
                created_at=utcnow(),
            )
            reply["concluded"] = concluded
        except ProviderError as error:
            reply = await self._store_message(
                user_id,
                room_id,
                sender_type="agent",
                agent_id=agent.id,
                agent_name=agent.name,
                provider=agent.provider,
                model=agent.model,
                content="",
                mentions=[],
                sequence=await self._next_sequence(room_id),
                reply_to_message_id=reply_link,
                context_message_ids=context_ids,
                run_id=run_id,
                is_summary=is_summary,
                input_tokens=None,
                output_tokens=None,
                status="error",
                error_code=error.code,
                created_at=utcnow(),
            )
            reply["concluded"] = False
        if task is not None:
            await self._finish_task(task, reply)
        return reply

    async def _set_message_run(self, doc: dict, run_id: UUID) -> None:
        await self.messages.update_one({"_id": doc["_id"]}, {"$set": {"run_id": run_id}})
        doc["run_id"] = run_id

    @staticmethod
    def _pick_next(members, latest_text: str, *, exclude_id, moderator_id):
        """Deterministic auto-discussion router (see ROLE_KEYWORDS)."""
        eligible = [
            a
            for a in members
            if a.id != exclude_id and (moderator_id is None or a.id != moderator_id)
        ]
        if not eligible:
            return None
        text = (latest_text or "").lower()
        best = None
        best_score = 0
        for agent in eligible:
            name = agent.name.lower()
            score = 0
            for role, keywords in ROLE_KEYWORDS.items():
                if role in name:
                    score += sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best, best_score = agent, score
        return best or eligible[0]

    async def _auto_discussion(self, user_id: UUID, room: dict, user_doc: dict):
        room_id = room["_id"]
        max_turns = room.get("max_turns") or 4
        run = await self._create_run(user_id, room_id, user_doc["_id"], "auto", max_turns)
        await self._set_message_run(user_doc, run["_id"])
        summaries = {a.id: a for a in (await self._agent_service().list_agents(user_id)).agents}
        members = [summaries[i] for i in (room.get("agent_ids") or []) if i in summaries]
        snapshot_order = {
            m["agent_id"]: m.get("execution_order")
            for m in (room.get("team_snapshot") or {}).get("members") or []
        }
        if snapshot_order:
            # Team rooms follow the configured execution order wherever
            # the router has no stronger signal.
            members.sort(
                key=lambda a: (snapshot_order.get(a.id) is None, snapshot_order.get(a.id) or 0)
            )
        moderator_id = room.get("moderator_agent_id")
        moderator = summaries.get(moderator_id) if moderator_id else None
        if moderator is not None and moderator.id not in [m.id for m in members]:
            moderator = None
        replies: list[dict] = []
        seen: set[str] = set()
        last_speaker = None
        latest_text = user_doc["content"]
        stop_reason = "turn_limit"
        turns = 0
        while turns < max_turns:
            fresh = await self.runs.find_one({"_id": run["_id"]}, {"status": 1})
            if fresh and fresh.get("status") == "cancelled":
                stop_reason = "cancelled_by_user"
                break
            agent = self._pick_next(
                members, latest_text, exclude_id=last_speaker, moderator_id=moderator_id
            )
            if agent is None:
                stop_reason = "no_eligible_agent"
                break
            reply = await self._agent_turn(
                user_id,
                room_id,
                agent,
                run_id=run["_id"],
                assigned_by="orchestrator",
                instruction=AUTO_INSTRUCTION,
                reply_link=user_doc["_id"],
                member=self._snapshot_member(room, agent.id),
            )
            replies.append(reply)
            turns += 1
            last_speaker = agent.id
            if reply.get("status") == "error":
                continue
            key = " ".join((reply.get("content") or "").lower().split())
            if key in seen:
                stop_reason = "loop_detected"
                break
            seen.add(key)
            latest_text = reply.get("content") or latest_text
            if reply.get("concluded"):
                stop_reason = "agent_concluded"
                break
        final_id = None
        synthesizer = moderator
        if synthesizer is None and turns > 0:
            # Rooms created without a Moderator still deserve a conclusion:
            # the lineup's Leader/coordinator (per the frozen snapshot when
            # there is one), otherwise the first member who did not speak
            # last, delivers the synthesis — instead of the run ending bare
            # at the turn limit with final_message_id null.
            ordered = []
            for candidate in members:
                snap = self._snapshot_member(room, candidate.id) or {}
                if (snap.get("role") or "").lower() in ("leader", "coordinator"):
                    ordered.append(candidate)
            ordered.extend(members)
            synthesizer = next(
                (c for c in ordered if c.id != last_speaker), None
            ) or (ordered[0] if ordered else None)
        if synthesizer is not None and turns > 0 and (
            last_speaker != synthesizer.id or len(members) == 1
        ):
            reply = await self._agent_turn(
                user_id,
                room_id,
                synthesizer,
                run_id=run["_id"],
                assigned_by="moderator",
                instruction=SUMMARY_INSTRUCTION,
                reply_link=user_doc["_id"],
                is_summary=True,
                member=self._snapshot_member(room, synthesizer.id),
            )
            replies.append(reply)
            if reply.get("status") == "done":
                final_id = reply["_id"]
            if stop_reason == "turn_limit":
                stop_reason = "moderator_summarized"
        status = "cancelled" if stop_reason == "cancelled_by_user" else "completed"
        await self._close_run(
            run, status=status, stop_reason=stop_reason, final_message_id=final_id
        )
        return run, replies

    async def post_message(self, user_id: UUID, room_id: UUID, payload: MessageIn) -> PostResult:
        room = await self._require_room(user_id, room_id)
        member_ids = list(room.get("agent_ids") or [])
        mentions = list(dict.fromkeys(payload.mention_agent_ids))
        if any(agent_id not in member_ids for agent_id in mentions):
            raise ProviderError("collab_agent_not_member")

        reply_target = None
        if payload.reply_to_message_id is not None:
            reply_target = await self.messages.find_one(
                {
                    "_id": payload.reply_to_message_id,
                    "room_id": room_id,
                    "user_id": user_id,
                }
            )
            if reply_target is None:
                raise ProviderError("collab_message_not_found")

        user_doc = await self._store_message(
            user_id,
            room_id,
            sender_type="user",
            agent_id=None,
            agent_name=None,
            provider=None,
            model=None,
            content=payload.content,
            mentions=[str(agent_id) for agent_id in mentions],
            sequence=await self._next_sequence(room_id),
            reply_to_message_id=payload.reply_to_message_id,
            context_message_ids=[],
            run_id=None,
            is_summary=False,
            input_tokens=None,
            output_tokens=None,
            status="done",
            error_code=None,
            created_at=utcnow(),
        )
        created = [self._message_out(user_doc)]
        run = None
        if mentions:
            run = await self._create_run(
                user_id, room_id, user_doc["_id"], "directed", len(mentions)
            )
            await self._set_message_run(user_doc, run["_id"])
            created[0] = self._message_out(user_doc)
            summaries = {
                a.id: a for a in (await self._agent_service().list_agents(user_id)).agents
            }
            instruction = self._directed_instruction(payload.content, reply_target)
            reply_link = payload.reply_to_message_id or user_doc["_id"]
            failed = 0
            for agent_id in mentions:
                agent = summaries.get(agent_id)
                if agent is None:
                    continue
                reply = await self._agent_turn(
                    user_id,
                    room_id,
                    agent,
                    run_id=run["_id"],
                    assigned_by="user",
                    instruction=instruction,
                    reply_link=reply_link,
                    member=self._snapshot_member(room, agent_id),
                )
                if reply.get("status") == "error":
                    failed += 1
                created.append(self._message_out(reply))
            status = "failed" if failed and failed == len(mentions) else "completed"
            stop = "all_agents_failed" if status == "failed" else None
            await self._close_run(run, status=status, stop_reason=stop)
        elif (room.get("mode") or "directed") == "auto" and member_ids:
            run, replies = await self._auto_discussion(user_id, room, user_doc)
            created[0] = self._message_out(user_doc)
            created.extend(self._message_out(reply) for reply in replies)
        return PostResult(
            messages=created, run=self._run_out(run) if run is not None else None
        )

    # --- run queries / control ---------------------------------------------------
    async def list_runs(self, user_id: UUID, room_id: UUID) -> RunList:
        await self._require_room(user_id, room_id)
        docs = (
            await self.runs.find({"room_id": room_id, "user_id": user_id})
            .sort("created_at", -1)
            .limit(50)
            .to_list(length=50)
        )
        return RunList(runs=[self._run_out(doc) for doc in docs])

    async def get_run(self, user_id: UUID, run_id: UUID) -> RunDetail:
        run = await self._require_run(user_id, run_id)
        tasks = (
            await self.tasks.find({"run_id": run_id, "user_id": user_id})
            .sort("created_at", 1)
            .to_list(length=200)
        )
        return RunDetail(run=self._run_out(run), tasks=[self._task_out(t) for t in tasks])

    async def cancel_run(self, user_id: UUID, run_id: UUID) -> RunOut:
        run = await self._require_run(user_id, run_id)
        if run["status"] == "running":
            updates = {
                "status": "cancelled",
                "stop_reason": "cancelled_by_user",
                "updated_at": utcnow(),
            }
            await self.runs.update_one({"_id": run_id}, {"$set": updates})
            run.update(updates)
        return self._run_out(run)

    async def retry_run(self, user_id: UUID, run_id: UUID) -> RunDetail:
        run = await self._require_run(user_id, run_id)
        await self._require_room(user_id, run["room_id"])
        failed = (
            await self.tasks.find({"run_id": run_id, "user_id": user_id, "status": "failed"})
            .sort("created_at", 1)
            .to_list(length=50)
        )
        if not failed:
            raise ProviderError("collab_nothing_to_retry")
        summaries = {a.id: a for a in (await self._agent_service().list_agents(user_id)).agents}
        for task in failed:
            agent = summaries.get(task["agent_id"])
            if agent is None:
                continue
            await self.tasks.update_one(
                {"_id": task["_id"]},
                {
                    "$set": {
                        "status": "running",
                        "attempt": (task.get("attempt") or 1) + 1,
                        "updated_at": utcnow(),
                    }
                },
            )
            task["attempt"] = (task.get("attempt") or 1) + 1
            await self._agent_turn(
                user_id,
                run["room_id"],
                agent,
                run_id=run_id,
                assigned_by=task["assigned_by"],
                instruction=RETRY_INSTRUCTION,
                reply_link=run["trigger_message_id"],
                task=task,
            )
        remaining = await self.tasks.count_documents({"run_id": run_id, "status": "failed"})
        if run["status"] == "failed" and remaining == 0:
            await self._close_run(run, status="completed", stop_reason=None)
        else:
            await self._close_run(run, status=run["status"], stop_reason=run.get("stop_reason"))
        return await self.get_run(user_id, run_id)

    async def summarize(
        self, user_id: UUID, room_id: UUID, payload: SummarizeIn
    ) -> CollabMessageOut:
        room = await self._require_room(user_id, room_id)
        member_ids = list(room.get("agent_ids") or [])
        if not member_ids:
            raise ProviderError("collab_no_agents")
        summaries = {a.id: a for a in (await self._agent_service().list_agents(user_id)).agents}
        chosen = None
        if payload.agent_id is not None:
            if payload.agent_id not in member_ids:
                raise ProviderError("collab_agent_not_member")
            chosen = summaries.get(payload.agent_id)
        if chosen is None and room.get("moderator_agent_id") is not None:
            chosen = summaries.get(room["moderator_agent_id"])
        if chosen is None:
            chosen = next((summaries[i] for i in member_ids if i in summaries), None)
        if chosen is None:
            raise ProviderError("collab_no_agents")
        reply = await self._agent_turn(
            user_id,
            room_id,
            chosen,
            run_id=None,
            assigned_by="moderator",
            instruction=SUMMARY_INSTRUCTION,
            reply_link=None,
            is_summary=True,
            member=self._snapshot_member(room, chosen.id),
        )
        return self._message_out(reply)

    # --- artifacts & export ------------------------------------------------------
    @staticmethod
    def _artifact_out(doc) -> ArtifactOut:
        return ArtifactOut(
            id=doc["_id"],
            room_id=doc["room_id"],
            run_id=doc.get("run_id"),
            name=doc["name"],
            kind=doc["kind"],
            mime_type=doc["mime_type"],
            size=doc["size"],
            checksum=doc["checksum"],
            created_at=doc["created_at"],
        )

    async def _store_artifact(
        self, user_id, room_id, run_id, *, name, kind, mime_type, data: bytes, text: bool
    ) -> dict:
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "room_id": room_id,
            "run_id": run_id,
            "name": name,
            "kind": kind,
            "mime_type": mime_type,
            "size": len(data),
            "checksum": hashlib.sha256(data).hexdigest(),
            "content_text": data.decode("utf-8") if text else None,
            "content_b64": None if text else base64.b64encode(data).decode("ascii"),
            "created_at": utcnow(),
        }
        await self.artifacts.insert_one(doc)
        return doc

    @staticmethod
    def _report_markdown(room: dict, messages: list[dict], runs: list[dict]) -> str:
        summary = next(
            (m for m in reversed(messages) if m.get("is_summary") and m.get("status") != "error"),
            None,
        )
        agents: list[str] = []
        for message in messages:
            if message["sender_type"] == "agent" and message.get("agent_name"):
                label = message["agent_name"]
                if label not in agents:
                    agents.append(label)
        lines = [
            f"# Báo cáo phòng hợp tác: {room['title']}",
            "",
            f"- Số tin nhắn: {len(messages)}",
            f"- Số lượt chạy (run): {len(runs)}",
            f"- Agent đã tham gia: {', '.join(agents) if agents else '—'}",
            "",
            "## Kết luận cuối cùng",
            "",
            summary["content"]
            if summary is not None
            else "Chưa có bản tổng hợp. Hãy yêu cầu Moderator tổng hợp trong phòng.",
            "",
            "## Thống kê lượt chạy",
            "",
        ]
        for run in runs:
            lines.append(
                f"- Run {run['_id']}: {run['mode']}, trạng thái {run['status']}, "
                f"{run.get('turn_count') or 0} lượt, "
                f"token vào {run.get('total_input_tokens') or 0} / "
                f"ra {run.get('total_output_tokens') or 0}, "
                f"lý do dừng: {run.get('stop_reason') or '—'}"
            )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _transcript_markdown(room: dict, messages: list[dict]) -> str:
        lines = [f"# Lịch sử thảo luận — {room['title']}", ""]
        for message in messages:
            seq = message.get("sequence") or "?"
            if message["sender_type"] == "agent":
                who = message.get("agent_name") or "Agent"
                provider = message.get("provider")
                model = message.get("model")
                if provider or model:
                    who = f"{who} ({provider or '?'}/{model or '?'})"
            else:
                who = "Người dùng"
            lines.append(f"## [#{seq}] {who}")
            lines.append("")
            if message.get("status") == "error":
                lines.append(f"⚠ Lượt trả lời thất bại: {message.get('error_code') or 'unknown'}")
            else:
                lines.append(message["content"])
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _agent_results(messages: list[dict]) -> dict[str, str]:
        grouped: dict[str, list[dict]] = {}
        for message in messages:
            if message["sender_type"] == "agent" and message.get("status") != "error":
                grouped.setdefault(message.get("agent_name") or "Agent", []).append(message)
        files: dict[str, str] = {}
        for name, items in grouped.items():
            slug = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")
            body = "\n\n".join(
                f"## Lượt {item.get('sequence') or '?'}\n\n{item['content']}" for item in items
            )
            files[f"agent-results/{slug or 'agent'}.md"] = f"# Kết quả của {name}\n\n{body}\n"
        return files

    async def export_room(self, user_id: UUID, room_id: UUID, payload: ExportIn) -> ExportResult:
        room = await self._require_room(user_id, room_id)
        query: dict = {"room_id": room_id, "user_id": user_id}
        if payload.run_id is not None:
            run = await self.runs.find_one(
                {"_id": payload.run_id, "room_id": room_id, "user_id": user_id}
            )
            if run is None:
                raise ProviderError("collab_run_not_found")
            query["run_id"] = payload.run_id
        messages = (
            await self.messages.find(query).sort("created_at", 1).to_list(length=2000)
        )
        runs = (
            await self.runs.find({"room_id": room_id, "user_id": user_id})
            .sort("created_at", 1)
            .to_list(length=200)
        )
        if payload.run_id is not None:
            runs = [r for r in runs if r["_id"] == payload.run_id]
        report = self._report_markdown(room, messages, runs)
        transcript = self._transcript_markdown(room, messages)
        results = {
            "room": {"id": str(room_id), "title": room["title"], "mode": room.get("mode")},
            "exported_at": utcnow().isoformat(),
            "messages": [self._message_out(m).model_dump(mode="json") for m in messages],
            "runs": [self._run_out(r).model_dump(mode="json") for r in runs],
        }
        results_text = json.dumps(results, ensure_ascii=False, indent=2)
        created: list[dict] = []
        run_id = payload.run_id
        if "md" in payload.formats:
            created.append(
                await self._store_artifact(
                    user_id, room_id, run_id,
                    name="FINAL-REPORT.md", kind="report",
                    mime_type="text/markdown", data=report.encode("utf-8"), text=True,
                )
            )
            created.append(
                await self._store_artifact(
                    user_id, room_id, run_id,
                    name="discussion-transcript.md", kind="transcript",
                    mime_type="text/markdown", data=transcript.encode("utf-8"), text=True,
                )
            )
        if "json" in payload.formats:
            created.append(
                await self._store_artifact(
                    user_id, room_id, run_id,
                    name="results.json", kind="results",
                    mime_type="application/json", data=results_text.encode("utf-8"), text=True,
                )
            )
        if "zip" in payload.formats:
            files: dict[str, bytes] = {
                "README.md": (
                    f"# Gói bàn giao phòng hợp tác: {room['title']}\n\n"
                    "Gói này chứa báo cáo tổng hợp, toàn bộ lịch sử thảo luận đã chọn, "
                    "kết quả theo từng Agent và manifest kiểm chứng. "
                    "Không chứa API key hay dữ liệu bí mật.\n"
                ).encode("utf-8"),
                "FINAL-REPORT.md": report.encode("utf-8"),
                "discussion-transcript.md": transcript.encode("utf-8"),
                "results.json": results_text.encode("utf-8"),
            }
            for path, text in self._agent_results(messages).items():
                files[path] = text.encode("utf-8")
            manifest = {
                "room_id": str(room_id),
                "generated_at": utcnow().isoformat(),
                "files": [
                    {
                        "name": name,
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                    for name, data in sorted(files.items())
                ],
            }
            files["manifest.json"] = json.dumps(
                manifest, ensure_ascii=False, indent=2
            ).encode("utf-8")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
            created.append(
                await self._store_artifact(
                    user_id, room_id, run_id,
                    name="mindflow-collab-export.zip", kind="package",
                    mime_type="application/zip", data=buffer.getvalue(), text=False,
                )
            )
        return ExportResult(artifacts=[self._artifact_out(doc) for doc in created])

    async def list_artifacts(self, user_id: UUID, room_id: UUID) -> ArtifactList:
        await self._require_room(user_id, room_id)
        docs = (
            await self.artifacts.find({"room_id": room_id, "user_id": user_id})
            .sort("created_at", -1)
            .limit(100)
            .to_list(length=100)
        )
        return ArtifactList(artifacts=[self._artifact_out(doc) for doc in docs])

    async def download_artifact(self, user_id: UUID, artifact_id: UUID) -> tuple[bytes, str, str]:
        doc = await self.artifacts.find_one({"_id": artifact_id, "user_id": user_id})
        if doc is None:
            raise ProviderError("collab_artifact_not_found")
        if doc.get("content_b64"):
            data = base64.b64decode(doc["content_b64"])
        else:
            data = (doc.get("content_text") or "").encode("utf-8")
        return data, doc["name"], doc["mime_type"]

    async def delete_artifact(self, user_id: UUID, artifact_id: UUID) -> None:
        result = await self.artifacts.delete_one({"_id": artifact_id, "user_id": user_id})
        if result.deleted_count == 0:
            raise ProviderError("collab_artifact_not_found")
