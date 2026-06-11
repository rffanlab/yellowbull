"""经验记录器

任务结束后记录经验：收集数据 → 计算评分 → LLM 总结 → 持久化存储。
LLM 失败时降级为机械记录。
"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from pydantic import BaseModel, Field

from yellowbull.config.settings import ExperienceSettings
from yellowbull.experience.repo import ExperienceRepo
from yellowbull.llm.client import LLMClient
from yellowbull.models.experience import Experience
from yellowbull.models.result import StepResult, TaskConclusion, TaskResult
from yellowbull.models.task import Task
from yellowbull.prompts.experience import (
    EXPERIENCE_SUMMARY_SYSTEM_PROMPT,
    EXPERIENCE_SUMMARY_USER_PROMPT_TEMPLATE,
)

logger = logging.getLogger(__name__)


class _SummaryResponse(BaseModel):
    """经验总结 LLM 响应模型"""

    task_summary: str = Field(default="", description="任务摘要")
    task_category: str = Field(default="unknown", description="任务类别")
    lessons_learned: str = Field(default="", description="经验教训")
    keywords: list[str] = Field(default_factory=list, description="关键词")
    tags: list[str] = Field(default_factory=list, description="标签")
    is_permanent: bool = Field(default=False, description="是否永久")
    generality: float = Field(default=0.5, description="通用性评分")


class ExperienceRecorder:
    """经验记录器"""

    def __init__(
        self,
        repo: ExperienceRepo,
        llm_client: LLMClient | None,
        settings: ExperienceSettings,
    ):
        self._repo = repo
        self._llm = llm_client
        self._settings = settings

    async def record(
        self,
        task: Task,
        task_result: TaskResult,
        project_name: str | None = None,
    ) -> Experience | None:
        """任务结束后记录经验

        流程:
        1. 收集执行数据
        2. 计算评分
        3. LLM 总结（生成摘要、教训、关键词、标签）
        4. 判断经验级别
        5. 持久化存储

        Args:
            task: 原始任务
            task_result: 任务执行结果
            project_name: 关联项目名称（None=通用经验）

        Returns:
            创建的经验对象，失败时返回 None
        """
        try:
            # 1. 计算评分
            score = self._calculate_score(task_result)

            # 2. 收集执行数据
            outcome = self._map_outcome(task_result.conclusion)
            steps_count = len(task_result.step_results)
            success_steps = sum(
                1 for r in task_result.step_results
                if r.status.value in ("done",)
            )
            success_rate = success_steps / steps_count if steps_count > 0 else 0.0
            retry_count = sum(r.retry_count for r in task_result.step_results)
            tool_chain = self._extract_tool_chain(task_result.step_results)

            # 3. LLM 总结（失败时降级）
            summary = await self._summarize_with_llm(
                task, task_result, score
            )

            # 4. 构建经验对象
            experience = Experience(
                id=str(uuid4()),
                task_summary=summary.task_summary or task.goal[:200],
                task_category=summary.task_category or "unknown",
                outcome=outcome,
                score=score,
                lessons_learned=summary.lessons_learned,
                tool_chain=tool_chain,
                steps_count=steps_count,
                success_rate=success_rate,
                retry_count=retry_count,
                duration_seconds=int(task_result.total_duration_seconds),
                is_permanent=summary.is_permanent,
                generality=summary.generality,
                project_name=project_name,
                keywords=summary.keywords or self._fallback_keywords(task.goal),
                tags=summary.tags,
            )

            # 5. 持久化
            await self._repo.save(experience)
            logger.info(
                "经验记录完成: id=%s score=%.2f category=%s",
                experience.id, score, experience.task_category,
            )
            return experience

        except Exception as e:
            logger.error("经验记录失败（不阻塞主流程）: %s", e, exc_info=True)
            return None

    def _calculate_score(self, task_result: TaskResult) -> float:
        """计算经验评分 (-1.0 ~ 1.0)

        score = (success_rate × 0.5)
              + (step_efficiency × 0.2)
              + (tool_effectiveness × 0.2)
              - (retry_penalty × 0.1)
        """
        total_steps = len(task_result.step_results)
        if total_steps == 0:
            return 0.0

        # 成功率
        success_steps = sum(
            1 for r in task_result.step_results
            if r.status.value == "done"
        )
        success_rate = success_steps / total_steps

        # 步骤效率（理想步骤数 = 成功步骤数，实际 = 总步骤数）
        ideal_steps = max(success_steps, 1)
        step_efficiency = max(0, 1 - (total_steps - ideal_steps) / total_steps)

        # 工具有效性（一次成功的比例）
        tool_success = sum(
            1 for r in task_result.step_results
            if r.retry_count == 0 and r.status.value == "done"
        )
        tool_effectiveness = tool_success / total_steps

        # 重试惩罚
        total_retries = sum(r.retry_count for r in task_result.step_results)
        retry_penalty = min(total_retries * 0.1, 1.0)

        # 加权计算
        w = self._settings
        raw_score = (
            success_rate * w.score_weight_success_rate
            + step_efficiency * w.score_weight_efficiency
            + tool_effectiveness * w.score_weight_tool
            - retry_penalty * w.score_weight_retry
        )

        # 结论调整
        if task_result.conclusion == TaskConclusion.FAILURE:
            raw_score -= 0.3
        elif task_result.conclusion == TaskConclusion.PARTIAL_SUCCESS:
            raw_score -= 0.1

        # 归一化到 [-1.0, 1.0]
        return max(-1.0, min(1.0, raw_score))

    async def _summarize_with_llm(
        self,
        task: Task,
        task_result: TaskResult,
        score: float,
    ) -> _SummaryResponse:
        """使用 LLM 总结经验

        LLM 不可用时降级为机械记录。
        """
        if self._llm is None:
            return self._mechanical_summary(task, task_result, score)

        steps_count = len(task_result.step_results)
        success_steps = sum(
            1 for r in task_result.step_results if r.status.value == "done"
        )
        tool_chain = self._extract_tool_chain(task_result.step_results)
        retry_count = sum(r.retry_count for r in task_result.step_results)

        user_prompt = EXPERIENCE_SUMMARY_USER_PROMPT_TEMPLATE.format(
            goal=task.goal[:500],
            outcome=task_result.conclusion.value,
            score=score,
            steps_count=steps_count,
            success_steps=success_steps,
            tool_chain=json.dumps(tool_chain, ensure_ascii=False),
            retry_count=retry_count,
            duration_seconds=int(task_result.total_duration_seconds),
        )

        try:
            response = await self._llm.structured_chat(
                system_prompt=EXPERIENCE_SUMMARY_SYSTEM_PROMPT,
                user_messages=[user_prompt],
                response_model=_SummaryResponse,
            )
            return response
        except Exception as e:
            logger.warning("LLM 总结失败，降级为机械记录: %s", e)
            return self._mechanical_summary(task, task_result, score)

    @staticmethod
    def _mechanical_summary(
        task: Task,
        task_result: TaskResult,
        score: float,
    ) -> _SummaryResponse:
        """机械总结（LLM 不可用时的降级方案）"""
        goal = task.goal[:200]
        keywords = ExperienceRecorder._fallback_keywords(goal)

        return _SummaryResponse(
            task_summary=goal,
            task_category="unknown",
            lessons_learned=f"任务{task_result.conclusion.value}，评分{score:.2f}",
            keywords=keywords,
            tags=[],
            is_permanent=False,
            generality=0.5,
        )

    @staticmethod
    def _map_outcome(conclusion: TaskConclusion) -> str:
        """映射任务结论为经验 outcome"""
        mapping = {
            TaskConclusion.SUCCESS: "success",
            TaskConclusion.PARTIAL_SUCCESS: "partial",
            TaskConclusion.FAILURE: "failed",
            TaskConclusion.CANCELLED: "failed",
        }
        return mapping.get(conclusion, "failed")

    @staticmethod
    def _extract_tool_chain(step_results: list[StepResult]) -> list[str]:
        """从步骤结果中提取工具链"""
        tools = []
        seen = set()
        for result in step_results:
            if result.output and isinstance(result.output, dict):
                tool = result.output.get("tool_type", "")
                if tool and tool not in seen:
                    tools.append(tool)
                    seen.add(tool)
        return tools

    @staticmethod
    def _fallback_keywords(text: str) -> list[str]:
        """简单的关键词提取（降级方案）"""
        import re
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text)
        return list(set(words))[:10]
