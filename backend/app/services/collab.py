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

from uuid import UUID, uuid4

from app.models.base import utcnow
from app.schemas.agents import RunRequest
from app.schemas.collab import (
    CollabMessageOut,
    MessageIn,
    PostResult,
    RoomAgentOut,
    RoomCreate,
    RoomList,
    RoomOut,
    RoomPatch,
)
from app.services.agents import AgentService
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP

ROOMS = "multi_chats"
MESSAGES = "collab_messages"
TRANSCRIPT_LIMIT = 20
TRANSCRIPT_CHARS = 12000
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
            agent_ids=list(doc.get("agent_ids") or []),
            agents=agents,
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
    async def create_room(self, user_id: UUID, payload: RoomCreate) -> RoomOut:
        await self._validate_agents(user_id, payload.agent_ids)
        now = utcnow()
        doc = {
            "_id": uuid4(),
            "user_id": user_id,
            "title": payload.title,
            "conversation_ids": [],
            "agent_ids": list(dict.fromkeys(payload.agent_ids)),
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
        updates: dict = {"updated_at": utcnow()}
        if payload.title is not None:
            updates["title"] = payload.title
        if payload.agent_ids is not None:
            await self._validate_agents(user_id, payload.agent_ids)
            updates["agent_ids"] = list(dict.fromkeys(payload.agent_ids))
        await self.rooms.update_one({"_id": room_id}, {"$set": updates})
        doc.update(updates)
        return await self._room_out(user_id, doc)

    async def delete_room(self, user_id: UUID, room_id: UUID) -> None:
        await self._require_room(user_id, room_id)
        await self.rooms.delete_one({"_id": room_id, "user_id": user_id})
        await self.messages.delete_many({"room_id": room_id, "user_id": user_id})

    # --- messages --------------------------------------------------------------
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

    async def _run_agent(self, user_id: UUID, agent_id: UUID, prompt: str) -> dict:
        service = self._agent_service()
        prepared = await service.prepare_run(
            user_id,
            agent_id,
            RunRequest(prompt=prompt),
            token_budget_override=COLLAB_TOKEN_BUDGET,
        )
        result: dict = {}
        async for event in service.stream_prepared(prepared):
            if event["event"] == "done":
                result = event["data"]["execution"]
        return result

    @staticmethod
    def _prompt(context: str, content: str, reply_target: dict | None) -> str:
        prompt = (
            "Bạn đang ở trong một phòng hợp tác cùng người dùng và các Agent khác. "
            "Toàn bộ lịch sử phòng dưới đây là nội dung bạn ĐỌC ĐƯỢC — khi cần, hãy "
            "dựa vào kết quả của Agent khác, nhắc tới tin nhắn bằng mã [#số] của nó, "
            "và đừng nói rằng bạn không nhìn thấy nội dung phòng.\n\n"
            f"Lịch sử phòng (cũ → mới):\n{context}\n\n"
            f"Tin nhắn mới của người dùng:\n{content}"
        )
        if reply_target is not None:
            author = reply_target.get("agent_name") or "Người dùng"
            seq = reply_target.get("sequence") or "?"
            prompt += (
                f"\n\nTin nhắn bạn cần trả lời trực tiếp là [#{seq}] của {author}:\n"
                f"{reply_target['content']}\n"
                "Hãy phản hồi trực tiếp nội dung đó."
            )
        return prompt

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
            input_tokens=None,
            output_tokens=None,
            status="done",
            error_code=None,
            created_at=utcnow(),
        )
        created = [self._message_out(user_doc)]
        if not mentions:
            return PostResult(messages=created)

        summaries = {a.id: a for a in (await self._agent_service().list_agents(user_id)).agents}
        reply_link = payload.reply_to_message_id or user_doc["_id"]
        for agent_id in mentions:
            agent = summaries.get(agent_id)
            # Rebuild the context from the database for THIS agent: it
            # includes the new user message and every reply the agents
            # mentioned before it in this same post have just stored.
            context, context_ids = await self._context(room_id)
            prompt = self._prompt(context, payload.content, reply_target)
            try:
                execution = await self._run_agent(user_id, agent_id, prompt)
                status = execution.get("status") or "error"
                reply = await self._store_message(
                    user_id,
                    room_id,
                    sender_type="agent",
                    agent_id=agent_id,
                    agent_name=agent.name if agent else None,
                    provider=agent.provider if agent else None,
                    model=agent.model if agent else None,
                    content=execution.get("content") or "",
                    mentions=[],
                    sequence=await self._next_sequence(room_id),
                    reply_to_message_id=reply_link,
                    context_message_ids=context_ids,
                    input_tokens=execution.get("input_tokens"),
                    output_tokens=execution.get("output_tokens"),
                    status="done" if status == "success" else "error",
                    error_code=None if status == "success" else execution.get("error_code"),
                    created_at=utcnow(),
                )
            except ProviderError as error:
                reply = await self._store_message(
                    user_id,
                    room_id,
                    sender_type="agent",
                    agent_id=agent_id,
                    agent_name=agent.name if agent else None,
                    provider=agent.provider if agent else None,
                    model=agent.model if agent else None,
                    content="",
                    mentions=[],
                    sequence=await self._next_sequence(room_id),
                    reply_to_message_id=reply_link,
                    context_message_ids=context_ids,
                    input_tokens=None,
                    output_tokens=None,
                    status="error",
                    error_code=error.code,
                    created_at=utcnow(),
                )
            created.append(self._message_out(reply))
        return PostResult(messages=created)
