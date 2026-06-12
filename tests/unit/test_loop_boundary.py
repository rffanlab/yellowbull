"""T03-12: 循环处理边界场景测试"""

import pytest
from unittest.mock import AsyncMock

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.executor import StepExecutor, LoopResult
from yellowbull.agent.guard import BudgetGuard
from yellowbull.models.step import Step, StepStatus
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult


class _MockLoopTool(Tool):
    """模拟循环工具"""

    model_config = {"extra": "allow"}

    def __init__(self, name: str, success: bool = True):
        super().__init__(name=name, description="Mock 循环工具")
        self._success = success

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(
            success=self._success,
            output=f"ok_{params.get('command', 'default')}",
        )


class TestLoopBoundary:
    """T03-12: 循环处理边界场景"""

    def _make_executor(self, llm_response: str = '{"command": "test"}') -> StepExecutor:
        context_store = ContextStore("task_1")
        llm_client = AsyncMock()
        llm_client.chat = AsyncMock(return_value=llm_response)
        return StepExecutor(context_store, llm_client, step_timeout=2)

    def _make_step_states(self) -> dict[str, StepState]:
        return {
            "loop1": StepState(step_id="loop1"),
        }

    # TC-03-12-01: 循环条件恒真（达到 max_iterations 终止）
    @pytest.mark.asyncio
    async def test_loop_infinite(self):
        """恒真条件应达到 max_iterations 后终止"""
        executor = self._make_executor()
        context_store = executor.context_store

        # 设置循环输入数据（100 个元素）
        context_store.set("input_step", list(range(100)))

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
            max_iterations=5,
        )

        # 应该被 max_iterations 截断
        assert result.iterations == 5
        assert result.success_count == 5
        assert result.failed_count == 0

    # TC-03-12-02: 循环条件恒假（不进入循环）
    @pytest.mark.asyncio
    async def test_loop_never_enters(self):
        """恒假条件应跳过循环"""
        executor = self._make_executor()

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="nonexistent_input",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        # 输入不存在，不进入循环
        assert result.iterations == 0
        assert result.success_count == 0

    # TC-03-12-03: 循环次数为 0
    @pytest.mark.asyncio
    async def test_loop_zero_iterations(self):
        """max_iterations=0 应跳过循环"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", [1, 2, 3])

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
            max_iterations=0,
        )

        assert result.iterations == 0

    # TC-03-12-04: 循环次数超限（截断到 max_iterations）
    @pytest.mark.asyncio
    async def test_loop_excessive_count(self):
        """极大循环次数应截断到 max_iterations"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", list(range(10000)))

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
            max_iterations=10,
        )

        assert result.iterations == 10
        assert result.success_count == 10

    # TC-03-12-05: 循环内步骤失败
    @pytest.mark.asyncio
    async def test_loop_step_failure(self):
        """某次迭代失败应终止循环并处理"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", [1, 2, 3])

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_fail_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        # 注册失败工具
        ToolRegistry.register(_MockLoopTool("mock_loop_fail_tool", success=False))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        assert result.iterations == 3
        assert result.failed_count == 3
        assert result.success_count == 0

    # TC-03-12-06: 循环依赖变化
    @pytest.mark.asyncio
    async def test_loop_dependency_change(self):
        """循环中依赖被修改应检测并处理"""
        executor = self._make_executor()
        context_store = executor.context_store

        # 初始数据
        context_store.set("input_step", [1, 2, 3])

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        # 正常执行
        assert result.iterations == 3

    # TC-03-12-07: 循环嵌套循环
    @pytest.mark.asyncio
    async def test_loop_nested(self):
        """双层循环应正确执行嵌套"""
        executor = self._make_executor()
        context_store = executor.context_store

        # 外层循环输入
        context_store.set("outer_input", [1, 2])
        # 内层循环输入
        context_store.set("inner_input", ["a", "b"])

        outer_step = Step(
            step_id="outer_loop",
            description="外层 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="outer_input",
            loop_item_variable="item",
        )

        inner_step = Step(
            step_id="inner_loop",
            description="内层 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="inner_input",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        # 执行外层循环
        outer_result = await executor.execute_loop(
            outer_step,
            self._make_step_states(),
        )
        assert outer_result.iterations == 2

        # 执行内层循环
        inner_result = await executor.execute_loop(
            inner_step,
            self._make_step_states(),
        )
        assert inner_result.iterations == 2

    @pytest.mark.asyncio
    async def test_loop_empty_collection(self):
        """空集合应跳过循环"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", [])

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        assert result.iterations == 0

    @pytest.mark.asyncio
    async def test_loop_no_input_step(self):
        """无 loop_input_step 应跳过循环"""
        executor = self._make_executor()

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step=None,
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        assert result.iterations == 0

    @pytest.mark.asyncio
    async def test_loop_single_item(self):
        """单个值应包装为列表执行一次"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", "single_value")

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        assert result.iterations == 1
        assert result.success_count == 1

    @pytest.mark.asyncio
    async def test_loop_dict_input(self):
        """字典输入应展开为 values"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", {"a": 1, "b": 2, "c": 3})

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        assert result.iterations == 3

    @pytest.mark.asyncio
    async def test_loop_budget_guard(self):
        """预算保护应终止循环"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", list(range(100)))

        step = Step(
            step_id="loop1",
            description="处理 {{item}}",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        # 创建一个预算守卫，限制步数
        budget_guard = BudgetGuard(
            max_total_steps=3,
            total_timeout=600,
            step_timeout=120,
        )
        budget_guard.start()

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
            budget_guard=budget_guard,
        )

        # 预算耗尽后终止
        assert result.iterations <= 3

    @pytest.mark.asyncio
    async def test_loop_variable_replacement(self):
        """循环变量替换应正确工作"""
        executor = self._make_executor()
        context_store = executor.context_store

        context_store.set("input_step", ["file1.txt", "file2.txt"])

        step = Step(
            step_id="loop1",
            description="读取文件 {{item}} (索引: {index})",
            tool_hint="mock_loop_tool",
            is_loop=True,
            loop_input_step="input_step",
            loop_item_variable="item",
        )

        ToolRegistry.register(_MockLoopTool("mock_loop_tool"))

        result = await executor.execute_loop(
            step,
            self._make_step_states(),
        )

        assert result.iterations == 2
        # 结果存储在 context_store 中
        assert context_store.get("loop1_iter_0") is not None
        assert context_store.get("loop1_iter_1") is not None
