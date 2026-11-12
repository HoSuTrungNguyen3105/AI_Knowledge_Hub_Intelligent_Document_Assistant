"""Fixed allowlist of safe, self-contained agent tools.

No tool executes arbitrary code or system commands. The calculator evaluates a
restricted arithmetic AST (never ``eval``); datetime uses fixed UTC offsets (no
IANA database dependency); data_analyzer computes descriptive statistics over a
bounded numeric array. Tool arguments arrive from the model (untrusted) and are
validated strictly before execution. Results are small structured dicts that
never contain credentials.

Search/RAG-dependent tools (document/knowledge/web search, summarizer) are listed
as deferred metadata for the picker but are NOT executable until their subsystems
exist (Phase 6/7). The registry is the single source of truth for what may run.
"""

import ast
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Shared limits -----------------------------------------------------------

MAX_RESULT_CHARS = 4000
_CALC_MAX_CHARS = 200
_CALC_MAX_NODES = 120
_CALC_MAX_MAGNITUDE = 1e18
_CALC_MAX_EXPONENT = 64
_CALC_ALLOWED_FUNCS = {"abs", "round", "min", "max", "sqrt"}


class ToolError(Exception):
    """A tool refused or failed; surfaced to the model as a sanitized observation."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


# --- Calculator (restricted AST, never eval) ---------------------------------


class CalculatorArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expression: str = Field(min_length=1, max_length=_CALC_MAX_CHARS)

    @field_validator("expression")
    @classmethod
    def strip_expression(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Expression cannot be empty")
        return text


def _guard_magnitude(value: float | int) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError("calculator_invalid", "Only numeric results are allowed.")
    if isinstance(value, float) and not math.isfinite(value):
        raise ToolError("calculator_invalid", "Result is not a finite number.")
    if abs(value) > _CALC_MAX_MAGNITUDE:
        raise ToolError("calculator_range", "Result exceeds the allowed magnitude.")
    return value


def _eval_node(node: ast.AST, budget: list[int]) -> float | int:
    budget[0] -= 1
    if budget[0] < 0:
        raise ToolError("calculator_complexity", "Expression is too complex.")
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, budget)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolError("calculator_invalid", "Only numeric literals are allowed.")
        return _guard_magnitude(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _eval_node(node.operand, budget)
        return _guard_magnitude(operand if isinstance(node.op, ast.UAdd) else -operand)
    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, budget)
        right = _eval_node(node.right, budget)
        op = node.op
        if isinstance(op, ast.Pow):
            # Bound the exponent BEFORE computing so 2**999999 can never allocate.
            if abs(right) > _CALC_MAX_EXPONENT:
                raise ToolError("calculator_range", "Exponent is too large.")
        try:
            if isinstance(op, ast.Add):
                result = left + right
            elif isinstance(op, ast.Sub):
                result = left - right
            elif isinstance(op, ast.Mult):
                result = left * right
            elif isinstance(op, ast.Div):
                result = left / right
            elif isinstance(op, ast.FloorDiv):
                result = left // right
            elif isinstance(op, ast.Mod):
                result = left % right
            elif isinstance(op, ast.Pow):
                result = left**right
            else:
                raise ToolError("calculator_invalid", "Operator is not allowed.")
        except ZeroDivisionError:
            raise ToolError("calculator_invalid", "Division by zero.") from None
        except (OverflowError, ValueError):
            raise ToolError("calculator_range", "Result exceeds the allowed range.") from None
        return _guard_magnitude(result)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _CALC_ALLOWED_FUNCS:
            raise ToolError("calculator_invalid", "Function is not allowed.")
        if node.keywords or len(node.args) > 20:
            raise ToolError("calculator_invalid", "Too many arguments.")
        args = [_eval_node(arg, budget) for arg in node.args]
        name = node.func.id
        if name == "sqrt":
            if len(args) != 1 or args[0] < 0:
                raise ToolError("calculator_invalid", "sqrt needs one non-negative number.")
            return _guard_magnitude(math.sqrt(args[0]))
        if name == "abs":
            if len(args) != 1:
                raise ToolError("calculator_invalid", "abs needs one number.")
            return _guard_magnitude(abs(args[0]))
        if name == "round":
            if not 1 <= len(args) <= 2:
                raise ToolError("calculator_invalid", "round needs one or two numbers.")
            digits = int(args[1]) if len(args) == 2 else 0
            if abs(digits) > 12:
                raise ToolError("calculator_range", "Rounding precision is too large.")
            return _guard_magnitude(round(args[0], digits))
        if not args:
            raise ToolError("calculator_invalid", f"{name} needs at least one number.")
        return _guard_magnitude(min(args) if name == "min" else max(args))
    raise ToolError("calculator_invalid", "Expression contains a disallowed construct.")


def _run_calculator(args: CalculatorArgs) -> dict:
    try:
        tree = ast.parse(args.expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        raise ToolError("calculator_invalid", "Expression could not be parsed.") from None
    result = _eval_node(tree, [_CALC_MAX_NODES])
    return {"expression": args.expression, "result": result}


# --- DateTime (fixed UTC offsets, no tzdata dependency) ----------------------


class DateTimeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation: Literal["now", "diff"]
    offset_hours: int = Field(default=0, ge=-12, le=14)
    start: str | None = Field(default=None, max_length=64)
    end: str | None = Field(default=None, max_length=64)


def _parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise ToolError("datetime_invalid", "Timestamp must be ISO 8601.") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _run_datetime(args: DateTimeArgs) -> dict:
    if args.operation == "now":
        tz = timezone(timedelta(hours=args.offset_hours))
        local = datetime.now(UTC).astimezone(tz)
        return {
            "operation": "now",
            "iso": local.isoformat(),
            "utc_iso": datetime.now(UTC).isoformat(),
            "offset_hours": args.offset_hours,
            "date": local.date().isoformat(),
            "time": local.strftime("%H:%M:%S"),
            "weekday": local.strftime("%A"),
        }
    if not args.start or not args.end:
        raise ToolError("datetime_invalid", "diff needs both start and end timestamps.")
    delta = _parse_iso(args.end) - _parse_iso(args.start)
    seconds = int(delta.total_seconds())
    return {
        "operation": "diff",
        "start": args.start,
        "end": args.end,
        "seconds": seconds,
        "days": delta.days,
        "hours": round(seconds / 3600, 4),
    }


# --- Data Analyzer (descriptive stats over a bounded numeric array) ----------


class DataAnalyzerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    values: list[float] = Field(min_length=1, max_length=10000)

    @field_validator("values")
    @classmethod
    def finite_values(cls, value: list[float]) -> list[float]:
        if any(not math.isfinite(item) for item in value):
            raise ValueError("All values must be finite numbers")
        if any(abs(item) > _CALC_MAX_MAGNITUDE for item in value):
            raise ValueError("Values exceed the allowed magnitude")
        return value


def _run_data_analyzer(args: DataAnalyzerArgs) -> dict:
    values = args.values
    count = len(values)
    total = math.fsum(values)
    mean = total / count
    variance = math.fsum((item - mean) ** 2 for item in values) / count
    ordered = sorted(values)
    mid = count // 2
    median = ordered[mid] if count % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "count": count,
        "sum": round(total, 6),
        "mean": round(mean, 6),
        "median": round(median, 6),
        "min": ordered[0],
        "max": ordered[-1],
        "stddev": round(math.sqrt(variance), 6),
    }


# --- Registry ----------------------------------------------------------------


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    args_model: type[BaseModel]
    run: Callable[[BaseModel], dict]


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "calculator": ToolDefinition(
        name="calculator",
        description=(
            "Evaluate a safe arithmetic expression (numbers, + - * / // % **, "
            "abs/round/min/max/sqrt). No code execution. Use for precise math."
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Arithmetic expression, e.g. '12.5 * (3 + 4)'.",
                }
            },
            "required": ["expression"],
        },
        args_model=CalculatorArgs,
        run=_run_calculator,
    ),
    "datetime": ToolDefinition(
        name="datetime",
        description=(
            "Get the current date/time at a fixed UTC offset (operation 'now'), or "
            "the difference between two ISO 8601 timestamps (operation 'diff')."
        ),
        parameters={
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["now", "diff"]},
                "offset_hours": {
                    "type": "integer",
                    "description": "UTC offset in hours for 'now' (-12..14).",
                },
                "start": {"type": "string", "description": "ISO start for 'diff'."},
                "end": {"type": "string", "description": "ISO end for 'diff'."},
            },
            "required": ["operation"],
        },
        args_model=DateTimeArgs,
        run=_run_datetime,
    ),
    "data_analyzer": ToolDefinition(
        name="data_analyzer",
        description=(
            "Compute descriptive statistics (count, sum, mean, median, min, max, "
            "stddev) over a provided array of numbers. No code execution."
        ),
        parameters={
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Numeric data to analyze (1..10000 items).",
                }
            },
            "required": ["values"],
        },
        args_model=DataAnalyzerArgs,
        run=_run_data_analyzer,
    ),
}

# Deferred tools: shown in the picker as unavailable, never executable yet.
DEFERRED_TOOLS: tuple[dict, ...] = (
    {
        "name": "document_search",
        "description": "Tìm kiếm nội dung trong tài liệu đã upload.",
        "phase": 6,
    },
    {
        "name": "knowledge_search",
        "description": "Tìm kiếm dữ liệu trong Knowledge Base (RAG).",
        "phase": 6,
    },
    {
        "name": "text_summarizer",
        "description": "Tóm tắt nội dung tài liệu/văn bản.",
        "phase": 6,
    },
    {
        "name": "web_search",
        "description": "Tìm kiếm Internet qua dịch vụ tìm kiếm được cấu hình.",
        "phase": 7,
    },
)


def tool_catalog() -> list[dict]:
    """Public metadata for the picker: executable tools + deferred roadmap tools."""
    catalog = [
        {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "available": True,
            "phase": None,
        }
        for tool in TOOL_REGISTRY.values()
    ]
    catalog.extend(
        {
            "name": item["name"],
            "description": item["description"],
            "parameters": None,
            "available": False,
            "phase": item["phase"],
        }
        for item in DEFERRED_TOOLS
    )
    return catalog


def is_tool_allowed(name: str, enabled: list[str] | tuple[str, ...]) -> bool:
    """A tool may run only if it is registered AND enabled on the agent."""
    return name in TOOL_REGISTRY and name in enabled


def execute_tool(name: str, arguments: dict) -> dict:
    """Validate untrusted model arguments and run a registered tool synchronously.

    Raises ToolError for unknown/disabled tools or invalid arguments. The caller
    (AgentService) runs this in a thread with a timeout and sanitizes the result.
    """
    definition = TOOL_REGISTRY.get(name)
    if definition is None:
        raise ToolError("tool_not_allowed", "This tool is not available.")
    if not isinstance(arguments, dict):
        raise ToolError("tool_invalid_arguments", "Arguments must be an object.")
    try:
        args = definition.args_model.model_validate(arguments)
    except (ValueError, TypeError):
        raise ToolError("tool_invalid_arguments", "Arguments failed validation.") from None
    result = definition.run(args)
    if not isinstance(result, dict):
        raise ToolError("tool_failed", "Tool returned an invalid result.")
    return result