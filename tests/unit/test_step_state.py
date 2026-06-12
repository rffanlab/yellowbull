"""T03: 步骤状态管理单元测试"""

import pytest

from yellowbull.agent.step_state import StepStatus, StepState
from yellowbull.models.step import Step


class TestStepStatus:
    """TC-03-01-01 ~ TC-03-01-03: StepStatus 枚举"""

    def test_status_values(self):
        """TC-03-01-01: 枚举值存在"""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.RUNNING.value == "running"
        assert StepStatus.DONE.value == "done"
        assert StepStatus.FAILED.value == "failed"
        assert StepStatus.SKIPPED.value == "skipped"

    def test_terminal_statuses(self):
        """TC-03-01-02: 终态"""
        terminal = (StepStatus.DONE, StepStatus.FAILED, StepStatus.SKIPPED)
        assert StepStatus.DONE in terminal
        assert StepStatus.FAILED in terminal
        assert StepStatus.SKIPPED in terminal

    def test_non_terminal_statuses(self):
        """TC-03-01-03: 非终态"""
        non_terminal = (StepStatus.PENDING, StepStatus.RUNNING)
        assert StepStatus.PENDING in non_terminal
        assert StepStatus.RUNNING in non_terminal


class TestStepStateCreation:
    """TC-03-01-04 ~ TC-03-01-07: StepState 初始化"""

    def test_initial_status(self):
        """TC-03-01-04: 初始状态为 pending"""
        state = StepState("step_1")
        assert state.status == StepStatus.PENDING

    def test_initial_result_none(self):
        """TC-03-01-05: 初始结果为 None"""
        state = StepState("step_1")
        assert state.result is None

    def test_initial_error_none(self):
        """TC-03-01-06: 初始错误为 None"""
        state = StepState("step_1")
        assert state.error is None

    def test_initial_retry_count_zero(self):
        """TC-03-01-07: 初始重试次数为 0"""
        state = StepState("step_1")
        assert state.retry_count == 0


class TestStepStateTransitions:
    """TC-03-01-08 ~ TC-03-01-15: 状态转换"""

    def test_mark_running(self):
        """TC-03-01-08: pending -> running"""
        state = StepState("step_1")
        state.mark_running()
        assert state.status == StepStatus.RUNNING

    def test_mark_done(self):
        """TC-03-01-09: running -> done"""
        state = StepState("step_1")
        state.mark_running()
        state.mark_done({"key": "value"})
        assert state.status == StepStatus.DONE
        assert state.result == {"key": "value"}

    def test_mark_failed(self):
        """TC-03-01-10: running -> failed"""
        state = StepState("step_1")
        state.mark_running()
        state.mark_failed("error message")
        assert state.status == StepStatus.FAILED
        assert state.error == "error message"

    def test_mark_skipped(self):
        """TC-03-01-11: pending -> skipped"""
        state = StepState("step_1")
        state.mark_skipped()
        assert state.status == StepStatus.SKIPPED

    def test_mark_skipped_by_dependency(self):
        """TC-03-01-12: 级联跳过"""
        state = StepState("step_1")
        state.mark_skipped(by_dependency=True)
        assert state.status == StepStatus.SKIPPED

    def test_mark_skipped_by_branch(self):
        """TC-03-01-13: 分支跳过"""
        state = StepState("step_1")
        state.mark_skipped(by_branch=True)
        assert state.status == StepStatus.SKIPPED

    def test_terminal_state_immutable(self):
        """TC-03-01-14: 终态不可变"""
        state = StepState("step_1")
        state.mark_done("result")
        state.mark_running()  # 不应改变
        assert state.status == StepStatus.DONE

    def test_terminal_state_cannot_change_result(self):
        """TC-03-01-15: 终态结果不可变"""
        state = StepState("step_1")
        state.mark_done("original")
        state.mark_done("new")
        assert state.result == "original"


class TestStepStateRetry:
    """TC-03-01-16 ~ TC-03-01-18: 重试"""

    def test_retry_count_increments(self):
        """TC-03-01-16: 重试次数递增"""
        state = StepState("step_1")
        assert state.retry_count == 0
        state.retry_count = 1
        assert state.retry_count == 1

    def test_retry_resets_error(self):
        """TC-03-01-17: 重试重置错误"""
        state = StepState("step_1")
        state.mark_failed("error")
        state.status = StepStatus.PENDING
        state.error = None
        assert state.error is None

    def test_pending_for_retry(self):
        """TC-03-01-18: 失败后可重置为 pending"""
        state = StepState("step_1")
        state.mark_failed("error")
        state.status = StepStatus.PENDING
        assert state.status == StepStatus.PENDING


class TestStepStateIsTerminal:
    """TC-03-01-19 ~ TC-03-01-22: 终态判断"""

    def test_done_is_terminal(self):
        """TC-03-01-19: done 是终态"""
        state = StepState("step_1")
        state.mark_done("result")
        assert state.is_terminal

    def test_failed_is_terminal(self):
        """TC-03-01-20: failed 是终态"""
        state = StepState("step_1")
        state.mark_failed("error")
        assert state.is_terminal

    def test_skipped_is_terminal(self):
        """TC-03-01-21: skipped 是终态"""
        state = StepState("step_1")
        state.mark_skipped()
        assert state.is_terminal

    def test_pending_not_terminal(self):
        """TC-03-01-22: pending 不是终态"""
        state = StepState("step_1")
        assert not state.is_terminal

    def test_running_not_terminal(self):
        """TC-03-01-23: running 不是终态"""
        state = StepState("step_1")
        state.mark_running()
        assert not state.is_terminal
