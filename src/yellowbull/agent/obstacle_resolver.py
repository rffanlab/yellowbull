"""障碍解决模块

当步骤失败时，请求 LLM 分析原因并尝试解决。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.agent.step_state import StepState
from yellowbull.llm.client import LLMClient
from yellowbull.models.step import Step

logger = logging.getLogger(__name__)


class ObstacleAnalysis(BaseModel):
    """障碍分析结果"""

    cause: str = Field(description="失败原因")
    suggestion: str = Field(description="解决建议")
    is_recoverable: bool = Field(description="是否可恢复")


class ObstacleResolver:
    """障碍解决

    失败 → 请求 LLM 分析原因 → 尝试解决
    """

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def resolve(
        self,
        step: Step,
        state: StepState,
        error: str,
        context: dict | None = None,
    ) -> ObstacleAnalysis | None:
        """请求 LLM 分析失败原因并给出解决建议

        Args:
            step: 失败的步骤
            state: 步骤状态
            error: 错误信息
            context: 额外上下文

        Returns:
            ObstacleAnalysis 或 None
        """
        system_prompt = (
            "你是一个任务故障分析助手。请分析步骤失败的原因，"
            "给出解决建议，并判断是否可恢复。"
        )

        user_prompt = (
            f"步骤ID: {step.step_id}\n"
            f"描述: {step.description}\n"
            f"工具: {step.tool_hint}\n"
            f"错误信息: {error}\n"
            f"重试次数: {state.retry_count}\n"
        )

        if context:
            user_prompt += f"\n额外上下文:\n"
            for key, value in context.items():
                user_prompt += f"  - {key}: {value}\n"

        user_prompt += (
            "\n请分析:\n"
            "1. 失败原因\n"
            "2. 解决建议\n"
            "3. 是否可恢复 (true/false)"
        )

        try:
            response = await self.llm_client.chat(system_prompt, [user_prompt])
            return self._parse_analysis(response, error)
        except Exception as e:
            logger.error("障碍分析失败: %s", e)
            return None

    def _parse_analysis(
        self,
        response: str,
        error: str,
    ) -> ObstacleAnalysis:
        """解析 LLM 响应为 ObstacleAnalysis"""
        response_lower = response.lower()

        is_recoverable = (
            "true" in response_lower
            or "可恢复" in response
            or "可以解决" in response
        )

        return ObstacleAnalysis(
            cause=error,
            suggestion=response[:500],  # 截断过长响应
            is_recoverable=is_recoverable,
        )
