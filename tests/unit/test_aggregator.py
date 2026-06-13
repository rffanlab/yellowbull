"""模块 04 - 结果汇总单元测试

覆盖: ExecutionDataCollector, ResultEvaluator, ReportGenerator, FeedbackCollector,
       RetryManager, ResultRepository, ResultAggregator
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.aggregator.feedback import FeedbackCollector
from yellowbull.aggregator.report_generator import ReportGenerator
from yellowbull.aggregator.retry import RetryManager
from yellowbull.aggregator.result_repo import ResultRepository
from yellowbull.models.result import (
    AggregationResult,
    EvaluationResult,
    ExecutionSummary,
    SideEffect,
    StepDetail,
    TerminationReason,
)
from yellowbull.models.step import Step, StepStatus
from yellowbull.models.task import Task


# ── Fixtures ───────────────────────────────────────────────

@pytest.fixture
def sample_task() -> Task:
    """创建示例任务"""
    return Task(
        id="task-001",
        goal="测试任务目标",
        confidence=0.9,
        steps=[
            Step(step_id="step-1", description="步骤一", tool_hint="shell"),
            Step(step_id="step-2", description="步骤二", tool_hint="file"),
            Step(step_id="step-3", description="步骤三", tool_hint="code"),
        ],
    )


@pytest.fixture
def sample_step_states(sample_task: Task) -> dict[str, StepState]:
    """创建示例步骤状态"""
    states = {}
    for step in sample_task.steps:
        state = StepState(step.step_id)
        if step.step_id == "step-1":
            state.status = StepStatus.DONE
            state.result = {"key": "value"}
        elif step.step_id == "step-2":
            state.status = StepStatus.FAILED
            state.error = "Connection timeout"
            state.retry_count = 2
        else:
            state.status = StepStatus.SKIPPED
        states[step.step_id] = state
    return states


@pytest.fixture
def sample_summary(sample_task: Task, sample_step_states: dict) -> ExecutionSummary:
    """创建示例执行汇总"""
    return ExecutionSummary(
        task_id=sample_task.id,
        goal=sample_task.goal,
        total_steps=3,
        done_steps=1,
        failed_steps=1,
        skipped_steps=1,
        step_details=[
            StepDetail(step_id="step-1", description="步骤一", status=StepStatus.DONE),
            StepDetail(step_id="step-2", description="步骤二", status=StepStatus.FAILED, error="Connection timeout"),
            StepDetail(step_id="step-3", description="步骤三", status=StepStatus.SKIPPED),
        ],
        termination_reason=TerminationReason.NORMAL,
        total_duration_seconds=45.5,
        steps_consumed=10,
    )


@pytest.fixture
def sample_evaluation() -> EvaluationResult:
    """创建示例评估结果"""
    return EvaluationResult(
        conclusion="partial_success",
        achievement_score=0.33,
        failure_analysis=None,
        side_effects=[],
        suggestions=["检查网络连接"],
        report_level=2,
    )


# ── ExecutionDataCollector Tests (T04-01) ─────────────────

class TestExecutionDataCollector:
    """测试数据收集器"""

    def test_collect_basic_summary(self, sample_task, sample_step_states):
        from yellowbull.aggregator.aggregator import ExecutionDataCollector

        collector = ExecutionDataCollector()
        summary = collector.collect(
            task=sample_task,
            step_states=sample_step_states,
            context_store=ContextStore(task_id="task-001"),
            steps_consumed=10,
            total_duration=45.5,
        )

        assert summary.task_id == sample_task.id
        assert summary.total_steps == 3
        assert summary.done_steps == 1
        assert summary.failed_steps == 1
        assert summary.skipped_steps == 1
        assert len(summary.step_details) == 3

    def test_collect_with_termination_reason(self, sample_task, sample_step_states):
        from yellowbull.aggregator.aggregator import ExecutionDataCollector

        collector = ExecutionDataCollector()
        summary = collector.collect(
            task=sample_task,
            step_states=sample_step_states,
            context_store=ContextStore(task_id="task-001"),
            steps_consumed=10,
            total_duration=45.5,
            termination_reason=TerminationReason.USER_CANCEL,
        )

        assert summary.termination_reason == TerminationReason.USER_CANCEL

    def test_record_interaction(self):
        from yellowbull.aggregator.aggregator import ExecutionDataCollector

        collector = ExecutionDataCollector()
        interaction = collector.record_interaction("confirmation", "确认继续")

        assert interaction.type == "confirmation"
        assert interaction.content == "确认继续"
        assert len(collector._user_interactions) == 1

    def test_record_side_effect(self):
        from yellowbull.aggregator.aggregator import ExecutionDataCollector

        collector = ExecutionDataCollector()
        se = SideEffect(type="FileWrite", description="创建了 config.yaml")
        collector.record_side_effect(se)

        assert len(collector._side_effects) == 1
        assert collector._side_effects[0].type == "FileWrite"

    def test_summarize_output(self):
        from yellowbull.aggregator.aggregator import ExecutionDataCollector

        # None → ""
        assert ExecutionDataCollector._summarize_output(None) == ""
        # Short string
        assert ExecutionDataCollector._summarize_output("hello") == "hello"
        # Long string truncated
        long_str = "x" * 300
        result = ExecutionDataCollector._summarize_output(long_str)
        assert len(result) <= 200
        # Dict
        d_result = ExecutionDataCollector._summarize_output({"a": 1, "b": 2})
        assert "dict" in d_result.lower()


# ── ResultEvaluator Tests (T04-02) ────────────────────────

class TestResultEvaluator:
    """测试结果评估器"""

    @pytest.mark.asyncio
    async def test_evaluate_success(self, sample_summary):
        from yellowbull.aggregator.aggregator import ResultEvaluator

        # 修改为全部完成
        sample_summary.done_steps = 3
        sample_summary.failed_steps = 0
        sample_summary.skipped_steps = 0
        for d in sample_summary.step_details:
            d.status = StepStatus.DONE

        evaluator = ResultEvaluator()
        result = await evaluator.evaluate(sample_summary)

        assert result.conclusion == "success"
        assert result.achievement_score >= 0.95

    @pytest.mark.asyncio
    async def test_evaluate_failure_with_critical(self, sample_summary):
        from yellowbull.aggregator.aggregator import ResultEvaluator

        # 标记关键步骤失败
        sample_summary.step_details[1].is_critical = True
        evaluator = ResultEvaluator()
        result = await evaluator.evaluate(sample_summary)

        assert result.conclusion == "failure"

    @pytest.mark.asyncio
    async def test_evaluate_partial_success(self, sample_summary):
        from yellowbull.aggregator.aggregator import ResultEvaluator

        # 部分完成，无失败
        sample_summary.done_steps = 2
        sample_summary.failed_steps = 0
        sample_summary.skipped_steps = 1
        for i, d in enumerate(sample_summary.step_details):
            d.status = StepStatus.DONE if i < 2 else StepStatus.SKIPPED

        evaluator = ResultEvaluator()
        result = await evaluator.evaluate(sample_summary)

        assert result.conclusion == "partial_success"

    @pytest.mark.asyncio
    async def test_evaluate_user_cancel(self, sample_summary):
        from yellowbull.aggregator.aggregator import ResultEvaluator

        sample_summary.termination_reason = TerminationReason.USER_CANCEL
        evaluator = ResultEvaluator()
        result = await evaluator.evaluate(sample_summary)

        assert result.conclusion == "cancelled"
        assert result.achievement_score == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_timeout(self, sample_summary):
        from yellowbull.aggregator.aggregator import ResultEvaluator

        sample_summary.termination_reason = TerminationReason.TIMEOUT
        evaluator = ResultEvaluator()
        result = await evaluator.evaluate(sample_summary)

        assert result.conclusion == "failure"
        assert result.achievement_score <= 0.3

    @pytest.mark.asyncio
    async def test_evaluate_budget_exhausted(self, sample_summary):
        from yellowbull.aggregator.aggregator import ResultEvaluator

        sample_summary.termination_reason = TerminationReason.BUDGET_EXHAUSTED
        evaluator = ResultEvaluator()
        result = await evaluator.evaluate(sample_summary)

        assert result.conclusion in ("partial_success", "failure")

    @pytest.mark.asyncio
    async def test_llm_analysis_degraded(self, sample_summary):
        """LLM 不可用时降级"""
        from yellowbull.aggregator.aggregator import ResultEvaluator

        # 无 LLM client → 降级
        evaluator = ResultEvaluator(llm_client=None)
        result = await evaluator.evaluate(sample_summary, report_level=3)

        assert result.conclusion in ("success", "partial_success", "failure", "cancelled")
        assert result.failure_analysis is None  # 无 LLM，无深度分析


# ── ReportGenerator Tests (T04-03) ────────────────────────

class TestReportGenerator:
    """测试报告生成器"""

    def test_concise_report(self, sample_summary, sample_evaluation):
        gen = ReportGenerator()
        report = gen.generate(sample_summary, sample_evaluation)

        assert "任务执行报告" in report
        assert sample_summary.task_id in report
        assert "部分完成" in report or "partial_success" in report.lower()

    def test_standard_report(self, sample_summary, sample_evaluation):
        gen = ReportGenerator()
        report = gen.generate(sample_summary, sample_evaluation)

        assert "执行指标" in report
        assert "步骤执行" in report
        assert str(sample_summary.total_steps) in report

    def test_detailed_report_includes_failures(self, sample_summary, sample_evaluation):
        sample_evaluation.report_level = 3
        gen = ReportGenerator()
        report = gen.generate(sample_summary, sample_evaluation)

        assert "失败步骤详情" in report

    def test_debug_report_has_extra_info(self, sample_summary, sample_evaluation):
        sample_evaluation.report_level = 4
        gen = ReportGenerator()
        report = gen.generate(sample_summary, sample_evaluation)

        assert "调试信息" in report

    def test_sanitize_api_key(self):
        """T04-04 脱敏测试"""
        text = 'api_key=sk-1234567890abcdef token: abc123'
        result = ReportGenerator._sanitize(text)
        assert "sk-1234567890abcdef" not in result
        assert "***" in result

    def test_sanitize_email(self):
        text = "联系 user@example.com 获取帮助"
        result = ReportGenerator._sanitize(text)
        assert "user@example.com" not in result
        assert "[email]" in result

    def test_sanitize_ip(self):
        text = "服务器地址 192.168.1.100 连接失败"
        result = ReportGenerator._sanitize(text)
        assert "192.168.1.100" not in result
        assert "[ip]" in result

    def test_sanitize_hash(self):
        text = "commit a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6 已提交"
        result = ReportGenerator._sanitize(text)
        assert "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6" not in result
        assert "[hash]" in result

    def test_format_duration_seconds(self):
        assert "秒" in ReportGenerator._format_duration(30.5)

    def test_format_duration_minutes(self):
        result = ReportGenerator._format_duration(125.0)
        assert "分" in result

    def test_format_duration_hours(self):
        result = ReportGenerator._format_duration(3700.0)
        assert "时" in result


# ── FeedbackCollector Tests (T04-05) ──────────────────────

class TestFeedbackCollector:
    """测试反馈收集器"""

    @pytest.mark.asyncio
    async def test_collect_feedback_returns_none(self):
        collector = FeedbackCollector()
        result = await collector.collect_feedback("task-001", "报告内容")
        assert result is None  # 默认实现返回 None

    def test_create_manual_feedback(self):
        feedback = FeedbackCollector.create_manual_feedback(
            task_id="task-001",
            satisfaction="satisfied",
            comment="很好用",
        )
        assert feedback.task_id == "task-001"
        assert feedback.satisfaction == "satisfied"

    def test_create_manual_feedback_invalid_satisfaction(self):
        with pytest.raises(ValueError, match="满意度必须是"):
            FeedbackCollector.create_manual_feedback(
                task_id="task-001",
                satisfaction="invalid_value",
            )


# ── RetryManager Tests (T04-06) ───────────────────────────

class TestRetryManager:
    """测试重试管理器"""

    def test_no_retry_for_success(self, sample_evaluation):
        sample_evaluation.conclusion = "success"
        manager = RetryManager()
        options = manager.generate_retry_options(sample_evaluation, 3, 3)
        assert len(options) == 0

    def test_full_retry_always_available(self, sample_evaluation):
        manager = RetryManager()
        options = manager.generate_retry_options(sample_evaluation, 3, 1)

        modes = [o.mode for o in options]
        assert "full" in modes

    def test_partial_retry_when_done_steps_exist(self, sample_evaluation):
        manager = RetryManager()
        options = manager.generate_retry_options(sample_evaluation, 3, 2)

        modes = [o.mode for o in options]
        assert "partial" in modes

    def test_fix_mode_with_analysis(self, sample_evaluation):
        sample_evaluation.failure_analysis = "网络超时导致失败"
        manager = RetryManager()
        options = manager.generate_retry_options(sample_evaluation, 3, 1)

        modes = [o.mode for o in options]
        assert "fix" in modes

    def test_recommend_fix_mode(self, sample_evaluation):
        sample_evaluation.failure_analysis = "网络超时"
        sample_evaluation.achievement_score = 0.6
        manager = RetryManager()
        mode = manager.recommend_mode(sample_evaluation, done_steps=2)
        assert mode == "fix"

    def test_recommend_partial_mode(self, sample_evaluation):
        sample_evaluation.failure_analysis = None
        sample_evaluation.achievement_score = 0.7
        manager = RetryManager()
        mode = manager.recommend_mode(sample_evaluation, done_steps=2)
        assert mode == "partial"


# ── ResultRepository Tests (T04-07) ───────────────────────

@pytest.fixture(scope="module")
def test_db_path():
    """共享的测试数据库路径"""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir) / "test.db"
    # 清理：手动删除文件（忽略 Windows 锁定错误）
    import shutil
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


class TestResultRepository:
    """测试结果持久化"""

    def test_save_and_load(self, sample_summary, sample_evaluation, test_db_path):
        repo = ResultRepository(test_db_path)

        result = AggregationResult(
            report="测试报告",
            evaluation=sample_evaluation,
        )
        repo.save(sample_summary, result)

        loaded = repo.get_task_result(sample_summary.task_id)
        assert loaded is not None
        assert loaded["task_id"] == sample_summary.task_id
        assert loaded["conclusion"] == sample_evaluation.conclusion

    def test_save_step_summaries(self, sample_summary, sample_evaluation, test_db_path):
        # 使用不同 task_id 避免冲突
        sample_summary.task_id = "task-steps"
        for d in sample_summary.step_details:
            d.step_id = d.step_id.replace("step-", "step-s-")

        repo = ResultRepository(test_db_path)
        result = AggregationResult(report="", evaluation=sample_evaluation)
        repo.save(sample_summary, result)

        steps = repo.get_step_summaries(sample_summary.task_id)
        assert len(steps) == 3
        assert "step-s-" in steps[0].step_id

    def test_upsert_updates_existing(self, sample_summary, sample_evaluation, test_db_path):
        # 使用不同 task_id 避免冲突
        sample_summary.task_id = "task-upsert"

        repo = ResultRepository(test_db_path)

        # 第一次保存
        result = AggregationResult(report="v1", evaluation=sample_evaluation)
        repo.save(sample_summary, result)

        # 更新评估结果
        sample_evaluation.conclusion = "success"
        sample_evaluation.achievement_score = 1.0
        result.evaluation = sample_evaluation
        result.report = "v2"
        repo.save(sample_summary, result)

        loaded = repo.get_task_result(sample_summary.task_id)
        assert loaded["conclusion"] == "success"

    def test_list_recent_tasks(self, sample_summary, sample_evaluation, test_db_path):
        # 使用不同 task_id 避免冲突
        sample_summary.task_id = "task-recent"

        repo = ResultRepository(test_db_path)
        result = AggregationResult(report="", evaluation=sample_evaluation)
        repo.save(sample_summary, result)

        tasks = repo.list_recent_tasks()
        assert len(tasks) >= 1
        task_ids = [t["task_id"] for t in tasks]
        assert "task-recent" in task_ids


# ── ResultAggregator Integration Tests (T04-09/10/11) ────

class TestResultAggregator:
    """测试汇总入口"""

    @pytest.mark.asyncio
    async def test_aggregate_full_flow(self, sample_task, sample_step_states):
        from yellowbull.aggregator.aggregator import ResultAggregator

        aggregator = ResultAggregator()
        result = await aggregator.aggregate(
            task=sample_task,
            step_states=sample_step_states,
            context_store=ContextStore(task_id="task-001"),
            steps_consumed=10,
            total_duration=45.5,
        )

        assert result.evaluation is not None
        assert result.evaluation.conclusion in ("success", "partial_success", "failure")

    @pytest.mark.asyncio
    async def test_aggregate_with_llm(self, sample_task, sample_step_states):
        from yellowbull.aggregator.aggregator import ResultAggregator

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="LLM 分析结果")

        aggregator = ResultAggregator(llm_client=mock_llm)
        result = await aggregator.aggregate(
            task=sample_task,
            step_states=sample_step_states,
            context_store=ContextStore(task_id="task-001"),
            steps_consumed=10,
            total_duration=45.5,
            report_level=3,
        )

        assert result.evaluation is not None

    def test_consistency_check_missing_state(self, sample_task):
        from yellowbull.aggregator.aggregator import ResultAggregator

        # 只有部分步骤有状态
        states = {
            "step-1": StepState("step-1"),
        }

        aggregator = ResultAggregator()
        report = aggregator._check_consistency(sample_task, states)

        assert not report.is_consistent
        assert any("缺少执行状态" in w for w in report.warnings)
        # 自动修复后，缺失的步骤被添加
        assert "step-2" in states
        assert "step-3" in states

    def test_handle_user_cancel(self, sample_summary):
        from yellowbull.aggregator.aggregator import ResultAggregator

        sample_summary.termination_reason = TerminationReason.USER_CANCEL
        aggregator = ResultAggregator()
        result = aggregator._handle_abnormal_termination(sample_summary)

        assert result.termination_reason == TerminationReason.USER_CANCEL


# ── Model Tests ────────────────────────────────────────────

class TestModels:
    """测试新增数据模型"""

    def test_termination_reason_enum(self):
        assert TerminationReason.NORMAL == "normal"
        assert TerminationReason.USER_CANCEL == "user_cancel"
        assert TerminationReason.TIMEOUT == "timeout"
        assert TerminationReason.BUDGET_EXHAUSTED == "budget_exhausted"

    def test_side_effect_model(self):
        se = SideEffect(type="FileWrite", description="创建文件", reversible=True)
        assert se.type == "FileWrite"
        assert se.reversible is True

    def test_step_detail_model(self):
        detail = StepDetail(
            step_id="s1",
            status=StepStatus.DONE,
            output_summary="OK",
            is_critical=True,
        )
        assert detail.is_critical is True

    def test_execution_summary_model(self):
        summary = ExecutionSummary(task_id="t1", goal="测试")
        assert summary.task_id == "t1"
        assert summary.total_steps == 0
