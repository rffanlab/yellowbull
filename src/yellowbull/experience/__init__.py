"""经验系统

对外服务接口。
MVP 阶段: 检索返回空列表，记录操作静默跳过。
后续版本: 接入完整的经验库。
"""

from __future__ import annotations

import logging

from yellowbull.config.settings import ExperienceSettings
from yellowbull.models.experience import Experience
from yellowbull.models.result import TaskResult
from yellowbull.models.task import Task

logger = logging.getLogger(__name__)


class ExperienceService:
    """经验系统对外服务接口

    MVP 阶段:
    - retrieve_experiences: 始终返回空列表
    - record_experience: 静默跳过

    后续版本: 接入完整的经验库。
    """

    def __init__(self, settings: ExperienceSettings):
        self._settings = settings
        self.enabled = settings.enabled

    async def retrieve_experiences(self, task: Task) -> list[Experience]:
        """检索相关经验

        MVP: 始终返回空列表。
        禁用时: 直接返回空列表。

        Args:
            task: 任务对象

        Returns:
            经验列表（MVP 阶段为空）
        """
        if not self.enabled:
            return []

        # MVP 阶段: 返回空列表
        # TODO: 后续接入 ExperienceRetriever
        logger.debug("经验检索 (MVP): 返回空列表")
        return []

    async def record_experience(
        self,
        task: Task,
        task_result: TaskResult,
        project_name: str | None = None,
    ) -> None:
        """记录任务经验

        MVP: 静默跳过。
        禁用时: 直接返回。

        Args:
            task: 任务对象
            task_result: 任务结果
            project_name: 项目名称
        """
        if not self.enabled:
            return

        # MVP 阶段: 静默跳过
        # TODO: 后续接入 ExperienceRecorder
        logger.debug("经验记录 (MVP): 静默跳过")
        pass
