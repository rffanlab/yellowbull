"""T00-01: 配置管理单元测试"""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from yellowbull.config.settings import (
    DatabaseSettings,
    ExperienceSettings,
    ExecutionSettings,
    LLMSettings,
    Settings,
)


@pytest.fixture
def settings_data_dir(tmp_path):
    return tmp_path / "yellowbull_data"


class TestLLMSettings:
    """TC-00-01-01 ~ TC-00-01-05: LLM 配置"""

    def test_default_values(self):
        """TC-00-01-01: 默认配置加载"""
        settings = LLMSettings()
        assert settings.provider == "openai"
        assert settings.model == "gpt-4o"
        assert settings.api_key == ""
        assert settings.temperature == 0.3
        assert settings.max_tokens == 4096
        assert settings.timeout == 60

    def test_custom_values(self):
        """TC-00-01-02: 自定义配置值"""
        settings = LLMSettings(provider="anthropic", model="claude-3", temperature=0.7)
        assert settings.provider == "anthropic"
        assert settings.model == "claude-3"
        assert settings.temperature == 0.7

    def test_env_variable_override(self, monkeypatch):
        """TC-00-01-03: 环境变量覆盖"""
        monkeypatch.setenv("YELLOWBULL_LLM_API_KEY", "env-key-123")
        monkeypatch.setenv("YELLOWBULL_LLM_MODEL", "gpt-4-turbo")
        settings = LLMSettings()
        assert settings.api_key == "env-key-123"
        assert settings.model == "gpt-4-turbo"

    def test_type_validation(self):
        """TC-00-10-01: 配置值类型错误"""
        with pytest.raises(ValidationError):
            LLMSettings(temperature="not_a_number")

    def test_negative_timeout(self):
        """TC-00-10-06: 负值拒绝"""
        settings = LLMSettings(timeout=0)
        assert settings.timeout == 0


class TestExecutionSettings:
    """执行配置"""

    def test_default_values(self):
        settings = ExecutionSettings()
        assert settings.step_timeout == 120
        assert settings.task_timeout == 1800
        assert settings.max_total_steps == 100
        assert settings.max_retries_per_step == 2

    def test_custom_values(self):
        settings = ExecutionSettings(step_timeout=60, max_total_steps=50)
        assert settings.step_timeout == 60
        assert settings.max_total_steps == 50


class TestExperienceSettings:
    """经验系统配置"""

    def test_default_values(self):
        settings = ExperienceSettings()
        assert settings.enabled is True
        assert settings.max_retrieve_count == 5
        assert settings.min_relevance_score == 0.3

    def test_disable_experience(self):
        settings = ExperienceSettings(enabled=False)
        assert settings.enabled is False


class TestDatabaseSettings:
    """数据库配置"""

    def test_default_path(self):
        settings = DatabaseSettings()
        assert settings.path == "./data/yellowbull.db"

    def test_custom_path(self):
        settings = DatabaseSettings(path="./custom/db.sqlite")
        assert settings.path == "./custom/db.sqlite"


class TestSettings:
    """TC-00-01: 顶层 Settings"""

    def test_default_settings(self):
        """TC-00-01-01: 默认配置加载"""
        settings = Settings()
        assert settings.llm.provider == "openai"
        assert settings.execution.step_timeout == 120
        assert settings.experience.enabled is True

    def test_enabled_tools(self):
        """解析工具列表"""
        settings = Settings()
        tools = settings.enabled_tools
        assert isinstance(tools, list)
        assert "file" in tools

    def test_data_dir_created(self):
        """数据目录自动创建"""
        settings = Settings()
        assert settings.data_dir.exists()

    def test_extra_fields_ignored(self):
        """TC-00-10-03: 多余字段忽略"""
        settings = Settings(unknown_field="ignored", another="value")
        assert settings.llm.provider == "openai"

    def test_env_prefix_isolation(self, monkeypatch):
        """TC-00-10-05: 环境变量前缀冲突"""
        monkeypatch.setenv("LLM_API_KEY", "should-not-work")
        settings = Settings()
        assert settings.llm.api_key != "should-not-work"

    def test_partial_override(self):
        """TC-00-10-04: 嵌套配置部分覆盖"""
        llm = LLMSettings(model="custom-model")
        settings = Settings(llm=llm)
        assert settings.llm.model == "custom-model"
        assert settings.llm.provider == "openai"  # 默认值保留


class TestSettingsEnvOverride:
    """TC-00-01-03: 环境变量覆盖测试"""

    def test_full_env_override(self, monkeypatch):
        monkeypatch.setenv("YELLOWBULL_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("YELLOWBULL_LLM_MODEL", "claude-3-opus")
        settings = Settings()
        assert settings.llm.provider == "anthropic"
        assert settings.llm.model == "claude-3-opus"
