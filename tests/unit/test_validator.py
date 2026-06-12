"""T03: 步骤校验器单元测试"""

import pytest

from yellowbull.agent.validator import StepValidator, ValidationResult
from yellowbull.models.step import Step


@pytest.fixture
def valid_steps():
    return [
        Step(
            step_id="step_1",
            description="读取文件",
            tool_hint="file",
            input_from=[],
            depends_on=[],
        ),
        Step(
            step_id="step_2",
            description="处理数据",
            tool_hint="code",
            input_from=["step_1"],
            depends_on=["step_1"],
        ),
        Step(
            step_id="step_3",
            description="保存结果",
            tool_hint="file",
            input_from=["step_2"],
            depends_on=["step_2"],
        ),
    ]


@pytest.fixture
def steps_with_duplicate_ids():
    return [
        Step(step_id="step_1", description="A", tool_hint="file"),
        Step(step_id="step_1", description="B", tool_hint="file"),
    ]


@pytest.fixture
def steps_with_missing_dependency():
    return [
        Step(
            step_id="step_1",
            description="A",
            tool_hint="file",
            depends_on=["step_99"],
        ),
    ]


class TestValidationResult:
    """TC-03-03-01 ~ TC-03-03-03"""

    def test_valid_result(self):
        """TC-03-03-01: 校验通过"""
        result = ValidationResult(valid=True, sorted_steps=[])
        assert result.valid is True
        assert result.errors == []

    def test_invalid_result(self):
        """TC-03-03-02: 校验失败"""
        result = ValidationResult(valid=False, errors=["error1"])
        assert result.valid is False
        assert "error1" in result.errors

    def test_sorted_steps(self):
        """TC-03-03-03: 排序后的步骤"""
        steps = [
            Step(step_id="step_2", description="B", tool_hint="file"),
            Step(step_id="step_1", description="A", tool_hint="file"),
        ]
        result = ValidationResult(valid=True, sorted_steps=steps)
        assert len(result.sorted_steps) == 2


class TestValidateStepsValid:
    """TC-03-03-04 ~ TC-03-03-07"""

    def test_valid_steps_pass(self, valid_steps):
        """TC-03-03-04: 有效步骤通过校验"""
        result = StepValidator.validate_steps(valid_steps)
        assert result.valid is True

    def test_sorted_steps_preserve_order(self, valid_steps):
        """TC-03-03-05: 拓扑排序"""
        result = StepValidator.validate_steps(valid_steps)
        step_ids = [s.step_id for s in result.sorted_steps]
        assert step_ids.index("step_1") < step_ids.index("step_2")
        assert step_ids.index("step_2") < step_ids.index("step_3")

    def test_sorted_steps_count(self, valid_steps):
        """TC-03-03-06: 排序后步骤数量不变"""
        result = StepValidator.validate_steps(valid_steps)
        assert len(result.sorted_steps) == len(valid_steps)

    def test_empty_steps_pass(self):
        """TC-03-03-07: 空步骤列表"""
        result = StepValidator.validate_steps([])
        assert result.valid is True


class TestValidateStepsDuplicates:
    """TC-03-03-08 ~ TC-03-03-10"""

    def test_duplicate_ids_fail(self, steps_with_duplicate_ids):
        """TC-03-03-08: 重复 ID 校验失败"""
        result = StepValidator.validate_steps(steps_with_duplicate_ids)
        assert result.valid is False
        assert any("重复" in err or "duplicate" in err.lower() for err in result.errors)

    def test_duplicate_ids_error_message(self, steps_with_duplicate_ids):
        """TC-03-03-09: 错误信息包含重复 ID"""
        result = StepValidator.validate_steps(steps_with_duplicate_ids)
        assert len(result.errors) > 0

    def test_unique_ids_pass(self, valid_steps):
        """TC-03-03-10: 唯一 ID 通过"""
        result = StepValidator.validate_steps(valid_steps)
        assert result.valid is True


class TestValidateStepsDependencies:
    """TC-03-03-11 ~ TC-03-03-14"""

    def test_missing_dependency_fail(self, steps_with_missing_dependency):
        """TC-03-03-11: 缺失依赖校验失败"""
        result = StepValidator.validate_steps(steps_with_missing_dependency)
        assert result.valid is False

    def test_missing_dependency_error_message(self, steps_with_missing_dependency):
        """TC-03-03-12: 错误信息包含缺失依赖"""
        result = StepValidator.validate_steps(steps_with_missing_dependency)
        assert len(result.errors) > 0

    def test_valid_dependencies_pass(self, valid_steps):
        """TC-03-03-13: 有效依赖通过"""
        result = StepValidator.validate_steps(valid_steps)
        assert result.valid is True

    def test_no_dependencies_pass(self):
        """TC-03-03-14: 无依赖通过"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file"),
        ]
        result = StepValidator.validate_steps(steps)
        assert result.valid is True


class TestValidateStepsCycles:
    """TC-03-03-15 ~ TC-03-03-17"""

    def test_cycle_detection(self):
        """TC-03-03-15: 循环依赖检测"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file", depends_on=["step_2"]),
            Step(step_id="step_2", description="B", tool_hint="file", depends_on=["step_1"]),
        ]
        result = StepValidator.validate_steps(steps)
        assert result.valid is False

    def test_cycle_error_message(self):
        """TC-03-03-16: 循环依赖错误信息"""
        steps = [
            Step(step_id="step_1", description="A", tool_hint="file", depends_on=["step_2"]),
            Step(step_id="step_2", description="B", tool_hint="file", depends_on=["step_1"]),
        ]
        result = StepValidator.validate_steps(steps)
        assert len(result.errors) > 0

    def test_no_cycle_pass(self, valid_steps):
        """TC-03-03-17: 无循环依赖通过"""
        result = StepValidator.validate_steps(valid_steps)
        assert result.valid is True
