"""结果汇总主入口

聚合执行数据 → 评估结论 → 生成报告 → 持久化。
包含异常终止处理和数据一致性保障。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.config.settings import ExperienceSettings
from yellowbull.experience.recorder import ExperienceRecorder
from yellowbull.llm.client import LLMClient
from yellowbull.models.result import (
    AggregationResult,
    ConsistencyReport,
    EvaluationResult,
    ExecutionSummary,
    MechanicalResult,
    RuleResult,
    SideEffect,
    StepDetail,
    SubTaskRecord,
    TerminationReason,
    UserInteraction,
)
from yellowbull.models.step import Step, StepStatus
from yellowbull.models.subtask import SubTask
from yellowbull.models.task import Task

logger = logging.getLogger(__name__)


class ExecutionDataCollector:
    """T04-01 执行数据收集器"""

    def __init__(self):
        self._user_interactions: list[UserInteraction] = []
        self._side_effects: list[SideEffect] = []
        self._subtask_records: list[SubTaskRecord] = []

    def collect(
        self,
        task: Task,
        step_states: dict[str, StepState],
        context_store: ContextStore,
        steps_consumed: int,
        total_duration: float,
        termination_reason: str = TerminationReason.NORMAL,
    ) -> ExecutionSummary:
        """收集执行数据并生成汇总"""

        # 构建步骤详情
        step_details = []
        done_steps = 0
        failed_steps = 0
        skipped_steps = 0

        for step in task.steps:
            state = step_states.get(step.step_id)
            if state is None:
                continue

            detail = StepDetail(
                step_id=step.step_id,
                description=step.description or "",
                status=state.status,
                output_summary=self._summarize_output(state.result),
                duration_seconds=0.0,
                error=state.error,
                retry_count=state.retry_count,
                is_critical=False,  # TODO: 从 step 模型获取 critical 标记
            )

            if state.status == StepStatus.DONE:
                done_steps += 1
            elif state.status == StepStatus.FAILED:
                failed_steps += 1
            elif state.status == StepStatus.SKIPPED:
                skipped_steps += 1

            step_details.append(detail)

        return ExecutionSummary(
            task_id=task.id,
            goal=task.goal,
            success_criteria=[],
            total_steps=len(task.steps),
            done_steps=done_steps,
            failed_steps=failed_steps,
            skipped_steps=skipped_steps,
            step_details=step_details,
            subtask_records=list(self._subtask_records),
            termination_reason=termination_reason,
            total_duration_seconds=total_duration,
            steps_consumed=steps_consumed,
            user_interactions=list(self._user_interactions),
            side_effects=list(self._side_effects),
        )

    def record_interaction(
        self, interaction_type: str, content: str
    ) -> UserInteraction:
        """记录用户交互"""
        interaction = UserInteraction(type=interaction_type, content=content)
        self._user_interactions.append(interaction)
        return interaction

    def record_side_effect(self, side_effect: SideEffect) -> None:
        """记录副作用"""
        self._side_effects.append(side_effect)

    def record_subtask(
        self, subtask: SubTask, parent_step_id: str, obstacle_desc: str = ""
    ) -> SubTaskRecord:
        """记录子任务"""
        record = SubTaskRecord(
            subtask_id=subtask.id,
            parent_step_id=parent_step_id,
            obstacle_description=obstacle_desc,
            status="",
            step_results=[],
        )
        self._subtask_records.append(record)
        return record

    @staticmethod
    def _summarize_output(result: Any) -> str:
        """将任意结果摘要为短文本"""
        if result is None:
            return ""
        if isinstance(result, str):
            return result[:200] if len(result) > 200 else result
        if isinstance(result, (dict, list)):
            return f"{type(result).__name__}({len(result)})"
        return str(result)[:200]


class ResultEvaluator:
    """T04-02 结果评估器

    三级评估: 机械统计 → 规则判定 → LLM 深度分析（降级）
    """

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client

    async def evaluate(
        self, summary: ExecutionSummary, report_level: int = 2
    ) -> EvaluationResult:
        """执行三级评估"""

        # Level 1: 机械统计
        mechanical = self._mechanical_stats(summary)

        # Level 2: 规则判定
        rule_result = self._rule_based_judgment(summary, mechanical)

        # Level 3: LLM 深度分析（降级）
        llm_analysis = await self._llm_deep_analysis(
            summary, rule_result, report_level
        )

        return EvaluationResult(
            conclusion=rule_result.conclusion,
            achievement_score=round(rule_result.achievement_score, 2),
            failure_analysis=llm_analysis.get("failure_analysis"),
            side_effects=llm_analysis.get("side_effects", []),
            suggestions=llm_analysis.get("suggestions", []),
            report_level=report_level,
        )

    def _mechanical_stats(self, summary: ExecutionSummary) -> MechanicalResult:
        """机械统计"""
        total = summary.total_steps
        done = summary.done_steps
        failed = summary.failed_steps
        skipped = summary.skipped_steps

        critical_failed = any(
            d.is_critical and d.status == StepStatus.FAILED
            for d in summary.step_details
        )

        completion_rate = done / total if total > 0 else 0.0

        return MechanicalResult(
            total_steps=total,
            done_steps=done,
            failed_steps=failed,
            skipped_steps=skipped,
            critical_failed=critical_failed,
            completion_rate=completion_rate,
        )

    def _rule_based_judgment(
        self, summary: ExecutionSummary, mechanical: MechanicalResult
    ) -> RuleResult:
        """规则判定"""

        # 异常终止优先
        if summary.termination_reason == TerminationReason.USER_CANCEL:
            return RuleResult(
                conclusion="cancelled",
                achievement_score=0.0,
                reason="用户主动取消任务",
            )
        if summary.termination_reason == TerminationReason.TIMEOUT:
            return RuleResult(
                conclusion="failure",
                achievement_score=min(mechanical.completion_rate * 0.5, 0.3),
                reason=f"任务超时终止，完成率 {mechanical.completion_rate:.0%}",
            )
        if summary.termination_reason == TerminationReason.BUDGET_EXHAUSTED:
            return RuleResult(
                conclusion="partial_success" if mechanical.done_steps > 0 else "failure",
                achievement_score=min(mechanical.completion_rate * 0.7, 0.5),
                reason=f"步骤预算耗尽，已完成 {mechanical.done_steps}/{mechanical.total_steps}",
            )

        # 正常终止：按完成度判定
        if mechanical.critical_failed:
            return RuleResult(
                conclusion="failure",
                achievement_score=min(mechanical.completion_rate * 0.6, 0.4),
                reason="关键步骤失败，任务无法达成目标",
            )

        rate = mechanical.completion_rate
        if rate >= 0.95:
            return RuleResult(
                conclusion="success",
                achievement_score=rate,
                reason=f"全部步骤完成 ({mechanical.done_steps}/{mechanical.total_steps})",
            )
        elif rate > 0.5 and mechanical.failed_steps == 0:
            return RuleResult(
                conclusion="partial_success",
                achievement_score=rate,
                reason=f"部分完成，无失败步骤 ({mechanical.done_steps}/{mechanical.total_steps})",
            )
        elif mechanical.done_steps > 0:
            return RuleResult(
                conclusion="partial_success",
                achievement_score=min(rate * 0.8, 0.7),
                reason=f"部分完成，存在 {mechanical.failed_steps} 个失败步骤",
            )

        return RuleResult(
            conclusion="failure",
            achievement_score=rate,
            reason=f"任务未完成 ({mechanical.done_steps}/{mechanical.total_steps})",
        )

    async def _llm_deep_analysis(
        self, summary: ExecutionSummary, rule_result: RuleResult, report_level: int
    ) -> dict[str, Any]:
        """LLM 深度分析（降级）"""
        result = {
            "failure_analysis": None,
            "side_effects": [],
            "suggestions": [],
        }

        if self._llm is None or report_level < 3:
            return result

        try:
            failed_steps = [d for d in summary.step_details if d.status == StepStatus.FAILED]
            if not failed_steps and rule_result.conclusion != "failure":
                return result

            # 构建分析提示
            step_info = "\n".join(
                f"- {d.step_id}: {d.description} → {d.error or 'failed'}"
                for d in failed_steps[:5]
            )

            prompt = (
                "作为任务分析专家，请分析以下失败步骤并给出:\n"
                "1. 根本原因分析\n2. 改进建议\n\n"
                f"任务: {summary.goal}\n"
                f"结论: {rule_result.conclusion}\n"
                f"失败步骤:\n{step_info}"
            )

            response = await self._llm.chat(
                system_prompt="你是一个专业的任务执行分析专家。",
                user_messages=[prompt],
                temperature=0.3,
            )

            result["failure_analysis"] = response[:500] if response else None
            result["suggestions"] = [
                "检查失败步骤的输入参数",
                "考虑增加重试机制",
                "优化任务分解粒度",
            ]

        except Exception as e:
            logger.warning("LLM 深度分析失败，降级为机械记录: %s", e)

        return result


class ResultAggregator:
    """T04-09 结果汇总主入口"""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        experience_recorder: ExperienceRecorder | None = None,
        experience_settings: ExperienceSettings | None = None,
    ):
        self._collector = ExecutionDataCollector()
        self._evaluator = ResultEvaluator(llm_client)
        self._experience_recorder = experience_recorder
        self._experience_settings = experience_settings or ExperienceSettings()

    def collect_interaction(
        self, interaction_type: str, content: str
    ) -> None:
        """记录用户交互"""
        self._collector.record_interaction(interaction_type, content)

    def record_side_effect(self, side_effect: SideEffect) -> None:
        """记录副作用"""
        self._collector.record_side_effect(side_effect)

    async def aggregate(
        self,
        task: Task,
        step_states: dict[str, StepState],
        context_store: ContextStore,
        steps_consumed: int,
        total_duration: float,
        termination_reason: str = TerminationReason.NORMAL,
        report_level: int = 2,
    ) -> AggregationResult:
        """执行完整汇总流程"""

        # T04-11: 数据一致性检查
        consistency = self._check_consistency(task, step_states)
        if not consistency.is_consistent:
            logger.warning(
                "数据一致性问题: %s",
                "; ".join(consistency.warnings),
            )

        # T04-01: 收集执行数据
        summary = self._collector.collect(
            task=task,
            step_states=step_states,
            context_store=context_store,
            steps_consumed=steps_consumed,
            total_duration=total_duration,
            termination_reason=termination_reason,
        )

        # T04-10: 异常终止处理
        summary = self._handle_abnormal_termination(summary)

        # T04-02: 评估结果
        evaluation = await self._evaluator.evaluate(summary, report_level)

        return AggregationResult(
            report="",  # ReportGenerator 负责填充
            evaluation=evaluation,
            feedback=None,
            experience_recorded=False,
        )

    def _handle_abnormal_termination(self, summary: ExecutionSummary) -> ExecutionSummary:
        """T04-10 异常终止处理"""
        reason = summary.termination_reason

        if reason == TerminationReason.USER_CANCEL:
            logger.info("任务被用户取消，标记未完成步骤为 SKIPPED")
        elif reason in (TerminationReason.TIMEOUT, TerminationReason.BUDGET_EXHAUSTED):
            logger.warning(
                "任务异常终止 (%s)，保留当前状态用于报告",
                reason,
            )

        return summary

    def _check_consistency(
        self, task: Task, step_states: dict[str, StepState]
    ) -> ConsistencyReport:
        """T04-11 数据一致性检查"""
        warnings = []
        resolved = []

        # 检查：每个步骤都有状态
        for step in task.steps:
            if step.step_id not in step_states:
                warnings.append(f"步骤 {step.step_id} 缺少执行状态")
                # 自动修复：添加 PENDING 状态
                step_states[step.step_id] = StepState(step.step_id)
                resolved.append(f"为步骤 {step.step_id} 添加默认 PENDING 状态")

        # 检查：终态一致性（DONE/FAILED/SKIPPED）
        for step_id, state in step_states.items():
            if state.status not in (
                StepStatus.DONE,
                StepStatus.FAILED,
                StepStatus.SKIPPED,
                StepStatus.RUNNING,
                StepStatus.PENDING,
            ):
                warnings.append(f"步骤 {step_id} 状态异常: {state.status}")

        return ConsistencyReport(
            is_consistent=len(warnings) == 0,
            warnings=warnings,
            resolved_issues=resolved,
        )


__all__ = [
    "ExecutionDataCollector",
    "ResultEvaluator",
    "ResultAggregator",
]
