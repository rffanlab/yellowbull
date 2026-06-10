"""T00-04: 核心数据模型单元测试"""

import json

import pytest
from pydantic import ValidationError

from yellowbull.models.experience import Experience
from yellowbull.models.result import StepResult, TaskConclusion, TaskResult
from yellowbull.models.step import Step, StepStatus
from yellowbull.models.subtask import SubTask
from yellowbull.models.task import Task, TaskStatus


class TestTaskModel:
    """TC-00-04-01: Task 序列化"""

    def test_create_task(self):
        task = Task(goal="test task", confidence=0.9)
        assert task.goal == "test task"
        assert task.confidence == 0.9
        assert task.status == TaskStatus.PENDING
        assert task.id is not None

    def test_task_json_serialization(self):
        """TC-00-04-01: Task JSON 序列化"""
        task = Task(goal="test", confidence=0.8, constraints=["c1"])
        data = task.model_dump_json()
        assert isinstance(data, str)
        parsed = json.loads(data)
        assert parsed["goal"] == "test"
        assert parsed["status"] == "pending"

    def test_task_default_values(self):
        """TC-00-04-05: 默认值验证"""
        task = Task(goal="test", confidence=0.5)
        assert task.constraints == []
        assert task.success_criteria == []
        assert task.context_files == []

    def test_task_status_update(self):
        task = Task(goal="test", confidence=0.5)
        task.status = TaskStatus.RUNNING
        assert task.status == TaskStatus.RUNNING


class TestStepModel:
    """TC-00-04-02: Step 分支字段"""

    def test_basic_step(self):
        step = Step(step_id="s1", description="do something", tool_hint="file")
        assert step.step_id == "s1"
        assert step.status == StepStatus.PENDING

    def test_branch_step(self):
        """TC-00-04-02: 分支字段"""
        step = Step(
            step_id="s1",
            description="branch",
            tool_hint="shell",
            is_branch_point=True,
            branch_condition="file_exists",
            true_next=["s2"],
            false_next=["s3"],
        )
        assert step.is_branch_point is True
        assert step.true_next == ["s2"]
        assert step.false_next == ["s3"]

    def test_loop_step(self):
        step = Step(
            step_id="s1",
            description="loop",
            tool_hint="file",
            is_loop=True,
            loop_input_step="s0",
            loop_item_variable="item",
        )
        assert step.is_loop is True

    def test_step_default_values(self):
        step = Step(step_id="s1", description="test", tool_hint="file")
        assert step.depends_on == []
        assert step.is_critical is False
        assert step.output_format == "text"


class TestEnumSerialization:
    """TC-00-04-03: 枚举序列化"""

    def test_task_status_enum(self):
        task = Task(goal="test", confidence=0.5)
        data = task.model_dump()
        assert data["status"] == TaskStatus.PENDING
        assert str(data["status"]) == "pending"

    def test_step_status_enum(self):
        step = Step(step_id="s1", description="test", tool_hint="file")
        assert step.status == StepStatus.PENDING
        step.status = StepStatus.DONE
        assert step.status == StepStatus.DONE

    def test_task_conclusion_enum(self):
        assert TaskConclusion.SUCCESS.value == "success"
        assert TaskConclusion.FAILURE.value == "failure"

    def test_invalid_enum_value(self):
        """TC-00-15-01: 枚举值非法"""
        with pytest.raises(ValidationError):
            Task(goal="test", confidence=0.5, status="invalid_status")


class TestNestedModels:
    """TC-00-04-04: 嵌套模型序列化"""

    def test_task_result_with_step_results(self):
        step_result = StepResult(step_id="s1", status=StepStatus.DONE)
        task_result = TaskResult(
            task_id="t1",
            conclusion=TaskConclusion.SUCCESS,
            achievement_score=0.95,
            step_results=[step_result],
        )
        data = task_result.model_dump_json()
        parsed = json.loads(data)
        assert parsed["task_id"] == "t1"
        assert len(parsed["step_results"]) == 1
        assert parsed["step_results"][0]["step_id"] == "s1"

    def test_task_result_with_subtasks(self):
        subtask_result = TaskResult(
            task_id="st1",
            conclusion=TaskConclusion.SUCCESS,
            achievement_score=0.8,
            step_results=[],
        )
        task_result = TaskResult(
            task_id="t1",
            conclusion=TaskConclusion.SUCCESS,
            achievement_score=0.9,
            step_results=[],
            subtask_results=[subtask_result],
        )
        data = task_result.model_dump()
        assert len(data["subtask_results"]) == 1

    def test_step_result_defaults(self):
        step_result = StepResult(step_id="s1", status=StepStatus.DONE)
        assert step_result.retry_count == 0
        assert step_result.duration_seconds == 0
        assert step_result.side_effects == []


class TestExperienceModel:
    """TC-00-04-05: 经验模型"""

    def test_create_experience(self):
        exp = Experience(id="e1", task_summary="test", task_category="dev", outcome="success", score=0.8)
        assert exp.id == "e1"
        assert exp.score == 0.8
        assert exp.lessons_learned == ""

    def test_experience_with_all_fields(self):
        exp = Experience(
            id="e1",
            task_summary="test",
            task_category="dev",
            outcome="success",
            score=0.9,
            lessons_learned="useful lesson",
            tool_chain=["file", "shell"],
            keywords=["python", "test"],
            tags=["important"],
            is_permanent=True,
        )
        assert exp.is_permanent is True
        assert len(exp.keywords) == 2

    def test_experience_defaults(self):
        exp = Experience(id="e1", task_summary="s", task_category="c", outcome="o", score=0.5)
        assert exp.steps_count == 0
        assert exp.success_rate == 0.0
        assert exp.generality == 0.5


class TestSubTaskModel:
    """子任务模型"""

    def test_create_subtask(self):
        step = Step(step_id="s1", description="step", tool_hint="file")
        subtask = SubTask(
            parent_task_id="t1",
            parent_step_id="s0",
            goal="sub goal",
            obstacle_description="an obstacle",
            steps=[step],
        )
        assert subtask.parent_task_id == "t1"
        assert len(subtask.steps) == 1

    def test_subtask_defaults(self):
        step = Step(step_id="s1", description="step", tool_hint="file")
        subtask = SubTask(
            parent_task_id="t1",
            parent_step_id="s0",
            goal="goal",
            obstacle_description="obstacle",
            steps=[step],
        )
        assert subtask.context_inherit is True
        assert subtask.max_steps == 3


class TestModelBoundaries:
    """TC-00-15: 数据模型边界"""

    def test_long_field_storage(self):
        """TC-00-15-03: 字段超长"""
        long_text = "x" * 100_000
        task = Task(goal=long_text, confidence=0.5)
        assert len(task.goal) == 100_000

    def test_nested_none_handling(self):
        """TC-00-15-02: 嵌套模型空值"""
        result = TaskResult(
            task_id="t1",
            conclusion=TaskConclusion.SUCCESS,
            achievement_score=0.5,
            step_results=[],
        )
        assert result.step_results == []
