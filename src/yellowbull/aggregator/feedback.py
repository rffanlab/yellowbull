"""用户反馈收集模块

在任务完成后收集用户满意度反馈。
"""

from __future__ import annotations

import logging

from yellowbull.models.result import UserFeedback

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """T04-05 反馈收集器"""

    SATISFACTION_OPTIONS = ("satisfied", "neutral", "dissatisfied")

    def __init__(self):
        pass

    async def collect_feedback(
        self, task_id: str, report: str
    ) -> UserFeedback | None:
        """收集用户反馈"""
        try:
            # 在实际系统中，这里会通过 CLI / Web UI 获取用户输入
            # 当前实现返回 None，表示未收集到反馈
            return await self._prompt_feedback(task_id, report)
        except Exception as e:
            logger.warning("收集用户反馈失败: %s", e)
            return None

    async def _prompt_feedback(self, task_id: str, report: str) -> UserFeedback | None:
        """提示用户输入反馈"""
        # TODO: 集成到 CLI / Web UI
        # 当前返回 None，表示跳过反馈收集
        return None

    @staticmethod
    def create_manual_feedback(
        task_id: str, satisfaction: str, comment: str | None = None
    ) -> UserFeedback:
        """手动创建反馈记录"""
        if satisfaction not in FeedbackCollector.SATISFACTION_OPTIONS:
            raise ValueError(f"满意度必须是 {FeedbackCollector.SATISFACTION_OPTIONS} 之一")

        return UserFeedback(
            task_id=task_id,
            satisfaction=satisfaction,
            comment=comment,
        )


__all__ = ["FeedbackCollector"]
