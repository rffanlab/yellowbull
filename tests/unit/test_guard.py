"""T03: 全局保护单元测试"""

import pytest
import time

from yellowbull.agent.guard import BudgetGuard, GuardResult


class TestGuardResult:
    """TC-03-10-01 ~ TC-03-10-03"""

    def test_ok_result(self):
        """TC-03-10-01: 通过检查"""
        result = GuardResult(ok=True)
        assert result.ok is True
        assert result.reason is None

    def test_failed_result(self):
        """TC-03-10-02: 未通过检查"""
        result = GuardResult(ok=False, reason="budget exceeded")
        assert result.ok is False
        assert result.reason == "budget exceeded"

    def test_reason_default_none(self):
        """TC-03-10-03: 默认 reason 为 None"""
        result = GuardResult(ok=True)
        assert result.reason is None


class TestBudgetGuardBasic:
    """TC-03-10-04 ~ TC-03-10-07"""

    def test_initial_check_passes(self):
        """TC-03-10-04: 初始检查通过"""
        guard = BudgetGuard(max_total_steps=10, total_timeout=60)
        result = guard.check()
        assert result.ok is True

    def test_consume_step(self):
        """TC-03-10-05: 消耗步骤"""
        guard = BudgetGuard(max_total_steps=10)
        assert guard.remaining_budget == 10
        guard.consume_step()
        assert guard.remaining_budget == 9

    def test_remaining_budget(self):
        """TC-03-10-06: 剩余预算"""
        guard = BudgetGuard(max_total_steps=5)
        for _ in range(3):
            guard.consume_step()
        assert guard.remaining_budget == 2

    def test_remaining_budget_zero(self):
        """TC-03-10-07: 预算耗尽"""
        guard = BudgetGuard(max_total_steps=2)
        guard.consume_step()
        guard.consume_step()
        assert guard.remaining_budget == 0


class TestBudgetGuardBudgetExceeded:
    """TC-03-10-08 ~ TC-03-10-10"""

    def test_budget_exceeded_fails(self):
        """TC-03-10-08: 预算耗尽检查失败"""
        guard = BudgetGuard(max_total_steps=3)
        for _ in range(3):
            guard.consume_step()
        result = guard.check()
        assert result.ok is False

    def test_budget_exceeded_reason(self):
        """TC-03-10-09: 预算耗尽原因"""
        guard = BudgetGuard(max_total_steps=2)
        guard.consume_step()
        guard.consume_step()
        result = guard.check()
        assert "预算" in result.reason or "budget" in result.reason.lower()

    def test_budget_not_exceeded_passes(self):
        """TC-03-10-10: 预算未耗尽通过"""
        guard = BudgetGuard(max_total_steps=5)
        for _ in range(3):
            guard.consume_step()
        result = guard.check()
        assert result.ok is True


class TestBudgetGuardTimeout:
    """TC-03-10-11 ~ TC-03-10-14"""

    def test_timeout_fails(self):
        """TC-03-10-11: 超时检查失败"""
        guard = BudgetGuard(max_total_steps=100, total_timeout=0)
        guard.start()
        time.sleep(0.01)
        result = guard.check()
        assert result.ok is False

    def test_timeout_reason(self):
        """TC-03-10-12: 超时原因"""
        guard = BudgetGuard(max_total_steps=100, total_timeout=0)
        guard.start()
        time.sleep(0.01)
        result = guard.check()
        assert "超时" in result.reason or "timeout" in result.reason.lower()

    def test_no_timeout_passes(self):
        """TC-03-10-13: 未超时通过"""
        guard = BudgetGuard(max_total_steps=100, total_timeout=3600)
        guard.start()
        result = guard.check()
        assert result.ok is True

    def test_elapsed_seconds(self):
        """TC-03-10-14: 已用时间"""
        guard = BudgetGuard()
        guard.start()
        time.sleep(0.01)
        assert guard.elapsed_seconds > 0


class TestBudgetGuardCancel:
    """TC-03-10-15 ~ TC-03-10-17"""

    def test_cancel_fails(self):
        """TC-03-10-15: 取消后检查失败"""
        guard = BudgetGuard()
        guard.cancel()
        result = guard.check()
        assert result.ok is False

    def test_cancel_reason(self):
        """TC-03-10-16: 取消原因"""
        guard = BudgetGuard()
        guard.cancel()
        result = guard.check()
        assert "取消" in result.reason or "cancel" in result.reason.lower()

    def test_cancel_then_check(self):
        """TC-03-10-17: 取消后持续失败"""
        guard = BudgetGuard()
        guard.cancel()
        result1 = guard.check()
        result2 = guard.check()
        assert result1.ok is False
        assert result2.ok is False


class TestBudgetGuardCombined:
    """TC-03-10-18 ~ TC-03-10-20"""

    def test_budget_and_timeout(self):
        """TC-03-10-18: 预算和超时同时检查"""
        guard = BudgetGuard(max_total_steps=2, total_timeout=3600)
        guard.start()
        guard.consume_step()
        guard.consume_step()
        result = guard.check()
        assert result.ok is False

    def test_budget_and_cancel(self):
        """TC-03-10-19: 预算和取消同时检查"""
        guard = BudgetGuard(max_total_steps=10)
        guard.cancel()
        result = guard.check()
        assert result.ok is False

    def test_all_checks_pass(self):
        """TC-03-10-20: 所有检查通过"""
        guard = BudgetGuard(max_total_steps=10, total_timeout=3600)
        guard.start()
        guard.consume_step()
        result = guard.check()
        assert result.ok is True


class TestBudgetGuardBoundary:
    """T03-16: 预算控制边界场景"""

    def test_zero_budget(self):
        """TC-03-16-01: 零预算"""
        guard = BudgetGuard(max_total_steps=0)
        result = guard.check()
        assert result.ok is False

    def test_single_step_budget(self):
        """TC-03-16-02: 单步预算"""
        guard = BudgetGuard(max_total_steps=1)
        assert guard.check().ok is True
        guard.consume_step()
        assert guard.check().ok is False

    def test_exhaust_then_cancel(self):
        """TC-03-16-03: 耗尽后取消"""
        guard = BudgetGuard(max_total_steps=1)
        guard.consume_step()
        guard.cancel()
        result = guard.check()
        assert result.ok is False

    def test_timeout_without_start(self):
        """TC-03-16-04: 未启动计时"""
        guard = BudgetGuard(max_total_steps=100, total_timeout=0)
        result = guard.check()
        assert result.ok is True

    def test_negative_timeout(self):
        """TC-03-16-05: 负超时"""
        guard = BudgetGuard(max_total_steps=100, total_timeout=-1)
        guard.start()
        result = guard.check()
        assert result.ok is False

    def test_large_budget(self):
        """TC-03-16-06: 大预算"""
        guard = BudgetGuard(max_total_steps=1000000)
        result = guard.check()
        assert result.ok is True
        assert guard.remaining_budget == 1000000
