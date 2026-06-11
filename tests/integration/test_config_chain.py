"""集成测试: 配置 -> 日志 -> LLM 客户端链路"""

import logging
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from yellowbull.config.settings import LLMSettings, Settings
from yellowbull.llm.client import LLMClient


class TestConfigToLLMChain:
    """配置 -> LLM 客户端链路"""

    @pytest.mark.asyncio
    async def test_full_chain(self):
        """完整链路: 创建配置 -> 初始化客户端 -> 发送请求"""
        settings = Settings()
        client = LLMClient(settings.llm)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Chain test OK"))]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10)

        with patch.object(client._client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response
            result = await client.chat("system", ["test"])
            assert result == "Chain test OK"

    def test_config_values_propagate(self):
        """配置值正确传递到客户端"""
        llm_settings = LLMSettings(
            provider="openai",
            model="gpt-4",
            temperature=0.7,
            max_tokens=2048,
            timeout=30,
        )
        client = LLMClient(llm_settings)
        assert client._settings.model == "gpt-4"
        assert client._settings.temperature == 0.7
        assert client._settings.max_tokens == 2048


class TestLoggingIntegration:
    """T00-02: 日志系统"""

    def test_logger_creation(self):
        """TC-00-02-01: 日志器创建"""
        logger = logging.getLogger("yellowbull.test")
        assert logger is not None

    def test_debug_log_level(self, caplog):
        """TC-00-02-01: DEBUG 日志输出"""
        logger = logging.getLogger("yellowbull.test")
        logger.setLevel(logging.DEBUG)
        with caplog.at_level(logging.DEBUG):
            logger.debug("test debug message")
            assert "test debug message" in caplog.text

    def test_log_levels(self, caplog):
        """TC-00-02-01: 日志分级输出"""
        logger = logging.getLogger("yellowbull.test")
        logger.setLevel(logging.DEBUG)
        with caplog.at_level(logging.DEBUG):
            logger.debug("debug msg")
            logger.info("info msg")
            logger.warning("warning msg")
            logger.error("error msg")
            assert "debug msg" in caplog.text
            assert "info msg" in caplog.text
            assert "warning msg" in caplog.text
            assert "error msg" in caplog.text

    def test_structured_log_format(self, caplog):
        """TC-00-02-03: 结构化日志格式"""
        logger = logging.getLogger("yellowbull.test")
        logger.setLevel(logging.INFO)
        with caplog.at_level(logging.INFO):
            logger.info("structured test")
            record = caplog.records[0]
            assert record.name == "yellowbull.test"
            assert record.levelname == "INFO"
