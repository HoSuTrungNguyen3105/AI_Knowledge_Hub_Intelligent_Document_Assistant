import math

import pytest

from app.services.ai.tools import (
    DEFERRED_TOOLS,
    TOOL_REGISTRY,
    ToolError,
    execute_tool,
    is_tool_allowed,
    tool_catalog,
)


def calc(expression):
    return execute_tool("calculator", {"expression": expression})["result"]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("2 ** 10", 1024),
        ("7 // 2", 3),
        ("7 % 3", 1),
        ("-5 + 3", -2),
        ("10 / 4", 2.5),
        ("abs(-4)", 4),
        ("round(2.567, 2)", 2.57),
        ("min(3, 1, 2)", 1),
        ("max(3, 1, 2)", 3),
        ("sqrt(16)", 4),
    ],
)
def test_calculator_valid(expression, expected):
    assert calc(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo hi')",
        "eval('1+1')",
        "open('/etc/passwd')",
        "().__class__.__bases__",
        "x + 1",
        "'text'",
        "[1, 2, 3]",
        "lambda: 1",
        "2 ** 999999",
        "999999 ** 999999",
        "1 / 0",
        "1 // 0",
        "sqrt(-1)",
        "foo(1)",
        "abs(1, 2)",
        "1e308 * 1e308",
        "True",
    ],
)
def test_calculator_rejects_unsafe(expression):
    with pytest.raises(ToolError):
        calc(expression)


def test_calculator_rejects_overlong_and_complex():
    with pytest.raises(ToolError):
        execute_tool("calculator", {"expression": "1+" * 200 + "1"})
    with pytest.raises(ToolError):
        execute_tool("calculator", {"expression": "1+" * 60 + "1"})


def test_calculator_rejects_empty_and_non_string():
    with pytest.raises(ToolError):
        execute_tool("calculator", {"expression": "   "})
    with pytest.raises(ToolError):
        execute_tool("calculator", {"expression": 123})


def test_datetime_now_with_offset():
    result = execute_tool("datetime", {"operation": "now", "offset_hours": 7})
    assert result["operation"] == "now"
    assert result["offset_hours"] == 7
    assert "T" in result["iso"]
    assert result["weekday"]


def test_datetime_diff():
    result = execute_tool(
        "datetime",
        {"operation": "diff", "start": "2026-01-01T00:00:00Z", "end": "2026-01-03T00:00:00Z"},
    )
    assert result["days"] == 2
    assert result["seconds"] == 172800


def test_datetime_rejects_bad_input():
    with pytest.raises(ToolError):
        execute_tool("datetime", {"operation": "diff", "start": "nope", "end": "2026-01-01"})
    with pytest.raises(ToolError):
        execute_tool("datetime", {"operation": "diff"})
    with pytest.raises(ToolError):
        execute_tool("datetime", {"operation": "now", "offset_hours": 99})
    with pytest.raises(ToolError):
        execute_tool("datetime", {"operation": "unknown"})


def test_data_analyzer_stats():
    result = execute_tool("data_analyzer", {"values": [2, 4, 4, 4, 5, 5, 7, 9]})
    assert result["count"] == 8
    assert result["sum"] == 40
    assert result["mean"] == 5
    assert result["min"] == 2
    assert result["max"] == 9
    assert result["stddev"] == pytest.approx(2.0)


def test_data_analyzer_rejects_bad_input():
    with pytest.raises(ToolError):
        execute_tool("data_analyzer", {"values": []})
    with pytest.raises(ToolError):
        execute_tool("data_analyzer", {"values": [1, "x"]})
    with pytest.raises(ToolError):
        execute_tool("data_analyzer", {"values": [1, float("nan")]})
    with pytest.raises(ToolError):
        execute_tool("data_analyzer", {"values": [1] * 10001})


def test_execute_unknown_tool_and_bad_arguments():
    with pytest.raises(ToolError) as exc:
        execute_tool("shell", {"command": "rm -rf /"})
    assert exc.value.code == "tool_not_allowed"
    with pytest.raises(ToolError):
        execute_tool("calculator", {"expression": "1+1", "extra": "nope"})
    with pytest.raises(ToolError):
        execute_tool("calculator", "not-a-dict")


def test_is_tool_allowed_requires_registry_and_enabled():
    assert is_tool_allowed("calculator", ["calculator", "datetime"])
    assert not is_tool_allowed("calculator", ["datetime"])
    assert not is_tool_allowed("shell", ["shell"])
    assert not is_tool_allowed("document_search", ["document_search"])


def test_catalog_lists_executable_and_deferred():
    catalog = tool_catalog()
    available = {item["name"] for item in catalog if item["available"]}
    deferred = {item["name"] for item in catalog if not item["available"]}
    assert available == set(TOOL_REGISTRY)
    assert deferred == {item["name"] for item in DEFERRED_TOOLS}
    for item in catalog:
        if item["available"]:
            assert item["parameters"]["type"] == "object"
        else:
            assert item["phase"] in (6, 7)


def test_results_are_bounded_and_json_safe():
    import json

    for name, args in [
        ("calculator", {"expression": "sqrt(2)"}),
        ("datetime", {"operation": "now"}),
        ("data_analyzer", {"values": [1, 2, 3]}),
    ]:
        result = execute_tool(name, args)
        encoded = json.dumps(result)
        assert len(encoded) < 4000
        assert math.isfinite(result.get("result", 0)) if name == "calculator" else True