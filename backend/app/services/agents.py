import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from bson import BSON
from bson.errors import InvalidDocument
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import SecretStr

from app.core.config import Settings
from app.core.credential_vault import CredentialVault
from app.models import Agent, AgentExecution, AIModel
from app.models.entities import AgentStep, AgentToolCall
from app.repositories.agents import AgentRepository
from app.repositories.chat import ChatRepository
from app.repositories.providers import ProviderRepository
from app.schemas.agents import (
    AgentCreate,
    AgentDetail,
    AgentList,
    AgentPatch,
    AgentStepOut,
    AgentSummary,
    AgentToolCallOut,
    ExecutionDetail,
    ExecutionList,
    ExecutionSummary,
    RunRequest,
    ToolCatalog,
    ToolCatalogItem,
    ToolExecutionOut,
)
from app.services.ai.ai_factory import create_provider
from app.services.ai.base_provider import ERRORS, BaseProvider, ProviderError
from app.services.ai.chat import ChatHTTP
from app.services.ai.chat_types import ChatRequest, ChatTurn, ToolCall, ToolSpec
from app.services.ai.registry import get_provider
from app.services.ai.tools import (
    MAX_RESULT_CHARS,
    TOOL_REGISTRY,
    ToolError,
    execute_tool,
    is_tool_allowed,
    tool_catalog,
)
from app.services.compare import _elapsed_ms, _estimate_cost


@dataclass(frozen=True)
class AgentLimits:
    """Hard safety budgets for one execution; not user-configurable."""

    max_steps: int = 6
    deadline_seconds: float = 120.0
    token_budget: int = 8000
    tool_timeout_seconds: float = 10.0
    max_tool_calls_per_step: int = 4


@dataclass
class PreparedAgent:
    user_id: UUID
    agent: Agent
    adapter: BaseProvider
    api_key: SecretStr
    model: AIModel
    prompt: str
    tools: tuple[ToolSpec, ...]


def _request_budget(agent: Agent, turns: list[ChatTurn], tools: tuple[ToolSpec, ...]) -> int:
    """Conservative UTF-8 byte estimate + framing, not provider-confirmed usage.

    Enforced even when the provider omits usage. Repeated context and tool specs
    count again for every model request; this safety estimate is never billed.
    """
    payload = {
        "system": agent.system_prompt or "",
        "turns": [
            {
                "role": turn.role, "content": turn.content,
                "calls": [
                    {
                        "id": call.id, "name": call.name, "arguments": call.arguments,
                        "replay_metadata": call.replay_metadata,
                    }
                    for call in turn.tool_calls
                ],
            }
            for turn in turns
        ],
        "tools": [
            {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
            for tool in tools
        ],
    }
    return len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 128


def _safe_tool_call(call: ToolCall) -> ToolCall:
    """Refuse unencodable/oversized arguments BEFORE traces, SSE or BSON audit.

    Invalid payloads are represented explicitly as rejected, not stored verbatim.
    The marker fails each allowlisted argument schema, so no tool executes it.
    """
    try:
        encoded = json.dumps(call.arguments, ensure_ascii=False, allow_nan=False)
        if len(encoded) > 65536:
            raise ValueError("Arguments too large")
        BSON.encode({"arguments": call.arguments})
        return call
    except (ValueError, TypeError, OverflowError, RecursionError, InvalidDocument, UnicodeError):
        return ToolCall(
            id=call.id, name=call.name,
            arguments={"rejected_arguments": "invalid_or_out_of_range"},
            replay_metadata=call.replay_metadata,
        )


def _sanitize_result(result: dict) -> dict:
    """Bound and JSON-guard a tool observation before it re-enters the model."""
    try:
        text = json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        return {"error": "tool_failed"}
    if len(text) > MAX_RESULT_CHARS:
        return {"truncated": True, "preview": text[:MAX_RESULT_CHARS]}
    return result


class AgentService:
    """Agent Studio CRUD plus a bounded, owner-scoped tool-calling execution loop.

    Validation/ownership/capability are checked before the SSE stream opens. The
    loop forwards only allowlisted tools, runs them in a thread with a timeout,
    and stops on step/token/deadline budgets. Tool results are sanitized
    observations; no arbitrary code or system command ever runs.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        settings: Settings,
        chat_http: ChatHTTP | None = None,
        limits: AgentLimits | None = None,
    ):
        self.repo = AgentRepository(db)
        self.providers = ProviderRepository(db)
        self.requests = ChatRepository(db)
        self.vault = CredentialVault(settings.credential_encryption_key)
        self.chat_http = chat_http
        self.limits = limits or AgentLimits()

    # --- Studio CRUD ---
    async def create_agent(self, user_id: UUID, payload: AgentCreate) -> AgentDetail:
        _, model = await self._require_target(user_id, payload.provider, payload.model)
        self._check_tools_capability(model, payload.tools)
        agent = await self.repo.create_agent(
            user_id,
            name=payload.name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            provider=payload.provider,
            model=payload.model,
            temperature=payload.temperature,
            max_output_tokens=payload.max_output_tokens,
            tools=self._validate_tools(payload.tools),
        )
        return self._detail(agent)

    async def list_agents(self, user_id: UUID) -> AgentList:
        agents = await self.repo.list_agents(user_id)
        return AgentList(agents=[self._summary(a) for a in agents])

    async def get_agent(self, user_id: UUID, agent_id: UUID) -> AgentDetail:
        return self._detail(await self._require_agent(user_id, agent_id))

    async def patch_agent(self, user_id: UUID, agent_id: UUID, patch: AgentPatch) -> AgentDetail:
        agent = await self._require_agent(user_id, agent_id)
        values = {
            field: getattr(patch, field)
            for field in (
                "name", "description", "system_prompt", "provider",
                "model", "temperature", "max_output_tokens", "tools",
            )
            if field in patch.model_fields_set
        }
        if "tools" in values:
            values["tools"] = self._validate_tools(values["tools"])
        if {"provider", "model", "tools"} & values.keys():
            _, model = await self._require_target(
                user_id, values.get("provider", agent.provider), values.get("model", agent.model)
            )
            self._check_tools_capability(model, values.get("tools", agent.tools))
        updated = await self.repo.update_agent(user_id, agent_id, values)
        if updated is None:
            raise ProviderError("agent_not_found")
        return self._detail(updated)

    async def delete_agent(self, user_id: UUID, agent_id: UUID) -> None:
        if not await self.repo.delete_agent(user_id, agent_id):
            raise ProviderError("agent_not_found")

    async def duplicate_agent(self, user_id: UUID, agent_id: UUID) -> AgentDetail:
        agent = await self._require_agent(user_id, agent_id)
        copy = await self.repo.create_agent(
            user_id,
            name=f"{agent.name[:110]} (bản sao)",
            description=agent.description,
            system_prompt=agent.system_prompt,
            provider=agent.provider,
            model=agent.model,
            temperature=agent.temperature,
            max_output_tokens=agent.max_output_tokens,
            tools=list(agent.tools),
        )
        return self._detail(copy)

    # --- Executions ---
    async def list_executions(self, user_id: UUID, agent_id: UUID) -> ExecutionList:
        await self._require_agent(user_id, agent_id)
        executions = await self.repo.list_executions(user_id, agent_id)
        return ExecutionList(executions=[self._execution_summary(e) for e in executions])

    async def get_execution(
        self, user_id: UUID, agent_id: UUID, execution_id: UUID
    ) -> ExecutionDetail:
        execution = await self._require_execution(user_id, agent_id, execution_id)
        audit = await self.repo.list_tool_executions(user_id, execution_id)
        return self._execution_detail(execution, audit)

    async def delete_execution(self, user_id: UUID, agent_id: UUID, execution_id: UUID) -> None:
        await self._require_execution(user_id, agent_id, execution_id)
        await self.repo.delete_execution(user_id, execution_id)

    @staticmethod
    def tool_catalog() -> ToolCatalog:
        return ToolCatalog(tools=[ToolCatalogItem(**item) for item in tool_catalog()])

    async def prepare_run(
        self, user_id: UUID, agent_id: UUID, payload: RunRequest
    ) -> PreparedAgent:
        agent = await self._require_agent(user_id, agent_id)
        credential, model = await self._require_target(user_id, agent.provider, agent.model)
        self._check_tools_capability(model, agent.tools)
        key = self.vault.decrypt(credential.encrypted_api_key, user_id, agent.provider)
        tools = tuple(
            ToolSpec(
                name=TOOL_REGISTRY[name].name,
                description=TOOL_REGISTRY[name].description,
                parameters=TOOL_REGISTRY[name].parameters,
            )
            for name in agent.tools
            if name in TOOL_REGISTRY
        )
        estimate = _request_budget(agent, [ChatTurn("user", payload.prompt)], tools)
        if estimate >= self.limits.token_budget:
            raise ProviderError("agent_budget_exceeded")
        return PreparedAgent(
            user_id, agent, create_provider(agent.provider, chat_http=self.chat_http),
            key, model, payload.prompt, tools,
        )

    async def stream_prepared(self, prepared: PreparedAgent) -> AsyncIterator[dict]:
        user_id = prepared.user_id
        agent = prepared.agent
        execution = await self.repo.create_execution(
            user_id, agent.id, prompt=prepared.prompt, provider=agent.provider, model=agent.model
        )
        started = time.monotonic()
        turns: list[ChatTurn] = [ChatTurn("user", prepared.prompt)]
        total_input: int | None = None
        total_output: int | None = None
        input_complete = output_complete = True
        budget_used = 0
        final_content = ""
        parts: list[str] = []
        calls: list[ToolCall] = []
        tool_calls: list[AgentToolCall] = []
        step_input: int | None = None
        step_output: int | None = None
        step_index = -1
        step_saved = True
        status, error_code = "success", None

        async def finish(terminal_status, terminal_error):
            inputs, outputs = total_input, total_output
            inputs_known, outputs_known = input_complete, output_complete
            if not step_saved:
                inputs_known = inputs_known and step_input is not None
                outputs_known = outputs_known and step_output is not None
                if step_input is not None:
                    inputs = (inputs or 0) + step_input
                if step_output is not None:
                    outputs = (outputs or 0) + step_output
                completed = {tc.id for tc in tool_calls}
                incomplete = [
                    AgentToolCall(
                        id=call.id, name=call.name, arguments=call.arguments,
                        status="skipped", error_code=terminal_error,
                    )
                    for call in calls if call.id not in completed
                ]
                await self.repo.append_step(
                    user_id, execution.id,
                    AgentStep(
                        index=step_index, content="".join(parts),
                        tool_calls=tool_calls + incomplete,
                        input_tokens=step_input, output_tokens=step_output,
                    ),
                )
            return await self._finalize_execution(
                user_id, agent, execution.id, prepared.model, final_content,
                terminal_status, terminal_error,
                inputs if inputs_known else None, outputs if outputs_known else None, started,
            )

        async def persist_terminal(terminal_status, terminal_error):
            # Exactly one finalizer survives cancellation at any persistence await.
            task = asyncio.create_task(finish(terminal_status, terminal_error))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    pass
                raise

        try:
            yield {
                "event": "execution",
                "data": {
                    "execution": self._execution_detail(execution, []).model_dump(mode="json")
                },
            }
            async with asyncio.timeout(self.limits.deadline_seconds):
                active_tools = prepared.tools
                tools_fallback_used = False
                for step_index in range(self.limits.max_steps):
                    input_estimate = _request_budget(agent, turns, active_tools)
                    remaining = self.limits.token_budget - budget_used - input_estimate
                    if remaining <= 0:
                        raise ProviderError("agent_budget_exceeded")
                    parts = []
                    calls = []
                    tool_calls = []
                    step_input = step_output = None
                    step_saved = False
                    output_estimate = 0
                    while True:
                        request = ChatRequest(
                            model=agent.model,
                            turns=tuple(turns),
                            system_prompt=agent.system_prompt,
                            temperature=agent.temperature,
                            max_output_tokens=min(agent.max_output_tokens or 2048, remaining),
                            tools=active_tools,
                        )
                        try:
                            stream = prepared.adapter.stream_chat(prepared.api_key, request)
                            async for event in stream:
                                if event.kind == "delta":
                                    output_estimate += len(event.text.encode("utf-8"))
                                    if output_estimate > remaining:
                                        raise ProviderError("agent_budget_exceeded")
                                    parts.append(event.text)
                                    final_content = "".join(parts)
                                    yield {
                                        "event": "step_delta",
                                        "data": {"step_index": step_index, "text": event.text},
                                    }
                                elif event.kind == "tool_call" and event.tool_call is not None:
                                    if len(calls) >= 16:
                                        raise ProviderError("generation_failed")
                                    call = _safe_tool_call(event.tool_call)
                                    encoded_arguments = json.dumps(
                                        call.arguments, ensure_ascii=False
                                    ).encode("utf-8")
                                    output_estimate += (
                                        len(encoded_arguments) + len(call.name) + 32
                                    )
                                    if output_estimate > remaining:
                                        raise ProviderError("agent_budget_exceeded")
                                    calls.append(call)
                                    pending = AgentToolCall(
                                        id=call.id, name=call.name, arguments=call.arguments,
                                        status="pending",
                                    )
                                    yield {
                                        "event": "tool_call",
                                        "data": {
                                            "step_index": step_index,
                                            "tool_call": self._tool_call_out(pending).model_dump(
                                                mode="json"
                                            ),
                                        },
                                    }
                                elif event.kind == "usage":
                                    if event.input_tokens is not None:
                                        step_input = event.input_tokens
                                    if event.output_tokens is not None:
                                        step_output = event.output_tokens
                        except ProviderError as error:
                            if (
                                error.code != "model_tools_unsupported"
                                or not active_tools
                                or tools_fallback_used
                            ):
                                raise
                            # The model rejected tool calling outright: drop
                            # tools for the rest of this execution and retry
                            # this step once without them.
                            tools_fallback_used = True
                            active_tools = ()
                            parts = []
                            calls = []
                            tool_calls = []
                            step_input = step_output = None
                            output_estimate = 0
                            final_content = ""
                            yield {
                                "event": "tools_fallback",
                                "data": {
                                    "code": "model_tools_unsupported",
                                    "step_index": step_index,
                                },
                            }
                            continue
                        break
                    content = "".join(parts)
                    final_content = content
                    if not content.strip() and not calls:
                        raise ProviderError("generation_failed")
                    budget_used += max(step_input or 0, input_estimate) + max(
                        step_output or 0, output_estimate
                    )
                    if budget_used > self.limits.token_budget:
                        raise ProviderError("agent_budget_exceeded")
                    for position, call in enumerate(calls):
                        if position < self.limits.max_tool_calls_per_step:
                            tc = await self._execute_tool_call(
                                user_id, agent, execution.id, step_index, call
                            )
                        else:
                            tc = AgentToolCall(
                                id=call.id, name=call.name, arguments=call.arguments,
                                status="skipped", error_code="tool_limit",
                            )
                            await self.repo.record_tool_execution(
                                user_id, agent.id, execution.id, step_index=step_index,
                                tool_name=call.name, arguments=call.arguments, result=None,
                                status="skipped", error_code="tool_limit", latency_ms=None,
                            )
                        tool_calls.append(tc)
                        yield {
                            "event": "tool_result",
                            "data": {
                                "step_index": step_index,
                                "tool_call": self._tool_call_out(tc).model_dump(mode="json"),
                            },
                        }
                    step = AgentStep(
                        index=step_index, content=content, tool_calls=tool_calls,
                        input_tokens=step_input, output_tokens=step_output,
                    )
                    await self.repo.append_step(user_id, execution.id, step)
                    step_saved = True
                    input_complete = input_complete and step_input is not None
                    output_complete = output_complete and step_output is not None
                    if step_input is not None:
                        total_input = (total_input or 0) + step_input
                    if step_output is not None:
                        total_output = (total_output or 0) + step_output
                    yield {
                        "event": "step_done",
                        "data": {"step": self._step_out(step).model_dump(mode="json")},
                    }
                    if not tool_calls:
                        break
                    turns.append(
                        ChatTurn(
                            "assistant", content,
                            tool_calls=tuple(calls),
                        )
                    )
                    for tc in tool_calls:
                        observation = (
                            tc.result
                            if tc.status == "success" and tc.result is not None
                            else {"error": tc.error_code or "tool_failed"}
                        )
                        turns.append(
                            ChatTurn(
                                "tool", json.dumps(observation, ensure_ascii=False),
                                tool_call_id=tc.id, tool_name=tc.name,
                            )
                        )
                else:
                    status, error_code = "error", "agent_step_limit"
        except TimeoutError:
            status, error_code = "error", "agent_timeout"
        except ProviderError as error:
            status, error_code = "error", error.code
        except (asyncio.CancelledError, GeneratorExit):
            await persist_terminal("stopped", None)
            raise
        except Exception:
            status, error_code = "error", "generation_failed"
        final, audit = await persist_terminal(status, error_code)
        if status == "error":
            yield {
                "event": "execution_error",
                "data": {"code": error_code, "message": ERRORS[error_code][1]},
            }
        yield {
            "event": "done",
            "data": {"execution": self._execution_detail(final, audit).model_dump(mode="json")},
        }

    async def _execute_tool_call(
        self, user_id: UUID, agent: Agent, execution_id: UUID, step_index: int, call: ToolCall
    ) -> AgentToolCall:
        started = time.monotonic()
        tc = AgentToolCall(id=call.id, name=call.name, arguments=call.arguments)
        if not is_tool_allowed(call.name, agent.tools):
            tc.status, tc.error_code = "error", "tool_not_allowed"
        else:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(execute_tool, call.name, call.arguments),
                    self.limits.tool_timeout_seconds,
                )
                tc.status, tc.result = "success", _sanitize_result(result)
            except ToolError as error:
                tc.status, tc.error_code = "error", error.code
            except TimeoutError:
                tc.status, tc.error_code = "error", "tool_timeout"
            except Exception:
                tc.status, tc.error_code = "error", "tool_failed"
        tc.latency_ms = _elapsed_ms(started)
        await self.repo.record_tool_execution(
            user_id, agent.id, execution_id, step_index=step_index, tool_name=call.name,
            arguments=call.arguments, result=tc.result, status=tc.status,
            error_code=tc.error_code, latency_ms=tc.latency_ms,
        )
        return tc

    async def _finalize_execution(
        self, user_id, agent, execution_id, model, content, status, error_code,
        total_input, total_output, started,
    ) -> tuple[AgentExecution, list]:
        latency = _elapsed_ms(started)
        input_tokens = total_input
        output_tokens = total_output
        await self.repo.update_execution(
            user_id, execution_id,
            {
                "status": status, "content": content,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "latency_ms": latency, "error_code": error_code,
                "estimated_cost": (
                    _estimate_cost(model, input_tokens, output_tokens)
                    if input_tokens is not None and output_tokens is not None else None
                ),
            },
        )
        await self.requests.record_request(
            user_id, provider=agent.provider, model=agent.model, status=status,
            input_tokens=input_tokens, output_tokens=output_tokens, latency_ms=latency,
        )
        execution = await self.repo.get_execution(user_id, execution_id)
        audit = await self.repo.list_tool_executions(user_id, execution_id)
        return execution, audit

    async def _require_agent(self, user_id: UUID, agent_id: UUID) -> Agent:
        agent = await self.repo.get_agent(user_id, agent_id)
        if agent is None:
            raise ProviderError("agent_not_found")
        return agent

    async def _require_execution(
        self, user_id: UUID, agent_id: UUID, execution_id: UUID
    ) -> AgentExecution:
        await self._require_agent(user_id, agent_id)
        execution = await self.repo.get_execution(user_id, execution_id)
        if execution is None or execution.agent_id != agent_id:
            raise ProviderError("execution_not_found")
        return execution

    async def _require_target(self, user_id: UUID, provider: str, model_id: str):
        get_provider(provider, require_implemented=True)
        credential = await self.providers.get(user_id, provider)
        if credential is None:
            raise ProviderError("credentials_missing")
        if not credential.enabled:
            raise ProviderError("provider_disabled")
        model = await self.providers.get_model(credential.id, model_id)
        if model is None:
            raise ProviderError("model_not_synced")
        if model.capabilities.get("chat") is False:
            raise ProviderError("model_not_chat_capable")
        return credential, model

    @staticmethod
    def _check_tools_capability(model: AIModel, tools: list[str]) -> None:
        # Listing metadata is tri-state; unknown is not a promise of tool support.
        # Actual generation decides support when the provider publishes no evidence.
        if tools and model.capabilities.get("tools") is False:
            raise ProviderError("model_not_tool_capable")

    @staticmethod
    def _validate_tools(tools: list[str]) -> list[str]:
        for name in tools:
            if name not in TOOL_REGISTRY:
                raise ProviderError("invalid_agent_tools")
        return tools

    @staticmethod
    def _summary(agent: Agent) -> AgentSummary:
        return AgentSummary(
            id=agent.id, name=agent.name, description=agent.description,
            provider=agent.provider, model=agent.model, tools=agent.tools,
            created_at=agent.created_at, updated_at=agent.updated_at,
        )

    @staticmethod
    def _detail(agent: Agent) -> AgentDetail:
        return AgentDetail(
            **AgentService._summary(agent).model_dump(),
            system_prompt=agent.system_prompt, temperature=agent.temperature,
            max_output_tokens=agent.max_output_tokens,
        )

    @staticmethod
    def _tool_call_out(tc: AgentToolCall) -> AgentToolCallOut:
        return AgentToolCallOut(
            id=tc.id, name=tc.name, arguments=tc.arguments, status=tc.status,
            result=tc.result, error_code=tc.error_code, latency_ms=tc.latency_ms,
        )

    @staticmethod
    def _step_out(step: AgentStep) -> AgentStepOut:
        return AgentStepOut(
            index=step.index, content=step.content,
            tool_calls=[AgentService._tool_call_out(tc) for tc in step.tool_calls],
            input_tokens=step.input_tokens, output_tokens=step.output_tokens,
        )

    @staticmethod
    def _tool_execution_out(record) -> ToolExecutionOut:
        return ToolExecutionOut(
            id=record.id, step_index=record.step_index, tool_name=record.tool_name,
            arguments=record.arguments, result=record.result, status=record.status,
            error_code=record.error_code, latency_ms=record.latency_ms,
            created_at=record.created_at,
        )

    @staticmethod
    def _execution_summary(execution: AgentExecution) -> ExecutionSummary:
        return ExecutionSummary(
            id=execution.id, agent_id=execution.agent_id, prompt=execution.prompt,
            provider=execution.provider, model=execution.model,
            status=execution.status, step_count=len(execution.steps),
            input_tokens=execution.input_tokens, output_tokens=execution.output_tokens,
            estimated_cost=execution.estimated_cost,
            created_at=execution.created_at, updated_at=execution.updated_at,
        )

    @staticmethod
    def _execution_detail(execution: AgentExecution, audit: list) -> ExecutionDetail:
        return ExecutionDetail(
            **AgentService._execution_summary(execution).model_dump(),
            content=execution.content,
            steps=[AgentService._step_out(s) for s in execution.steps],
            latency_ms=execution.latency_ms, error_code=execution.error_code,
            tool_executions=[AgentService._tool_execution_out(t) for t in audit],
        )