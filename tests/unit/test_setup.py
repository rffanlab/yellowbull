"""setup 命令单元测试

覆盖: _generate_env, _init_data_dirs, _init_database, _gitignore_add_env,
       Settings.export_env(), Settings.from_dict()
       --non-interactive, --init-data-only, --show-config, --force
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

# ── Fixtures ───────────────────────────────────────────────


@pytest.fixture
def tmp_dir(tmp_path: Path) -> Path:
    """创建临时工作目录"""
    return tmp_path


@pytest.fixture
def cli_runner() -> CliRunner:
    """Click CLI 测试运行器"""
    return CliRunner()


# ── Settings export_env / from_dict 测试 ───────────────────


class TestSettingsExportEnv:
    """Settings.export_env() 和 Settings.from_dict() 测试"""

    def test_export_env_creates_file(self, tmp_dir: Path):
        """用途: 验证 export_env 生成 .env 文件

        入参: 临时目录
        返回: 无
        """
        from yellowbull.config.settings import Settings

        settings = Settings()
        env_path = tmp_dir / ".env"
        settings.export_env(env_path)

        assert env_path.exists()
        content = env_path.read_text(encoding="utf-8")
        assert "YELLOWBULL_LLM_PROVIDER=" in content
        assert "YELLOWBULL_LLM_MODEL=" in content
        assert "YELLOWBULL_DATABASE_PATH=" in content

    def test_export_env_content_correct(self, tmp_dir: Path):
        """用途: 验证 .env 文件内容格式正确

        入参: 临时目录
        返回: 无
        """
        from yellowbull.config.settings import Settings

        settings = Settings()
        env_path = tmp_dir / ".env"
        settings.export_env(env_path)

        content = env_path.read_text(encoding="utf-8")
        # 验证 KEY=VALUE 格式，无引号包裹
        for line in content.strip().split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            assert "=" in line, f"行 '{line}' 缺少 = 分隔符"
            key, value = line.split("=", 1)
            assert key.startswith("YELLOWBULL_"), f"Key '{key}' 缺少前缀 YELLOWBULL_"

    def test_export_env_custom_values(self, tmp_dir: Path):
        """用途: 验证自定义配置值正确写入 .env

        入参: 临时目录
        返回: 无
        """
        from yellowbull.config.settings import DatabaseSettings, LLMSettings, Settings

        settings = Settings()
        settings.llm = LLMSettings(provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-test-key")
        settings.database = DatabaseSettings(path="/custom/path.db")
        settings.tools_allowed = "file,shell"

        env_path = tmp_dir / ".env"
        settings.export_env(env_path)

        content = env_path.read_text(encoding="utf-8")
        assert "YELLOWBULL_LLM_PROVIDER=anthropic" in content
        assert "YELLOWBULL_LLM_MODEL=claude-sonnet-4-20250514" in content
        assert "YELLOWBULL_LLM_API_KEY=sk-test-key" in content
        assert "YELLOWBULL_DATABASE_PATH=/custom/path.db" in content
        assert "YELLOWBULL_TOOLS_ALLOWED=file,shell" in content

    def test_from_dict(self):
        """用途: 验证 from_dict 从扁平 dict 创建 Settings

        入参: 无
        返回: 无
        """
        from yellowbull.config.settings import (
            DatabaseSettings,
            ExecutionSettings,
            LLMSettings,
            Settings,
        )

        config = {
            "llm_provider": "anthropic",
            "llm_model": "claude-sonnet-4-20250514",
            "llm_api_key": "sk-test-key",
            "db_path": "/custom/path.db",
            "tools_allowed": "file,shell",
            "step_timeout": 60,
            "task_timeout": 900,
            "max_steps": 50,
            "retry_limit": 3,
        }

        settings = Settings.from_dict(config)

        assert isinstance(settings.llm, LLMSettings)
        assert settings.llm.provider == "anthropic"
        assert settings.llm.model == "claude-sonnet-4-20250514"
        assert settings.llm.api_key == "sk-test-key"
        assert settings.database.path == "/custom/path.db"
        assert settings.tools_allowed == "file,shell"
        assert isinstance(settings.execution, ExecutionSettings)
        assert settings.execution.step_timeout == 60
        assert settings.execution.task_timeout == 900
        assert settings.execution.max_total_steps == 50
        assert settings.execution.max_retries_per_step == 3

    def test_from_dict_defaults(self):
        """用途: 验证 from_dict 缺失字段时使用默认值

        入参: 无
        返回: 无
        """
        from yellowbull.config.settings import Settings

        config = {
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
        }

        settings = Settings.from_dict(config)

        assert settings.llm.provider == "openai"
        assert settings.llm.model == "gpt-4o-mini"
        # 默认值
        assert settings.execution.step_timeout == 120
        assert settings.execution.max_total_steps == 100


# ── .env 生成测试 ──────────────────────────────────────────


class TestGenerateEnv:
    """_generate_env() 函数测试"""

    def test_generate_env_creates_file(self, tmp_dir: Path):
        """用途: 验证 _generate_env 创建 .env 文件

        入参: 临时目录 + 配置 dict
        返回: 无
        """
        from yellowbull.cli.setup import _generate_env

        config = {
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "llm_api_key": "sk-test123",
            "db_path": "./data/yellowbull.db",
            "tools_allowed": "file,shell,code",
        }
        env_path = tmp_dir / ".env"

        _generate_env(config, env_path)

        assert env_path.exists()
        content = env_path.read_text(encoding="utf-8")
        assert "YELLOWBULL_LLM_PROVIDER=openai" in content
        assert "YELLOWBULL_LLM_API_KEY=sk-test123" in content

    def test_generate_env_overwrite_protection(self, tmp_dir: Path):
        """用途: 验证 _generate_env 本身不检查覆盖（CLI 层负责）

        入参: 临时目录 + 已有 .env
        返回: 无
        """
        from yellowbull.cli.setup import _generate_env

        env_path = tmp_dir / ".env"
        env_path.write_text("OLD=value", encoding="utf-8")

        config = {
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "llm_api_key": "sk-test123",
        }

        # _generate_env 本身不检查覆盖，直接写入
        _generate_env(config, env_path)

        content = env_path.read_text(encoding="utf-8")
        assert "YELLOWBULL_LLM_PROVIDER=openai" in content


# ── 数据目录初始化测试 ─────────────────────────────────────


class TestDataInit:
    """_init_data_dirs() + _init_database() 测试"""

    def test_init_data_dirs_creates_directory(self, tmp_dir: Path):
        """用途: 验证数据目录创建成功

        入参: 临时目录
        返回: 无
        """
        from yellowbull.cli.setup import _init_data_dirs

        db_path_str = str(tmp_dir / "data" / "yellowbull.db")

        result = _init_data_dirs(db_path_str)

        assert (tmp_dir / "data").exists()
        assert (tmp_dir / "data").is_dir()
        # _init_data_dirs 返回父目录（绝对路径）
        assert result == (Path(db_path_str).parent)

    def test_init_database_creates_tables(self, tmp_dir: Path):
        """用途: 验证数据库初始化创建所有表

        入参: 临时目录
        返回: 无
        """
        import asyncio

        from yellowbull.cli.setup import _init_database

        db_path = tmp_dir / "data" / "test.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        async def _run():
            await _init_database(db_path)

            # 验证表存在 — 通过重新连接检查
            import aiosqlite

            async with aiosqlite.connect(str(db_path)) as conn:
                async with conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ) as cursor:
                    tables = [row[0] async for row in cursor]

            assert "experiences" in tables
            assert "experience_keywords" in tables
            assert "experience_tags" in tables

        asyncio.run(_run())


# ── .gitignore 测试 ────────────────────────────────────────


class TestGitignore:
    """_gitignore_add_env() 测试"""

    def test_gitignore_create_and_add(self, tmp_dir: Path):
        """用途: 验证 .gitignore 不存在时创建并追加 .env

        入参: 临时目录（无 .gitignore）
        返回: 无
        """
        from yellowbull.cli.setup import _gitignore_add_env

        gitignore = tmp_dir / ".gitignore"
        assert not gitignore.exists()

        # 需要在 tmp_dir 下执行
        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            _gitignore_add_env(gitignore)
        finally:
            os.chdir(old_cwd)

        assert gitignore.exists()
        assert ".env" in gitignore.read_text(encoding="utf-8")

    def test_gitignore_append_not_replace(self, tmp_dir: Path):
        """用途: 验证 .gitignore 追加模式不破坏原有内容

        入参: 临时目录（已有 .gitignore）
        返回: 无
        """
        from yellowbull.cli.setup import _gitignore_add_env

        gitignore = tmp_dir / ".gitignore"
        gitignore.write_text("__pycache__/\n*.pyc\n", encoding="utf-8")

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            _gitignore_add_env(gitignore)
        finally:
            os.chdir(old_cwd)

        result = gitignore.read_text(encoding="utf-8")
        assert "__pycache__/" in result  # 原有内容保留
        assert "*.pyc" in result
        assert ".env" in result

    def test_gitignore_idempotent(self, tmp_dir: Path):
        """用途: 验证 .gitignore 中已有 .env 时不重复追加

        入参: 临时目录（.gitignore 已包含 .env）
        返回: 无
        """
        from yellowbull.cli.setup import _gitignore_add_env

        gitignore = tmp_dir / ".gitignore"
        gitignore.write_text(".env\n", encoding="utf-8")

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            _gitignore_add_env(gitignore)
        finally:
            os.chdir(old_cwd)

        result = gitignore.read_text(encoding="utf-8")
        assert result.count(".env") == 1


# ── CLI 命令测试 ───────────────────────────────────────────


class TestSetupCLI:
    """setup 命令 CLI 入口测试"""

    def test_non_interactive_setup_success(self, cli_runner: CliRunner, tmp_dir: Path):
        """用途: 验证 --non-interactive 模式完整流程

        入参: CLI runner + 临时目录
        返回: 无
        """
        from yellowbull.cli.setup import setup

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            result = cli_runner.invoke(
                setup,
                [
                    "--non-interactive",
                    "--provider", "openai",
                    "--model", "gpt-4o",
                    "--api-key", "sk-test123",
                ],
                catch_exceptions=False,
            )
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        assert (tmp_dir / ".env").exists()
        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        assert "YELLOWBULL_LLM_PROVIDER=openai" in content
        assert "YELLOWBULL_LLM_MODEL=gpt-4o" in content

    def test_non_interactive_missing_params(self, cli_runner: CliRunner):
        """用途: 验证 --non-interactive 缺少必要参数时报错

        入参: CLI runner
        返回: 无
        """
        from yellowbull.cli.setup import setup

        result = cli_runner.invoke(
            setup,
            ["--non-interactive"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "需要" in result.output or "required" in result.output.lower() or "ClickException" in str(type(result.exception))

    def test_ollama_auto_base_url(self, cli_runner: CliRunner, tmp_dir: Path):
        """用途: 验证 Ollama provider 自动填充 base_url

        入参: CLI runner + 临时目录
        返回: 无
        """
        from yellowbull.cli.setup import setup

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            result = cli_runner.invoke(
                setup,
                [
                    "--non-interactive",
                    "--provider", "ollama",
                    "--model", "llama3",
                    "--api-key", "not-needed",
                ],
                catch_exceptions=False,
            )
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        assert "YELLOWBULL_LLM_BASE_URL=http://localhost:11434" in content

    def test_init_data_only(self, cli_runner: CliRunner, tmp_dir: Path):
        """用途: 验证 --init-data-only 仅初始化数据

        入参: CLI runner + 临时目录
        返回: 无
        """
        from yellowbull.cli.setup import setup

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            result = cli_runner.invoke(
                setup,
                ["--init-data-only"],
                catch_exceptions=False,
            )
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        # .env 不应被创建（仅数据初始化）
        assert not (tmp_dir / ".env").exists()

    def test_show_config(self, cli_runner: CliRunner):
        """用途: 验证 --show-config 打印配置后退出

        入参: CLI runner
        返回: 无
        """
        from yellowbull.cli.setup import setup

        result = cli_runner.invoke(
            setup,
            ["--show-config"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0


# ── Python 版本检测测试 ────────────────────────────────────


class TestPythonVersionCheck:
    """_check_environment() 测试"""

    def test_python_version_pass(self):
        """用途: 验证当前 Python >= 3.10 通过检查

        入参: 无
        返回: 无
        """
        from yellowbull.cli.setup import _check_environment

        assert _check_environment() is True

    def test_python_version_fail(self):
        """用途: 验证 Python < 3.10 时拒绝执行

        入参: mock Python 3.9
        返回: 无
        """
        from yellowbull.cli.setup import _check_environment

        with patch("sys.version_info", (3, 9, 0)):
            result = _check_environment()
            assert result is False


# ── 边界/异常测试 ──────────────────────────────────────────


class TestEdgeCases:
    """边界和异常情况测试"""

    def test_custom_db_path(self, cli_runner: CliRunner, tmp_dir: Path):
        """用途: 验证自定义数据库路径正确写入 .env

        入参: CLI runner + 临时目录
        返回: 无
        """
        from yellowbull.cli.setup import setup

        custom_db = str(tmp_dir / "custom" / "my.db")

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            result = cli_runner.invoke(
                setup,
                [
                    "--non-interactive",
                    "--provider", "openai",
                    "--model", "gpt-4o",
                    "--api-key", "sk-test123",
                    "--db-path", custom_db,
                ],
                catch_exceptions=False,
            )
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        assert f"YELLOWBULL_DATABASE_PATH={custom_db}" in content

    def test_custom_tools_list(self, cli_runner: CliRunner, tmp_dir: Path):
        """用途: 验证自定义工具列表正确写入 .env

        入参: CLI runner + 临时目录
        返回: 无
        """
        from yellowbull.cli.setup import setup

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)
            result = cli_runner.invoke(
                setup,
                [
                    "--non-interactive",
                    "--provider", "openai",
                    "--model", "gpt-4o",
                    "--api-key", "sk-test123",
                    "--tools-allowed", "file,shell",
                ],
                catch_exceptions=False,
            )
        finally:
            os.chdir(old_cwd)

        assert result.exit_code == 0
        content = (tmp_dir / ".env").read_text(encoding="utf-8")
        assert "YELLOWBULL_TOOLS_ALLOWED=file,shell" in content

    def test_idempotent_execution(self, cli_runner: CliRunner, tmp_dir: Path):
        """用途: 验证重复执行幂等（--force 覆盖不报错）

        入参: CLI runner + 临时目录
        返回: 无
        """
        from yellowbull.cli.setup import setup

        old_cwd = Path.cwd()
        try:
            import os
            os.chdir(tmp_dir)

            # 第一次执行
            result1 = cli_runner.invoke(
                setup,
                [
                    "--non-interactive",
                    "--provider", "openai",
                    "--model", "gpt-4o",
                    "--api-key", "sk-test123",
                ],
                catch_exceptions=False,
            )
            assert result1.exit_code == 0

            # 第二次执行（无 --force 应报错）
            result2 = cli_runner.invoke(
                setup,
                [
                    "--non-interactive",
                    "--provider", "openai",
                    "--model", "gpt-4o",
                    "--api-key", "sk-test123",
                ],
                catch_exceptions=False,
            )
            assert result2.exit_code != 0

            # 第三次执行（--force 应成功）
            result3 = cli_runner.invoke(
                setup,
                [
                    "--non-interactive",
                    "--provider", "anthropic",
                    "--model", "claude-sonnet-4-20250514",
                    "--api-key", "sk-new-key",
                    "--force",
                ],
                catch_exceptions=False,
            )
            assert result3.exit_code == 0

            content = (tmp_dir / ".env").read_text(encoding="utf-8")
            assert "YELLOWBULL_LLM_PROVIDER=anthropic" in content
        finally:
            os.chdir(old_cwd)
