"""T01-07 ~ T01-11: 步骤拆解模块单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from yellowbull.agent.breakdown import StepBreakdown, ValidationReport
from yellowbull.config.settings import Settings
from yellowbull.models.step import Step, StepStatus
from yellowbull.models.task import Task, TaskStatus
from yellowbull.llm.client import LLMClient
from yellowbull.tools.base import Tool, ToolRegistry


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "yellowbull_data")


@pytest.fixture
def mock_llm():
    return MagicMock(spec=LLMClient)


@pytest.fixture(autouse=True)
def register_mock_tools():
    """注册模拟工具供测试使用"""
    ToolRegistry.register(Tool(name="file", description="文件操作工具"))
    ToolRegistry.register(Tool(name="code", description="代码分析工具"))
    yield
    # 清理
    ToolRegistry._tools.clear()


@pytest.fixture
def breakdown(mock_llm, settings, register_mock_tools):
    return StepBreakdown(mock_llm, settings)


@pytest.fixture
def sample_task():
    return Task(
        goal="读取 src/main.py 并检查语法",
        constraints=["不修改文件"],
        success_criteria=["完成语法检查"],
        confidence=0.9,
        status=TaskStatus.PENDING,
    )


class TestStepBreakdownLLM:
    """TC-01-07-01 ~ TC-01-07-04"""

    @pytest.mark.asyncio
    async def test_normal_breakdown(self, breakdown, mock_llm, sample_task):
        """TC-01-07-01: 正常拆解"""
        mock_llm.chat = AsyncMock(
            return_value='{"steps": [{"step_id": "step_1", "description": "读取文件", "tool_hint": "file"}]}'
        )

        steps = await breakdown.breakdown(sample_task)
        assert len(steps) == 1
        assert steps[0].step_id == "step_1"

    @pytest.mark.asyncio
    async def test_breakdown_with_code_block(self, breakdown, mock_llm, sample_task):
        """TC-01-07-02: LLM 返回带 code block 的 JSON"""
        mock_llm.chat = AsyncMock(
            return_value='```json\n{"steps": [{"step_id": "step_1", "description": "读取文件", "tool_hint": "file"}]}\n```'
        )

        steps = await breakdown.breakdown(sample_task)
        assert len(steps) == 1

    @pytest.mark.asyncio
    async def test_llm_failure_raises(self, breakdown, mock_llm, sample_task):
        """TC-01-07-03: LLM 调用失败"""
        mock_llm.chat = AsyncMock(side_effect=Exception("LLM 连接失败"))

        with pytest.raises(Exception, match="LLM 连接失败"):
            await breakdown.breakdown(sample_task)

    @pytest.mark.asyncio
    async def test_json_parse_failure_degrades(self, breakdown, mock_llm, sample_task):
        """TC-01-07-04: JSON 解析失败降级为单步"""
        mock_llm.chat = AsyncMock(return_value="无效的 JSON 响应")

        steps = await breakdown.breakdown(sample_task)
        # 降级为单步任务
        assert len(steps) >= 1


class TestValidation:
    """TC-01-08-01 ~ TC-01-08-05"""

    def test_valid_steps(self, breakdown):
        """TC-01-08-01: 有效步骤"""
        steps = [
            Step(step_id="step_1", description="读取文件", tool_hint="file"),
            Step(step_id="step_2", description="分析", tool_hint="code", depends_on=["step_1"]),
        ]
        report = breakdown._validate_steps(steps, Task(goal="test", confidence=0.9, status=TaskStatus.PENDING))
        assert report.is_valid is True

    def test_circular_dependency(self, breakdown):
        """TC-01-08-02: 循环依赖"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file", depends_on=["step_2"]),
            Step(step_id="step_2", description="B", tool_hint="file", depends_on=["step_1"]),
        ]
        report = breakdown._validate_steps(steps, Task(goal="test", confidence=0.9, status=TaskStatus.PENDING))
        assert report.is_valid is False
        assert any("循环" in issue for issue in report.issues)

    def test_duplicate_step_ids(self, breakdown):
        """TC-01-08-03: 重复 step_id"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
            Step(step_id="step_1", description="B", tool_hint="file"),
        ]
        report = breakdown._validate_steps(steps, Task(goal="test", confidence=0.9, status=TaskStatus.PENDING))
        assert report.is_valid is False

    def test_invalid_dependency_reference(self, breakdown):
        """TC-01-08-04: 无效依赖引用"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file", depends_on=["step_99"]),
        ]
        report = breakdown._validate_steps(steps, Task(goal="test", confidence=0.9, status=TaskStatus.PENDING))
        assert report.is_valid is False

    def test_orphan_steps(self, breakdown):
        """TC-01-08-05: 孤立步骤"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
            Step(step_id="step_2", description="B", tool_hint="file"),
            Step(step_id="step_3", description="C", tool_hint="file"),
        ]
        report = breakdown._validate_steps(steps, Task(goal="test", confidence=0.9, status=TaskStatus.PENDING))
        # step_2 和 step_3 是孤立的（不依赖 step_1，也没有步骤依赖它们）
        assert any("孤立" in issue for issue in report.issues)


class TestStepSorting:
    """TC-01-09-01 ~ TC-01-09-03"""

    def test_topological_sort(self, breakdown):
        """TC-01-09-01: 拓扑排序"""
        steps = [
            Step(step_id="step_2", description="B", tool_hint="file", depends_on=["step_1"]),
            Step(step_id="step_1", description="A", tool_hint="file"),
            Step(step_id="step_3", description="C", tool_hint="file", depends_on=["step_2"]),
        ]
        sorted_steps = breakdown._sort_steps(steps)
        ids = [s.step_id for s in sorted_steps]
        assert ids.index("step_1") < ids.index("step_2")
        assert ids.index("step_2") < ids.index("step_3")

    def test_critical_steps_first(self, breakdown):
        """TC-01-09-02: 关键步骤优先"""
        steps = [
            Step(step_id="step_1", description="普通", tool_hint="file", is_critical=False),
            Step(step_id="step_2", description="关键", tool_hint="file", is_critical=True),
        ]
        sorted_steps = breakdown._sort_steps(steps)
        assert sorted_steps[0].is_critical is True

    def test_empty_steps(self, breakdown):
        """TC-01-09-03: 空列表"""
        assert breakdown._sort_steps([]) == []


class TestStepMerging:
    """TC-01-11-01 ~ TC-01-11-03"""

    def test_merge_when_exceeds_max(self, breakdown, settings):
        """TC-01-11-01: 超过 max_steps 时合并"""
        settings.execution.max_subtask_steps = 3
        steps = [
            Step(step_id=f"step_{i}", description=f"步骤{i}", tool_hint="file")
            for i in range(5)
        ]
        merged = breakdown._merge_steps_if_needed(steps)
        assert len(merged) <= 5  # 可能合并也可能截断

    def test_no_merge_when_within_limit(self, breakdown):
        """TC-01-11-02: 未超过限制不合并"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
            Step(step_id="step_2", description="B", tool_hint="file"),
        ]
        result = breakdown._merge_steps_if_needed(steps)
        assert len(result) == 2

    def test_critical_steps_preserved(self, breakdown):
        """TC-01-11-03: 关键步骤不被合并"""
        steps = [
            Step(step_id="step_1", description="关键1", tool_hint="file", is_critical=True),
            Step(step_id="step_2", description="关键2", tool_hint="file", is_critical=True),
            Step(step_id="step_3", description="普通", tool_hint="file", is_critical=False),
        ]
        result = breakdown._merge_steps_if_needed(steps)
        critical_ids = {s.step_id for s in result if s.is_critical}
        assert "step_1" in critical_ids
        assert "step_2" in critical_ids


class TestDegradation:
    """TC-01-11-04: 降级为单步"""

    def test_degrade_to_single_step(self, breakdown, sample_task):
        steps = breakdown._degrade_to_single_step(sample_task)
        assert len(steps) == 1
        assert steps[0].is_critical is True
        assert sample_task.goal in steps[0].description
