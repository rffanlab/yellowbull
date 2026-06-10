"""T00-03: LLM 客户端单元测试 (Mock)"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, RateLimitError
from pydantic import BaseModel

from yellowbull.config.settings import LLMSettings
from yellowbull.llm.client import LLMClient


class DummyResponse(BaseModel):
    name: str
    value: int


class TestLLMClientChat:
    """TC-00-03-01 ~ TC-00-03-06: chat() 方法"""

    @pytest.fixture
    def client(self):
        settings = LLMSettings(api_key="test-key")
        return LLMClient(settings)

    @pytest.mark.asyncio
    async def test_normal_chat(self, client):
        """TC-00-03-01: 正常对话请求"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello!"))]
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            result = await client.chat("system prompt", ["user message"])
            assert result == "Hello!"
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_json_mode(self, client):
        """TC-00-03-02: JSON 模式响应"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"key": "value"}'))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=10, total_tokens=15)

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            result = await client.chat("system", ["user"], json_mode=True)
            assert result == '{"key": "value"}'
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_timeout_error(self, client):
        """TC-00-03-04: 超时异常"""
        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = TimeoutError("request timeout")
            with pytest.raises(TimeoutError):
                await client.chat("system", ["user"])

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self, client):
        """TC-00-03-05: 自动重试"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="OK"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10)
        mock_request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [APIConnectionError(message="conn error", request=mock_request), mock_response]
            result = await client.chat("system", ["user"])
            assert result == "OK"
            assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, client):
        """TC-00-11-05: 重试耗尽"""
        mock_request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = APIConnectionError(message="persistent error", request=mock_request)
            with pytest.raises(APIConnectionError):
                await client.chat("system", ["user"])

    @pytest.mark.asyncio
    async def test_empty_response(self, client):
        """TC-00-11-06: 空响应处理"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=""))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=0, total_tokens=5)

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            result = await client.chat("system", ["user"])
            assert result == ""


class TestLLMClientStructuredChat:
    """TC-00-03-02: structured_chat() 方法"""

    @pytest.fixture
    def client(self):
        settings = LLMSettings(api_key="test-key")
        return LLMClient(settings)

    @pytest.mark.asyncio
    async def test_structured_response(self, client):
        """正常结构化响应"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"name": "test", "value": 42}'))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=10, total_tokens=15)

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            result = await client.structured_chat("system", ["user"], DummyResponse)
            assert isinstance(result, DummyResponse)
            assert result.name == "test"
            assert result.value == 42

    @pytest.mark.asyncio
    async def test_structured_response_with_code_block(self, client):
        """兼容 code block 包裹的 JSON"""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="```json\n{\"name\": \"test\", \"value\": 42}\n```"))
        ]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=10, total_tokens=15)

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            result = await client.structured_chat("system", ["user"], DummyResponse)
            assert result.name == "test"

    @pytest.mark.asyncio
    async def test_invalid_json(self, client):
        """TC-00-11-01: JSON 模式返回非 JSON"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="{invalid json"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10)

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            with pytest.raises(ValueError, match="JSON 解析失败"):
                await client.structured_chat("system", ["user"], DummyResponse)

    @pytest.mark.asyncio
    async def test_model_validation_failure(self, client):
        """模型校验失败"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"name": "test"}'))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10)

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            with pytest.raises(ValueError, match="模型校验失败"):
                await client.structured_chat("system", ["user"], DummyResponse)


class TestLLMClientInit:
    """客户端初始化"""

    def test_init_with_settings(self):
        settings = LLMSettings(api_key="my-key", base_url="https://custom.api", timeout=30)
        client = LLMClient(settings)
        assert client._settings.api_key == "my-key"

    def test_init_with_empty_api_key(self):
        settings = LLMSettings(api_key="")
        client = LLMClient(settings)
        assert client._client.api_key == "dummy-key"
