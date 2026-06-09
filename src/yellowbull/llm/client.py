"""LLM 调用客户端

统一封装 LLM 请求接口，支持 OpenAI 兼容 API。
提供 chat() 文本对话和 structured_chat() 结构化输出两种模式。
"""

import json
import logging

from openai import AsyncOpenAI, APIConnectionError, RateLimitError
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from yellowbull.config.settings import LLMSettings

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 调用客户端"""

    def __init__(self, settings: LLMSettings):
        """用途: 初始化 LLM 客户端，创建 AsyncOpenAI 连接

        入参:
            settings (LLMSettings): LLM 配置对象
        """
        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.api_key or "dummy-key",
            base_url=settings.base_url,
            timeout=settings.timeout,
        )

    @retry(
        retry=retry_if_exception_type((APIConnectionError, RateLimitError, TimeoutError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def chat(
        self,
        system_prompt: str,
        user_messages: list[str],
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        """用途: 发起对话请求，返回 LLM 回复文本

        入参:
            system_prompt (str): 系统提示词
            user_messages (list[str]): 用户消息列表
            json_mode (bool): 是否启用 JSON 模式
            temperature (float | None): 采样温度，None 时使用默认值

        返回:
            str: LLM 回复文本
        """
        messages = [{"role": "system", "content": system_prompt}]
        for msg in user_messages:
            messages.append({"role": "user", "content": msg})

        kwargs = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""

            # 记录 token 消耗
            if hasattr(response, "usage") and response.usage:
                logger.info(
                    "LLM 调用完成 | model=%s | prompt_tokens=%d | completion_tokens=%d | total_tokens=%d",
                    self._settings.model,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                    response.usage.total_tokens,
                )

            return content
        except Exception as e:
            logger.error("LLM 请求失败: %s", e)
            raise

    @retry(
        retry=retry_if_exception_type((APIConnectionError, RateLimitError, TimeoutError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def structured_chat(
        self,
        system_prompt: str,
        user_messages: list[str],
        response_model: type[BaseModel],
    ) -> BaseModel:
        """用途: 发起对话请求，自动解析 JSON 响应为 Pydantic 模型

        入参:
            system_prompt (str): 系统提示词
            user_messages (list[str]): 用户消息列表
            response_model (type[BaseModel]): 目标 Pydantic 模型类

        返回:
            BaseModel: 解析后的模型实例

        异常:
            ValueError: JSON 解析失败或模型校验失败时抛出
        """
        raw_text = await self.chat(
            system_prompt=system_prompt,
            user_messages=user_messages,
            json_mode=True,
        )

        # 尝试从回复中提取 JSON（兼容 code block 包裹的情况）
        text = raw_text.strip()
        if text.startswith("```"):
            # 移除 markdown code block 标记
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 返回的 JSON 解析失败: {e}\n原始内容: {text[:200]}") from e

        try:
            return response_model(**data)
        except Exception as e:
            raise ValueError(f"模型校验失败: {e}\nJSON 数据: {data}") from e
