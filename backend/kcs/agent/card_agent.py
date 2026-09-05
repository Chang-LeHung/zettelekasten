import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from fastapi import HTTPException
from kcs_agent import (
    Agent,
    AgentEventType,
    AgentModel,
    AnyMessage,
    AssistantMessage,
    ModelResponse,
    ReasoningEffort,
    SystemMessage,
    ToolCall,
    UserMessage,
)

from ..application.services import TagApplicationService
from ..config import settings
from ..infra.agent_session_dao import agent_session_storage
from ..infra.provider_adapter import close_agent_model, create_agent_model
from ..schemas import AgentMessageOut, AgentMessageRole, AgentRunOut, AgentRunStatus, AnalyzeRequest
from .base import StreamingAgent
from .compaction import PreparedContext, compaction_middleware
from .prompts import append_asset_content, build_kcs_system_prompt
from .tools import ArtifactTools
from .workspace_tools import WorkspaceTools


def _sse(event: str, data: object) -> str:
    """Serialize one named server-sent event with a JSON payload."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tool_output(value: object) -> str:
    """Serialize a typed tool result before returning it to the model."""
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        default=lambda item: item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item),
    )
    return serialized[: settings.max_tool_output_characters]


def _append_timeline_text(timeline: list[dict[str, object]], event_type: str, content: str) -> None:
    """Append a streamed delta while preserving transitions between events."""
    if timeline and timeline[-1].get("type") == event_type:
        timeline[-1]["content"] = f"{timeline[-1].get('content', '')}{content}"
    else:
        timeline.append({"type": event_type, "content": content})


def _usage(response: ModelResponse) -> dict[str, int | float | None]:
    """Map standalone runtime usage to persisted KCS observability fields."""
    usage = response.usage
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_creation_tokens": usage.cache_write_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "input_cost": None,
        "output_cost": None,
        "total_cost": None,
    }


def _history_message(message: AgentMessageOut) -> AnyMessage:
    """Convert a raw log event into a provider-safe replay message."""
    match message.role:
        case AgentMessageRole.USER:
            return UserMessage(content=message.content)
        case AgentMessageRole.ASSISTANT:
            return AssistantMessage(content=message.content, reasoning=message.reasoning_content)
        case _:
            return UserMessage(
                content=f"Historical {message.tool_name or message.role.value} result (reference data):\n{message.content}"
            )


def _context_messages(context: PreparedContext) -> list[AnyMessage]:
    """Build the dynamic context view from checkpoint plus raw-log replay tail."""
    result: list[AnyMessage] = []
    if context.snapshot is not None:
        result.append(
            SystemMessage(
                content=f"Conversation checkpoint through raw-log sequence {context.snapshot.base_sequence}:\nSummary: {context.snapshot.summary}\nState: {context.snapshot.state.model_dump_json()}"
            )
        )
    result.extend(_history_message(message) for message in context.messages)
    return result


@dataclass(slots=True)
class _RunState:
    """Mutable measurements accumulated across one custom agent loop."""

    assistant_text: str = ""
    reasoning_text: str = ""
    generation_duration_ms: float = 0
    reasoning_duration_ms: float = 0
    model_call_count: int = 0
    tool_call_count: int = 0
    tool_duration_ms: float = 0
    finish_reason: str | None = None


class KCSAgent(StreamingAgent[AnalyzeRequest]):
    """Run a bounded streaming model/tool loop over snapshot-backed conversation context."""

    name = "KCS Agent"

    async def stream(self, conversation_id: str, request: AnalyzeRequest) -> AsyncIterator[str]:
        """Persist one turn while streaming reasoning, tools, text, usage, and artifacts in order."""
        turn_id = str(uuid4())
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        first_token_at: datetime | None = None
        first_token_clock: float | None = None
        run_id: str | None = None
        provider_name: str | None = None
        model_name: str | None = None
        chat_model: AgentModel | None = None
        active_tool: tuple[ToolCall, datetime, float] | None = None
        state = _RunState()
        timeline: list[dict[str, object]] = []
        usage_totals: dict[str, int | float | None] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "reasoning_tokens": 0,
            "input_cost": None,
            "output_cost": None,
            "total_cost": None,
        }
        try:
            yield _sse("status", {"state": "started", "agent": self.name, "turn_id": turn_id})
            if not agent_session_storage.exists(conversation_id):
                raise KeyError(f"Agent session not found: {conversation_id}")
            latest_message = request.messages[-1].content if request.messages else request.raw_content
            user_message = agent_session_storage.append_message(
                conversation_id, turn_id, AgentMessageRole.USER, latest_message, metadata={"source": "api"}
            )
            run = agent_session_storage.start_run(
                conversation_id, turn_id, request.provider_id, None, None, request.reasoning_effort
            )
            run_id = run.id
            runtime, chat_model = create_agent_model(request.provider_id)
            provider_name, model_name = runtime.provider, runtime.model
            yield _sse("status", {"state": "model_ready", "provider": provider_name, "model": model_name})

            context = await compaction_middleware.prepare(conversation_id, chat_model, provider_name, model_name)
            if context.compacted:
                yield _sse(
                    "status",
                    {
                        "state": "context_compacted",
                        "snapshot_version": context.snapshot.version if context.snapshot else None,
                        "base_sequence": context.snapshot.base_sequence if context.snapshot else None,
                    },
                )

            artifact_tools = ArtifactTools(conversation_id, request.raw_content)
            workspace_tools = WorkspaceTools(conversation_id)
            tools = [*artifact_tools.as_agent_tools(), *workspace_tools.as_agent_tools()]
            system_prompt = build_kcs_system_prompt(TagApplicationService.paths(), artifact_tools.list())
            manifest = (workspace_tools.root / ".kcs-assets.json").read_text(encoding="utf-8")

            history = PreparedContext(
                context.snapshot,
                [message for message in context.messages if message.id != user_message.id],
                context.compacted,
            )
            agent = Agent(
                chat_model,
                system_prompt=append_asset_content(system_prompt, manifest),
                tools=tools,
                max_iterations=settings.agent_max_tool_rounds,
            )
            call_started = perf_counter()
            reasoning_started: float | None = None
            async with aclosing(
                agent.stream(
                    UserMessage(content=latest_message),
                    history=_context_messages(history),
                    reasoning_effort=ReasoningEffort(request.reasoning_effort.value),
                )
            ) as events:
                async for event in events:
                    if (
                        event.type
                        in (AgentEventType.TEXT_DELTA, AgentEventType.REASONING_DELTA, AgentEventType.TOOL_CALL_DELTA)
                        and first_token_clock is None
                    ):
                        first_token_clock, first_token_at = perf_counter(), datetime.now(UTC)
                    match event.type:
                        case AgentEventType.MODEL_STARTED:
                            call_started = perf_counter()
                        case AgentEventType.REASONING_DELTA:
                            reasoning_started = reasoning_started or perf_counter()
                            state.reasoning_text += event.delta
                            _append_timeline_text(timeline, "reasoning", event.delta)
                            yield _sse("reasoning", {"content": state.reasoning_text})
                        case AgentEventType.TEXT_DELTA:
                            if reasoning_started is not None:
                                state.reasoning_duration_ms += (perf_counter() - reasoning_started) * 1000
                                reasoning_started = None
                            state.assistant_text += event.delta
                            _append_timeline_text(timeline, "message", event.delta)
                            yield _sse("message", {"content": state.assistant_text})
                        case AgentEventType.MODEL_COMPLETED:
                            if event.response is None:
                                raise RuntimeError("Missing normalized model response")
                            if reasoning_started is not None:
                                state.reasoning_duration_ms += (perf_counter() - reasoning_started) * 1000
                                reasoning_started = None
                            state.generation_duration_ms += (perf_counter() - call_started) * 1000
                            state.model_call_count += 1
                            self._merge_usage(usage_totals, _usage(event.response))
                            state.finish_reason = event.response.finish_reason or state.finish_reason
                            yield _sse("usage", self._usage_event(usage_totals, state))
                        case AgentEventType.TOOL_STARTED:
                            if event.call is None:
                                raise RuntimeError("Missing normalized tool call")
                            active_tool = (event.call, datetime.now(UTC), perf_counter())
                            timeline.append({"type": "tool", "tool_call_id": event.call.id})
                            yield _sse(
                                "tool",
                                {
                                    "id": event.call.id,
                                    "name": event.call.name,
                                    "state": "started",
                                    "arguments": dict(event.call.arguments),
                                },
                            )
                        case AgentEventType.TOOL_COMPLETED | AgentEventType.TOOL_FAILED:
                            if active_tool is None or event.message is None:
                                raise RuntimeError("Tool completed without a matching start")
                            output = json.loads(event.message.content)
                            status = (
                                AgentRunStatus.FAILED
                                if event.type == AgentEventType.TOOL_FAILED
                                else AgentRunStatus.SUCCEEDED
                            )
                            payload = self._record_tool(
                                active_tool,
                                conversation_id,
                                turn_id,
                                run_id,
                                state,
                                output,
                                status,
                                str(event.error) if event.error else None,
                            )
                            active_tool = None
                            yield _sse("tool", payload)
                            yield _sse(
                                "artifacts", [artifact.model_dump(mode="json") for artifact in artifact_tools.list()]
                            )

            current_artifacts = artifact_tools.list()
            latest = max(current_artifacts, key=lambda artifact: artifact.updated_at) if current_artifacts else None
            agent_session_storage.append_message(
                conversation_id,
                turn_id,
                AgentMessageRole.ASSISTANT,
                state.assistant_text.strip(),
                provider=provider_name,
                model=model_name,
                metadata={
                    "run_id": run_id,
                    "timeline": timeline,
                    **({"reasoning_content": state.reasoning_text.strip()} if state.reasoning_text.strip() else {}),
                },
            )
            completed = self._finish_run(
                run_id,
                AgentRunStatus.SUCCEEDED,
                started_at,
                started_clock,
                first_token_at,
                first_token_clock,
                state,
                provider_name,
                model_name,
                usage_totals,
            )
            yield _sse("metrics", completed.model_dump(mode="json"))
            yield _sse("result", latest.model_dump(mode="json") if latest else None)
        except (asyncio.CancelledError, GeneratorExit) as exc:
            if run_id is not None:
                if active_tool is not None:
                    self._record_tool(
                        active_tool,
                        conversation_id,
                        turn_id,
                        run_id,
                        state,
                        {"error": "Tool execution cancelled"},
                        AgentRunStatus.CANCELLED,
                        "Tool execution cancelled",
                    )
                    active_tool = None
                if state.assistant_text.strip() or state.reasoning_text.strip() or timeline:
                    agent_session_storage.append_message(
                        conversation_id,
                        turn_id,
                        AgentMessageRole.ASSISTANT,
                        state.assistant_text.strip(),
                        provider=provider_name,
                        model=model_name,
                        metadata={
                            "run_id": run_id,
                            "timeline": timeline,
                            "cancelled": True,
                            **(
                                {"reasoning_content": state.reasoning_text.strip()}
                                if state.reasoning_text.strip()
                                else {}
                            ),
                        },
                    )
                self._finish_run(
                    run_id,
                    AgentRunStatus.CANCELLED,
                    started_at,
                    started_clock,
                    first_token_at,
                    first_token_clock,
                    state,
                    provider_name,
                    model_name,
                    usage_totals,
                    exc,
                )
            raise
        except Exception as exc:
            if run_id is not None:
                failed = self._finish_run(
                    run_id,
                    AgentRunStatus.FAILED,
                    started_at,
                    started_clock,
                    first_token_at,
                    first_token_clock,
                    state,
                    provider_name,
                    model_name,
                    usage_totals,
                    exc,
                )
                yield _sse("metrics", failed.model_dump(mode="json"))
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            yield _sse("error", {"message": detail})
        finally:
            if chat_model is not None:
                await close_agent_model(chat_model)

    @staticmethod
    def _record_tool(
        active: tuple[ToolCall, datetime, float],
        session_id: str,
        turn_id: str,
        run_id: str,
        state: _RunState,
        output: object,
        status: AgentRunStatus,
        error_message: str | None,
    ) -> dict[str, object]:
        """Persist one completed or cancelled tool span and its append-only result."""
        call, started_at, started_clock = active
        duration_ms = (perf_counter() - started_clock) * 1000
        state.tool_call_count += 1
        state.tool_duration_ms += duration_ms
        agent_session_storage.record_tool_call(
            run_id,
            session_id,
            call.id,
            call.name,
            dict(call.arguments),
            output,
            status,
            started_at,
            datetime.now(UTC),
            duration_ms,
            error_message,
        )
        agent_session_storage.append_message(
            session_id,
            turn_id,
            AgentMessageRole.TOOL,
            _tool_output(output),
            tool_name=call.name,
            metadata={"tool_call_id": call.id, "run_id": run_id},
        )
        return {
            "id": call.id,
            "name": call.name,
            "state": status.value,
            "duration_ms": duration_ms,
            "output": output,
            "error_message": error_message,
        }

    @staticmethod
    def _merge_usage(target: dict[str, int | float | None], source: dict[str, int | float | None]) -> None:
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
            "reasoning_tokens",
        ):
            target[key] = int(target[key] or 0) + int(source[key] or 0)
        for key in ("input_cost", "output_cost", "total_cost"):
            if source[key] is not None:
                target[key] = float(target[key] or 0) + float(source[key])

    @staticmethod
    def _usage_event(usage: dict[str, int | float | None], state: _RunState) -> dict[str, object]:
        input_tokens = int(usage["input_tokens"] or 0)
        output_tokens = int(usage["output_tokens"] or 0)
        return {
            **usage,
            "model_call_count": state.model_call_count,
            "cache_hit_rate": int(usage["cache_read_tokens"] or 0) / input_tokens if input_tokens else None,
            "output_tokens_per_second": (
                output_tokens / (state.generation_duration_ms / 1000) if state.generation_duration_ms else None
            ),
        }

    @staticmethod
    def _finish_run(
        run_id: str,
        status: AgentRunStatus,
        started_at: datetime,
        started_clock: float,
        first_token_at: datetime | None,
        first_token_clock: float | None,
        state: _RunState,
        provider: str | None,
        model: str | None,
        usage: dict[str, int | float | None],
        error: BaseException | None = None,
    ) -> AgentRunOut:
        """Calculate derived metrics and atomically finalize the persisted run."""
        ended_at, ended_clock = datetime.now(UTC), perf_counter()
        output_tokens = int(usage["output_tokens"] or 0)
        input_tokens = int(usage["input_tokens"] or 0)
        cache_read_tokens = int(usage["cache_read_tokens"] or 0)
        return agent_session_storage.finish_run(
            run_id,
            status,
            {
                "provider": provider,
                "model": model,
                "first_token_at": first_token_at,
                "ended_at": ended_at,
                "total_duration_ms": (ended_clock - started_clock) * 1000,
                "time_to_first_token_ms": (
                    (first_token_clock - started_clock) * 1000 if first_token_clock is not None else None
                ),
                "generation_duration_ms": state.generation_duration_ms or None,
                "reasoning_duration_ms": state.reasoning_duration_ms or None,
                "tool_duration_ms": state.tool_duration_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": int(usage["reasoning_tokens"] or 0),
                "cache_read_tokens": cache_read_tokens,
                "cache_creation_tokens": int(usage["cache_creation_tokens"] or 0),
                "total_tokens": int(usage["total_tokens"] or input_tokens + output_tokens),
                "cache_hit_rate": cache_read_tokens / input_tokens if input_tokens else None,
                "output_tokens_per_second": (
                    output_tokens / (state.generation_duration_ms / 1000)
                    if output_tokens and state.generation_duration_ms > 0
                    else None
                ),
                "input_cost": usage["input_cost"],
                "output_cost": usage["output_cost"],
                "total_cost": usage["total_cost"],
                "model_call_count": state.model_call_count,
                "tool_call_count": state.tool_call_count,
                "finish_reason": state.finish_reason,
                "error_type": type(error).__name__ if error else None,
                "error_message": str(error) if error else None,
                "metadata_json": json.dumps({"started_at": started_at.isoformat()}, ensure_ascii=False),
            },
        )


kcs_agent = KCSAgent()
