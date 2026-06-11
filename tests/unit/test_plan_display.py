"""T01-12: 计划展示模块单元测试"""

import pytest

from yellowbull.agent.plan_display import PlanDisplay
from yellowbull.agent.receiver import DangerLevel
from yellowbull.models.step import Step
from yellowbull.models.task import Task, TaskStatus


@pytest.fixture
def display():
    return PlanDisplay()


@pytest.fixture
def sample_task():
    return Task(
        goal="读取 src/main.py 并检查语法",
        constraints=["不修改文件"],
        success_criteria=["完成语法检查"],
        confidence=0.6,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def sample_steps():
    return [
        Step(step_id="step_1", description="读取文件", tool_hint="file", is_critical=True),
        Step(step_id="step_2", description="语法检查", tool_hint="code", is_critical=True, depends_on=["step_1"]),
    ]


class TestRenderPlan:
    """TC-01-12-01 ~ TC-01-12-04"""

    def test_basic_render(self, display, sample_task, sample_steps):
        """TC-01-12-01: 基本渲染"""
        text = display.render_plan(sample_task, sample_steps)
        assert "任务执行计划" in text
        assert sample_task.goal in text
        assert "读取文件" in text

    def test_render_with_constraints(self, display, sample_task, sample_steps):
        """TC-01-12-02: 含约束条件"""
        text = display.render_plan(sample_task, sample_steps)
        assert "约束条件" in text
        assert "不修改文件" in text

    def test_render_with_success_criteria(self, display, sample_task, sample_steps):
        """TC-01-12-03: 含成功标准"""
        text = display.render_plan(sample_task, sample_steps)
        assert "成功标准" in text

    def test_render_step_count(self, display, sample_task, sample_steps):
        """TC-01-12-04: 步骤数显示"""
        text = display.render_plan(sample_task, sample_steps)
        assert "共 2 步" in text

    def test_render_confidence(self, display, sample_task, sample_steps):
        """TC-01-12-05: 置信度显示"""
        text = display.render_plan(sample_task, sample_steps)
        assert "置信度" in text

    def test_render_confirmation_hint(self, display, sample_task, sample_steps):
        """TC-01-12-06: 确认提示"""
        text = display.render_plan(sample_task, sample_steps)
        assert "确认" in text or "取消" in text


class TestRenderStepLine:
    """TC-01-12-07 ~ TC-01-12-09"""

    def test_normal_step(self, display):
        """TC-01-12-07: 普通步骤"""
        step = Step(step_id="step_1", description="读取文件", tool_hint="file")
        line = display.render_step_line(1, step)
        assert "[文件]" in line
        assert "读取文件" in line

    def test_critical_step(self, display):
        """TC-01-12-08: 关键步骤标记"""
        step = Step(step_id="step_1", description="关键操作", tool_hint="file", is_critical=True)
        line = display.render_step_line(1, step)
        assert "★" in line

    def test_step_with_dependencies(self, display):
        """TC-01-12-09: 依赖显示"""
        step = Step(
            step_id="step_2",
            description="后续操作",
            tool_hint="code",
            depends_on=["step_1"],
        )
        line = display.render_step_line(2, step)
        assert "依赖" in line
        assert "step_1" in line


class TestRenderWarning:
    """TC-01-12-10 ~ TC-01-12-12"""

    def test_green_no_warning(self, display):
        """TC-01-12-10: 绿色无警告"""
        steps = [Step(step_id="step_1", description="读取文件", tool_hint="file")]
        warning = display.render_warning(DangerLevel.GREEN, steps)
        assert warning is None

    def test_red_warning(self, display):
        """TC-01-12-11: 红色警告"""
        steps = [Step(step_id="step_1", description="删除文件", tool_hint="shell")]
        warning = display.render_warning(DangerLevel.RED, steps)
        assert warning is not None
        assert "高危" in warning

    def test_yellow_warning(self, display):
        """TC-01-12-12: 黄色警告"""
        steps = [Step(step_id="step_1", description="安装依赖", tool_hint="shell")]
        warning = display.render_warning(DangerLevel.YELLOW, steps)
        assert warning is not None
        assert "注意" in warning or "警告" in warning

    def test_danger_step_ids_shown(self, display):
        """TC-01-12-13: 危险步骤 ID 显示"""
        steps = [Step(step_id="step_1", description="删除文件", tool_hint="shell")]
        warning = display.render_warning(DangerLevel.RED, steps)
        assert "step_1" in warning
