"""报告格式化模块

根据 report_level 生成不同详细程度的任务执行报告。
包含结果脱敏功能。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from yellowbull.models.result import (
    AggregationResult,
    EvaluationResult,
    ExecutionSummary,
)
from yellowbull.models.step import StepStatus

logger = logging.getLogger(__name__)


class ReportGenerator:
    """T04-03 报告生成器"""

    def __init__(self):
        pass

    def generate(self, summary: ExecutionSummary, evaluation: EvaluationResult | None) -> str:
        """根据 report_level 生成报告"""
        level = 2
        if evaluation:
            level = evaluation.report_level

        if level == 1:
            return self._concise_report(summary, evaluation)
        elif level == 2:
            return self._standard_report(summary, evaluation)
        elif level == 3:
            return self._detailed_report(summary, evaluation)
        else:
            return self._debug_report(summary, evaluation)

    def _concise_report(self, summary: ExecutionSummary, evaluation: EvaluationResult | None) -> str:
        """简洁报告：结论 + 关键指标"""
        conclusion = "未知"
        score = 0.0
        if evaluation:
            conclusion_map = {
                "success": "成功",
                "partial_success": "部分完成",
                "failure": "失败",
                "cancelled": "已取消",
            }
            conclusion = conclusion_map.get(evaluation.conclusion, str(evaluation.conclusion))
            score = evaluation.achievement_score

        lines = [
            "=" * 50,
            f"任务执行报告 - {summary.task_id}",
            "=" * 50,
            f"结论: {conclusion} ({score:.0%})",
            f"步骤: {summary.done_steps}/{summary.total_steps} 完成",
            f"耗时: {self._format_duration(summary.total_duration_seconds)}",
        ]

        if evaluation and evaluation.suggestions:
            lines.append("\n建议:")
            for s in evaluation.suggestions[:3]:
                lines.append(f"  - {s}")

        lines.append("=" * 50)
        return "\n".join(lines)

    def _standard_report(self, summary: ExecutionSummary, evaluation: EvaluationResult | None) -> str:
        """标准报告：结论 + 指标 + 步骤摘要"""
        conclusion = "未知"
        score = 0.0
        reason = ""
        if evaluation:
            conclusion_map = {
                "success": "成功",
                "partial_success": "部分完成",
                "failure": "失败",
                "cancelled": "已取消",
            }
            conclusion = conclusion_map.get(evaluation.conclusion, str(evaluation.conclusion))
            score = evaluation.achievement_score

        lines = [
            "=" * 60,
            f"任务执行报告 - {summary.task_id}",
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 60,
            "",
            f"目标: {summary.goal}",
            f"结论: {conclusion} ({score:.0%})",
            "",
            "--- 执行指标 ---",
            f"总步骤: {summary.total_steps}",
            f"已完成: {summary.done_steps}",
            f"失败: {summary.failed_steps}",
            f"跳过: {summary.skipped_steps}",
            f"耗时: {self._format_duration(summary.total_duration_seconds)}",
        ]

        if summary.termination_reason and summary.termination_reason != "normal":
            lines.append(f"终止原因: {summary.termination_reason}")

        # 步骤摘要（脱敏）
        lines.append("")
        lines.append("--- 步骤执行 ---")
        for detail in summary.step_details[:10]:
            status_icon = self._status_icon(detail.status)
            output = self._sanitize(detail.output_summary)
            lines.append(f"  {status_icon} [{detail.step_id}] {detail.description}")
            if output:
                lines.append(f"     → {output[:80]}")

        if len(summary.step_details) > 10:
            lines.append(f"  ... 还有 {len(summary.step_details) - 10} 个步骤")

        # 副作用
        if summary.side_effects:
            lines.append("")
            lines.append("--- 副作用 ---")
            for se in summary.side_effects:
                lines.append(f"  ⚠ {se.type}: {se.description}")

        # 建议
        if evaluation and evaluation.suggestions:
            lines.append("")
            lines.append("--- 改进建议 ---")
            for s in evaluation.suggestions[:5]:
                lines.append(f"  - {s}")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)

    def _detailed_report(self, summary: ExecutionSummary, evaluation: EvaluationResult | None) -> str:
        """详细报告：标准 + 失败分析 + 子任务详情"""
        report = self._standard_report(summary, evaluation)

        extras = []

        # 失败步骤详情
        failed = [d for d in summary.step_details if d.status == StepStatus.FAILED]
        if failed:
            extras.append("--- 失败步骤详情 ---")
            for d in failed:
                error_info = self._sanitize(d.error or "未知错误")
                extras.append(f"  [{d.step_id}] {d.description}")
                extras.append(f"    错误: {error_info[:120]}")
                extras.append(f"    重试: {d.retry_count} 次")

        # LLM 分析
        if evaluation and evaluation.failure_analysis:
            extras.append("")
            extras.append("--- 失败原因分析 ---")
            extras.append(evaluation.failure_analysis)

        # 子任务详情
        if summary.subtask_records:
            extras.append("")
            extras.append("--- 子任务记录 ---")
            for record in summary.subtask_records:
                extras.append(f"  [{record.subtask_id}] 触发于 {record.parent_step_id}")
                extras.append(f"    障碍: {record.obstacle_description[:100]}")

        if extras:
            report += "\n\n" + "\n".join(extras)

        return report

    def _debug_report(self, summary: ExecutionSummary, evaluation: EvaluationResult | None) -> str:
        """调试报告：详细 + 原始数据"""
        report = self._detailed_report(summary, evaluation)

        extras = [
            "",
            "--- 调试信息 ---",
            f"步骤预算消耗: {summary.steps_consumed}",
            f"用户交互次数: {len(summary.user_interactions)}",
        ]

        if summary.user_interactions:
            extras.append("用户交互:")
            for ui in summary.user_interactions:
                content = self._sanitize(ui.content)
                extras.append(f"  [{ui.type}] {content[:100]}")

        report += "\n".join(extras)
        return report

    @staticmethod
    def _status_icon(status: str) -> str:
        """状态图标"""
        icons = {
            StepStatus.DONE: "✓",
            StepStatus.FAILED: "✗",
            StepStatus.SKIPPED: "⊘",
            StepStatus.RUNNING: "⟳",
            StepStatus.PENDING: "○",
        }
        return icons.get(status, "?")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """格式化耗时"""
        if seconds < 60:
            return f"{seconds:.1f}秒"
        minutes = int(seconds // 60)
        secs = seconds % 60
        if minutes < 60:
            return f"{minutes}分{secs:.0f}秒"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}时{mins}分{secs:.0f}秒"

    @staticmethod
    def _sanitize(text: str) -> str:
        """T04-04 结果脱敏"""
        if not text:
            return ""

        # API Key / Token 模式
        text = re.sub(
            r'(api[_-]?key|token|secret|password)[=:]\s*\S+',
            r'\1=***',
            text,
            flags=re.IGNORECASE,
        )
        # Bearer token
        text = re.sub(r'Bearer\s+\S+', 'Bearer ***', text)
        # 邮箱
        text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[email]', text)
        # IP 地址 (内网)
        text = re.sub(
            r'\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b',
            '[ip]',
            text,
        )
        # 长十六进制串 (hash/key)
        text = re.sub(r'\b[0-9a-fA-F]{32,}\b', '[hash]', text)

        return text


__all__ = ["ReportGenerator"]
