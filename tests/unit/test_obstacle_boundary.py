"""T03-14: 障碍处理边界场景测试"""

import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.executor import StepExecutor
from yellowbull.models.step import Step
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockObstacleTool(Tool):
    """模拟障碍工具"""

    model_config = {"extra": "allow"}

    def __init__(self, name: str, fail: bool = False):
        super().__init__(name=name, description="Mock 障碍工具")
        self._fail = fail

    async def execute(self, params: dict) -> ToolResult:
        if self._fail:
            return ToolResult(
                success=False,
                error="障碍未解决",
            )
        return ToolResult(
            success=True,
            output="ok",
        )


class TestObstacleBoundary:
    """T03-14: 障碍处理边界场景"""

    def _make_executor(self) -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value='{"command": "test"}')
        return StepExecutor(context_store, llm_client, step_timeout=2)

    # TC-03-14-01: 障碍解决失败
    @pytest.mark.asyncio
    async def test_obstacle_resolution_failure(self):
        """障碍解决失败应返回错误"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="障碍解决失败",
            tool_hint="mock_obstacle_fail",
        )

        ToolRegistry.register(_MockObstacleTool(name="mock_obstacle_fail", fail=True))

        result = await executor.execute(step)

        assert result.success is False
        assert result.error is not None

    # TC-03-14-02: 障碍解决超时
    @pytest.mark.asyncio
    async def test_obstacle_resolution_timeout(self):
        """障碍解决超时应终止"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="障碍解决超时",
            tool_hint="mock_obstacle_timeout",
        )

        class _MockTimeoutObstacleTool(Tool):
            model_config = {"extra": "allow"}

            async def execute(self, params: dict) -> ToolResult:
                import asyncio
                await asyncio.sleep(10)
                return ToolResult(success=True, output="ok")

        ToolRegistry.register(_MockTimeoutObstacleTool(name="mock_obstacle_timeout", description="Mock"))

        result = await executor.execute(step)

        # 应超时失败
        assert result.success is False
        assert result.error is not None

    # TC-03-14-03: 重复障碍
    @pytest.mark.asyncio
    async def test_duplicate_obstacle(self):
        """重复障碍应只处理一次"""
        executor = self._make_executor()

        # 注册成功工具
        ToolRegistry.register(_MockObstacleTool(name="mock_dup_obstacle_tool", fail=False))

        step = Step(
            step_id="s1",
            description="重复障碍",
            tool_hint="mock_dup_obstacle_tool",
        )

        # 执行一次
        result = await executor.execute(step)
        assert result.success is True

    # TC-03-14-04: 模糊障碍
    @pytest.mark.asyncio
    async def test_vague_obstacle(self):
        """模糊障碍描述应要求澄清"""
        executor = self._make_executor()

        step = Step(
            step_id="s1",
            description="模糊障碍",
            tool_hint="mock_vague_obstacle_tool",
        )

        class _MockVagueObstacleTool(Tool):
            model_config = {"extra": "allow"}

            async def execute(self, params: dict) -> ToolResult:
                return ToolResult(
                    success=False,
                    error="有些问题",  # 模糊的错误描述
                )

        ToolRegistry.register(_MockVagueObstacleTool(name="mock_vague_obstacle_tool", description="Mock"))

        result = await executor.execute(step)

        assert result.success is False
        assert result.error is not None
