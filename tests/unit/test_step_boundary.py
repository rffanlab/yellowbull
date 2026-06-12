"""T03-10: 步骤执行边界场景测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from yellowbull.agent.step_state import ContextStore
from yellowbull.agent.executor import StepExecutor, StepResultData
from yellowbull.models.step import Step
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockTool(Tool):
    """模拟工具"""

    model_config = {"extra": "allow"}

    def __init__(self, name: str, fail: bool = False, slow: bool = False, raise_exc: bool = False, long_output: bool = False):
        super().__init__(name=name, description="Mock 工具")
        self._fail = fail
        self._slow = slow
        self._raise_exc = raise_exc
        self._long_output = long_output

    async def execute(self, params: dict) -> ToolResult:
        if self._raise_exc:
            raise RuntimeError("tool_exception")
        if self._slow:
            await asyncio.sleep(10)
        if self._fail:
            return ToolResult(success=False, error="tool_error")
        if self._long_output:
            return ToolResult(success=True, output="x" * 100_000)
        return ToolResult(success=True, output="mock_result")


class TestStepBoundary:
    """T03-10: 步骤执行边界场景"""

    def test_empty_tool_hint(self):
        """TC-03-10-01: 步骤无 tool_hint"""
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=2)

        step = Step(
            step_id="s1",
            description="空 tool_hint 步骤",
            tool_hint="",
        )
        # 空 tool_hint 应返回 None 工具
        assert executor._resolve_tool("") is None

    def test_invalid_tool_hint(self):
        """TC-03-10-02: tool_hint 无效"""
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=2)

        step = Step(
            step_id="s1",
            description="无效 tool_hint 步骤",
            tool_hint="nonexistent_tool",
        )
        assert executor._resolve_tool("nonexistent_tool") is None

    @pytest.mark.asyncio
    async def test_tool_timeout(self):
        """TC-03-10-03: 工具调用超时"""
        context_store = ContextStore("task_1")
        mock_tool = _MockTool("slow_tool", slow=True)
        ToolRegistry.register(mock_tool)

        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=0.1)

        step = Step(
            step_id="s1",
            description="超时步骤",
            tool_hint="slow_tool",
        )
        result = await executor.execute(step)
        assert result.success is False
        assert "超时" in result.error or "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_tool_exception(self):
        """TC-03-10-04: 工具返回异常"""
        context_store = ContextStore("task_1")
        mock_tool = _MockTool("exception_tool", raise_exc=True)
        ToolRegistry.register(mock_tool)

        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=2)

        step = Step(
            step_id="s1",
            description="异常步骤",
            tool_hint="exception_tool",
        )
        result = await executor.execute(step)
        assert result.success is False
        assert "tool_exception" in result.error

    def test_missing_input_params(self):
        """TC-03-10-05: 步骤参数缺失"""
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=2)

        step = Step(
            step_id="s1",
            description="参数缺失步骤",
            tool_hint="mock_tool",
            input_from=["nonexistent_step"],
        )
        inputs = executor._collect_inputs(step)
        # 缺失的输入不会报错，只是返回空 dict
        assert inputs == {}

    def test_input_type_error(self):
        """TC-03-10-06: 步骤参数类型错误"""
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=2)

        context_store.set("s0", 123)
        step = Step(
            step_id="s1",
            description="类型错误步骤",
            tool_hint="mock_tool",
            input_from=["s0"],
            input_format="json",
        )
        inputs = executor._collect_inputs(step)
        # 数字可以被 str() 转换后 json.loads 解析为数字，所以应该通过
        ok, err = executor._validate_input_format(inputs, "json")
        assert ok is True

    @pytest.mark.asyncio
    async def test_long_result_handling(self):
        """TC-03-10-07: 步骤结果超长"""
        context_store = ContextStore("task_1")
        mock_tool = _MockTool("long_tool", long_output=True)
        ToolRegistry.register(mock_tool)

        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=2)

        step = Step(
            step_id="s1",
            description="超长结果步骤",
            tool_hint="long_tool",
        )
        # 超长结果不应导致崩溃
        result = await executor.execute(step)
        # 结果被正常处理
        assert isinstance(result, StepResultData)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_concurrent_step_execution(self):
        """TC-03-10-08: 步骤并发执行"""
        context_store = ContextStore("task_1")
        mock_tool = _MockTool("concurrent_tool")
        ToolRegistry.register(mock_tool)

        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        executor = StepExecutor(context_store, llm_client, step_timeout=2)

        steps = [
            Step(step_id=f"s{i}", description=f"步骤{i}", tool_hint="concurrent_tool")
            for i in range(5)
        ]

        results = await asyncio.gather(
            *[executor.execute(s) for s in steps]
        )
        # 所有步骤都成功
        assert all(r.success for r in results)
        # 结果不冲突
        assert len(set(r.step_id for r in results)) == 5
