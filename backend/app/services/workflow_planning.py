"""Dynamic planning for multi-agent workflows (Task Analysis,
Decomposition and Agent Selection).

One Leader agent drafts the plan as JSON; this service validates it
tolerantly and then applies the guarantees the model cannot be trusted
with:

- the agent count is snapped to {1, 2, 3, 5}; in manual mode a mismatch
  with the recommendation becomes an explicit warning, never a silent
  override;
- task keys are re-issued as t1..tn, dependency edges are remapped,
  unknown/self/cyclic edges are dropped, waves are computed, and a task
  is marked parallelizable only when another task shares its wave;
- the lineup is matched against the user's REAL agents (role inferred
  from the agent's name exactly like the orchestrator does); a role
  with no agent stays empty and produces a warning instead of a fake
  assignment;
- human suggestions come from the Workforce resources with a plain
  skill-overlap score — informational only, the workflow itself is
  executed by agents.
"""

import json
import logging
import re
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from app.core.config import Settings
from app.repositories.agents import AgentRepository
from app.schemas.workflows import (
    PLAN_COUNTS,
    PlanApplyIn,
    PlanApplyOut,
    PlanDraft,
    PlanHumanSuggestion,
    PlanLineupItem,
    PlanOut,
    PlanRequest,
    PlanTaskOut,
    TeamCreate,
    TeamMemberIn,
    WorkflowCreate,
)
from app.services.ai.base_provider import ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.workflows import WorkflowService, effective_role

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """[PLAN_REQUEST]
Bạn là AI Leader của một hệ thống điều phối nhiều Agent. Hãy phân tích
yêu cầu công việc dưới đây và lập kế hoạch thực thi.

Tiêu đề: {title}
Yêu cầu: {goal}
{answers_block}
Trả về DUY NHẤT một JSON đúng cấu trúc sau, không thêm chữ nào ngoài JSON:
{{"summary": "tóm tắt mục tiêu và cách tiếp cận",
"complexity": "low|medium|high|critical",
"skills_required": ["kỹ năng"], "assumptions": ["giả định"],
"missing_info": ["thông tin còn thiếu"],
"clarifying_questions": ["câu hỏi cần người dùng trả lời"],
"acceptance_criteria": ["tiêu chí nghiệm thu chung"],
"recommended_agent_count": 1,
"count_reason": "vì sao chọn số Agent này",
"tasks": [{{"key": "t1", "title": "tên task",
"description": "mô tả việc cần làm",
"expected_output": "đầu ra mong đợi",
"skills_required": ["kỹ năng"], "priority": "low|normal|high",
"difficulty": "low|medium|high", "depends_on": ["t1"],
"suggested_role": "planner|architect|researcher|developer|tester|reviewer|evaluator|member",
"acceptance_criteria": ["tiêu chí nghiệm thu của task"]}}]}}

Nguyên tắc bắt buộc:
- Số Agent chỉ chọn một trong 1, 2, 3, 5. Việc đơn giản một chuyên môn:
1 Agent. Tách được phần thực hiện và phần review, hoặc hai phần việc
độc lập: 2. Cần lập kế hoạch/kiến trúc + thực hiện + kiểm tra: 3. Chỉ
dùng 5 khi có nhiều luồng công việc hoặc chuyên môn độc lập thật sự.
Không dùng nhiều Agent cho có.
- Chia 2-10 task; mỗi task phải giao, theo dõi và nghiệm thu độc lập
được, có đầu ra rõ ràng. Không chia vụn máy móc.
- depends_on chỉ liệt kê key của các task phải xong trước; task không
phụ thuộc thì để mảng rỗng (chạy song song được).
- Nếu yêu cầu thiếu thông tin quan trọng, ghi vào clarifying_questions
và missing_info thay vì tự bịa dữ kiện."""


def snap_count(value: int) -> int:
    """Snap any model-suggested count to the allowed {1, 2, 3, 5} set,
    preferring the cheaper option on ties."""
    count = max(1, min(99, int(value or 1)))
    return min(PLAN_COUNTS, key=lambda allowed: (abs(allowed - count), allowed))


def parse_plan(text: str) -> PlanDraft:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        logger.warning("Plan parse failed (no JSON object): %.800s", text)
        raise ProviderError("analysis_invalid_response")
    candidate = re.sub(r",\s*([}\]])", r"\1", cleaned[start : end + 1])
    try:
        return PlanDraft.model_validate(json.loads(candidate))
    except (json.JSONDecodeError, ValidationError):
        logger.warning("Plan parse failed (invalid draft): %.800s", text)
        raise ProviderError("analysis_invalid_response") from None


def _process_tasks(draft_tasks) -> list[PlanTaskOut]:
    """Re-issue keys, remap + sanitize dependencies, compute waves."""
    keys = [f"t{i + 1}" for i in range(len(draft_tasks))]
    old_to_new: dict[str, str] = {}
    for task, new_key in zip(draft_tasks, keys, strict=True):
        if task.key and task.key not in old_to_new:
            old_to_new[task.key] = new_key
    deps: dict[str, list[str]] = {}
    for task, new_key in zip(draft_tasks, keys, strict=True):
        mapped = []
        for dep in task.depends_on:
            target = old_to_new.get(dep)
            if target and target != new_key and target not in mapped:
                mapped.append(target)
        deps[new_key] = mapped
    # Drop edges that would close a cycle, in task order.
    kept: dict[str, list[str]] = {key: [] for key in keys}

    def reaches(source: str, target: str) -> bool:
        stack, seen = [source], set()
        while stack:
            node = stack.pop()
            if node == target:
                return True
            if node not in seen:
                seen.add(node)
                stack.extend(kept.get(node, []))
        return False

    for key in keys:
        for dep in deps[key]:
            if not reaches(dep, key):
                kept[key].append(dep)
    waves: dict[str, int] = {}

    def wave(key: str) -> int:
        if key not in waves:
            waves[key] = 0 if not kept[key] else 1 + max(wave(dep) for dep in kept[key])
        return waves[key]

    for key in keys:
        wave(key)
    wave_sizes: dict[int, int] = {}
    for key in keys:
        wave_sizes[waves[key]] = wave_sizes.get(waves[key], 0) + 1
    return [
        PlanTaskOut(
            key=new_key,
            title=task.title,
            description=task.description,
            expected_output=task.expected_output,
            skills_required=task.skills_required,
            priority=task.priority,
            difficulty=task.difficulty,
            depends_on=kept[new_key],
            parallelizable=wave_sizes[waves[new_key]] > 1,
            wave=waves[new_key],
            suggested_role=task.suggested_role,
            acceptance_criteria=task.acceptance_criteria,
        )
        for task, new_key in zip(draft_tasks, keys, strict=True)
    ]


def _build_lineup(tasks, chosen, pool):
    """Group tasks into `chosen` execution slots and match real agents.

    Slots start as one per distinct suggested role; they are split
    (largest group first) or merged (smallest groups last) to hit the
    chosen count. Agents are matched by their inferred role, then by
    availability; an unmatched slot keeps agent_id=None.
    """
    groups: list[dict] = []
    by_role: dict[str, dict] = {}
    for task in tasks:
        group = by_role.get(task.suggested_role)
        if group is None:
            group = {"role": task.suggested_role, "task_keys": []}
            by_role[task.suggested_role] = group
            groups.append(group)
        group["task_keys"].append(task.key)
    while len(groups) < chosen:
        biggest = max(groups, key=lambda g: len(g["task_keys"]), default=None)
        if biggest is None or len(biggest["task_keys"]) < 2:
            break
        half = len(biggest["task_keys"]) // 2
        groups.append(
            {"role": biggest["role"], "task_keys": biggest["task_keys"][half:]}
        )
        biggest["task_keys"] = biggest["task_keys"][:half]
    while len(groups) > chosen and len(groups) > 1:
        merged = groups.pop()
        groups[-1]["task_keys"].extend(merged["task_keys"])
    used: set[UUID] = set()
    lineup: list[PlanLineupItem] = []
    warnings: list[str] = []
    for group in groups:
        match = None
        for agent in pool:
            if agent.id not in used and effective_role("member", agent.name) == group["role"]:
                match = agent
                break
        if match is None:
            for agent in pool:
                if agent.id not in used:
                    match = agent
                    break
        if match is None:
            warnings.append(
                f"Chưa có Agent trống cho vai trò {group['role']} — "
                "hãy tạo thêm Agent hoặc giảm số Agent trong kế hoạch."
            )
            lineup.append(PlanLineupItem(role=group["role"], task_keys=group["task_keys"]))
            continue
        used.add(match.id)
        lineup.append(
            PlanLineupItem(
                role=group["role"],
                agent_id=match.id,
                agent_name=match.name,
                provider=match.provider,
                model=match.model,
                task_keys=group["task_keys"],
            )
        )
    return lineup, warnings


class PlanningService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        chat_http: ChatHTTP | None = None,
    ):
        self.db = db
        self.settings = settings
        self.chat_http = chat_http
        self.agents = AgentRepository(db)

    def _workflows(self) -> WorkflowService:
        return WorkflowService(self.db, self.settings, self.chat_http)

    async def analyze(self, user_id: UUID, payload: PlanRequest) -> PlanOut:
        leader = await self.agents.get_agent(user_id, payload.agent_id)
        if leader is None:
            raise ProviderError("agent_not_found")
        answers_block = ""
        if payload.answers and payload.answers.strip():
            answers_block = (
                "\nThông tin bổ sung từ người dùng (dùng để thay thế các "
                f"giả định): {payload.answers.strip()}\n"
            )
        prompt = PLANNER_PROMPT.format(
            title=payload.title, goal=payload.goal, answers_block=answers_block
        )
        content, usage = await self._workflows()._run_agent_resilient(
            user_id, payload.agent_id, prompt, max_output_tokens=8192
        )
        draft = parse_plan(content)
        tasks = _process_tasks(draft.tasks)
        recommended = snap_count(draft.recommended_agent_count)
        chosen = payload.agent_count if payload.mode == "manual" else recommended
        if chosen is None:
            chosen = recommended
        warnings: list[str] = []
        if payload.mode == "manual" and chosen != recommended:
            warnings.append(
                f"Bạn chọn {chosen} Agent nhưng phân tích đề xuất {recommended} Agent. "
                f"Lý do của AI Leader: {draft.count_reason or 'không nêu rõ'}. "
                "Kế hoạch vẫn dùng số bạn chọn; cân nhắc lại nếu chi phí/lợi ích chưa hợp lý."
            )
        if draft.clarifying_questions and not payload.answers:
            warnings.append(
                "Kế hoạch còn câu hỏi cần làm rõ — nên trả lời ở ô thông tin bổ sung "
                "rồi lập kế hoạch lại trước khi chạy."
            )
        pool = [
            agent
            for agent in await self.agents.list_agents(user_id)
            if agent.id != payload.agent_id
        ]
        lineup, lineup_warnings = _build_lineup(tasks, chosen, pool)
        warnings.extend(lineup_warnings)
        return PlanOut(
            title=payload.title,
            goal=payload.goal,
            summary=draft.summary,
            complexity=draft.complexity,
            skills_required=draft.skills_required,
            assumptions=draft.assumptions,
            missing_info=draft.missing_info,
            clarifying_questions=draft.clarifying_questions,
            acceptance_criteria=draft.acceptance_criteria,
            mode=payload.mode,
            recommended_agent_count=recommended,
            chosen_agent_count=chosen,
            count_reason=draft.count_reason,
            warnings=warnings,
            tasks=tasks,
            lineup=lineup,
            human_suggestions=await self._human_suggestions(user_id, tasks),
            leader_agent_id=payload.agent_id,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )

    async def _human_suggestions(self, user_id, tasks) -> list[PlanHumanSuggestion]:
        """Informational matches from the Workforce module: humans whose
        skills overlap a task's required skills. Execution stays with
        agents; this only surfaces people a manager may assign in
        parallel (see the /projects allocation flow)."""
        cursor = self.db.resources.find({"user_id": user_id, "type": "human"})
        humans = [doc async for doc in cursor]
        suggestions: list[PlanHumanSuggestion] = []
        for task in tasks:
            wanted = {skill.strip().lower() for skill in task.skills_required if skill}
            if not wanted:
                continue
            scored = []
            for doc in humans:
                if doc.get("availability_status") == "unavailable":
                    continue
                matched = sum(
                    int(skill.get("level") or 0)
                    for skill in doc.get("skills") or []
                    if str(skill.get("name") or "").strip().lower() in wanted
                )
                if matched:
                    scored.append((matched / (5 * len(wanted)) * 100, doc))
            scored.sort(key=lambda item: item[0], reverse=True)
            for score, doc in scored[:2]:
                suggestions.append(
                    PlanHumanSuggestion(
                        task_key=task.key,
                        resource_id=str(doc["_id"]),
                        name=str(doc.get("name") or ""),
                        role=doc.get("role"),
                        score=round(score, 1),
                    )
                )
        return suggestions

    async def apply(self, user_id: UUID, payload: PlanApplyIn) -> PlanApplyOut:
        plan = payload.plan
        workflows = self._workflows()
        members = [TeamMemberIn(agent_id=plan.leader_agent_id, role="coordinator")]
        seen = {plan.leader_agent_id}
        for item in plan.lineup:
            if item.agent_id is None or item.agent_id in seen:
                continue
            seen.add(item.agent_id)
            members.append(TeamMemberIn(agent_id=item.agent_id, role=item.role))
        team_name = payload.team_name or f"Đội cho: {plan.title}"
        team = await workflows.create_team(
            user_id,
            TeamCreate(
                name=team_name[:120],
                description=f"Đội hình từ kế hoạch AI cho: {plan.title}"[:2000],
                coordinator_agent_id=plan.leader_agent_id,
                members=members,
            ),
        )
        lines = [plan.goal, "", "KẾ HOẠCH ĐÃ ĐƯỢC NGƯỜI DÙNG DUYỆT:"]
        for task in plan.tasks:
            deps = f" (sau: {', '.join(task.depends_on)})" if task.depends_on else ""
            lines.append(
                f"- [{task.suggested_role}] {task.title}{deps}: {task.description}"
            )
            if task.expected_output:
                lines.append(f"  Đầu ra: {task.expected_output}")
            if task.acceptance_criteria:
                lines.append(f"  Nghiệm thu: {'; '.join(task.acceptance_criteria)}")
        workflow = await workflows.create_workflow(
            user_id,
            WorkflowCreate(
                team_id=team.id,
                title=plan.title,
                goal="\n".join(lines)[:32000],
                output_type=payload.output_type,
                requires_approval=payload.requires_approval,
                plan=plan.model_dump(mode="json"),
            ),
        )
        return PlanApplyOut(team=team, workflow=workflow)
