"""T01-10: ContextStore 单元测试"""

import pytest

from yellowbull.agent.context_store import ContextStore, StepOutput
from yellowbull.models.step import Step


@pytest.fixture
def context_store():
    return ContextStore(task_id="task_001")


@pytest.fixture
def sample_step():
    return Step(
        step_id="step_1",
        description="读取文件",
        tool_hint="file",
        input_from=[],
        depends_on=[],
    )


@pytest.fixture
def sample_output():
    return StepOutput(
        step_id="step_1",
        data="文件内容",
        output_format="text",
    )


class TestContextStoreBasic:
    """TC-01-10-01 ~ TC-01-10-04"""

    def test_store_and_get(self, context_store, sample_output):
        """TC-01-10-01: 存储和获取"""
        context_store.store("step_1", sample_output)
        result = context_store.get("step_1")
        assert result is not None
        assert result.step_id == "step_1"
        assert result.data == "文件内容"

    def test_get_nonexistent(self, context_store):
        """TC-01-10-02: 获取不存在的 key"""
        result = context_store.get("nonexistent")
        assert result is None

    def test_contains(self, context_store, sample_output):
        """TC-01-10-03: __contains__"""
        context_store.store("step_1", sample_output)
        assert "step_1" in context_store
        assert "step_2" not in context_store

    def test_len(self, context_store, sample_output):
        """TC-01-10-04: __len__"""
        assert len(context_store) == 0
        context_store.store("step_1", sample_output)
        assert len(context_store) == 1

    def test_clear(self, context_store, sample_output):
        """TC-01-10-05: clear"""
        context_store.store("step_1", sample_output)
        context_store.clear()
        assert len(context_store) == 0
        assert context_store.get("step_1") is None


class TestGatherInputs:
    """TC-01-10-06 ~ TC-01-10-08"""

    def test_gather_no_inputs(self, context_store, sample_step, sample_output):
        """TC-01-10-06: 无依赖的步骤"""
        context_store.store("step_1", sample_output)
        inputs = context_store.gather_inputs(sample_step)
        assert inputs == {}

    def test_gather_with_inputs(self, context_store):
        """TC-01-10-07: 有依赖的步骤"""
        out1 = StepOutput(step_id="step_1", data="data1")
        out2 = StepOutput(step_id="step_2", data="data2")
        context_store.store("step_1", out1)
        context_store.store("step_2", out2)

        step = Step(
            step_id="step_3",
            description="合并",
            tool_hint="file",
            input_from=["step_1", "step_2"],
        )
        inputs = context_store.gather_inputs(step)
        assert "step_1" in inputs
        assert "step_2" in inputs

    def test_gather_missing_dependency(self, context_store):
        """TC-01-10-08: 依赖缺失"""
        out1 = StepOutput(step_id="step_1", data="data1")
        context_store.store("step_1", out1)

        step = Step(
            step_id="step_3",
            description="合并",
            tool_hint="file",
            input_from=["step_1", "step_2"],
        )
        with pytest.raises(RuntimeError, match="未满足"):
            context_store.gather_inputs(step)


class TestHasAllInputs:
    """TC-01-10-09 ~ TC-01-10-10"""

    def test_has_all_true(self, context_store):
        out1 = StepOutput(step_id="step_1", data="data1")
        context_store.store("step_1", out1)

        step = Step(
            step_id="step_2",
            description="后续步骤",
            tool_hint="file",
            input_from=["step_1"],
        )
        assert context_store.has_all_inputs(step) is True

    def test_has_all_false(self, context_store):
        step = Step(
            step_id="step_2",
            description="后续步骤",
            tool_hint="file",
            input_from=["step_1"],
        )
        assert context_store.has_all_inputs(step) is False

    def test_has_all_no_inputs(self, context_store):
        step = Step(
            step_id="step_1",
            description="无依赖",
            tool_hint="file",
            input_from=[],
        )
        assert context_store.has_all_inputs(step) is True
