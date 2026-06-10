"""T00-08: Shell 工具单元测试"""

import pytest

from yellowbull.tools.shell_tool import ShellTool


@pytest.fixture
def tool():
    return ShellTool(safe_mode=True)


@pytest.fixture
def unsafe_tool():
    return ShellTool(safe_mode=False)


class TestShellToolBasic:
    """TC-00-08-01: 简单命令"""

    @pytest.mark.asyncio
    async def test_echo_command(self, tool):
        """TC-00-08-01: 简单命令"""
        result = await tool.execute({"command": "echo hello"})
        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_directory_listing(self, tool):
        result = await tool.execute({"command": "dir" if __import__("sys").platform.startswith("win") else "ls"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_command_with_stderr(self, tool):
        """命令产生 stderr"""
        cmd = "dir nonexistent_file_xyz" if __import__("sys").platform.startswith("win") else "ls /nonexistent_path_xyz"
        result = await tool.execute({"command": cmd})
        assert result.success is False


class TestShellToolSafety:
    """TC-00-08-02: 危险命令拦截"""

    @pytest.mark.asyncio
    async def test_rm_rf_blocked(self, tool):
        """TC-00-08-02 / TC-00-14-05: rm -rf 拦截"""
        result = await tool.execute({"command": "rm -rf /"})
        assert result.success is False
        assert "安全模式拦截" in result.error

    @pytest.mark.asyncio
    async def test_format_blocked(self, tool):
        result = await tool.execute({"command": "format C:"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_shutdown_blocked(self, tool):
        result = await tool.execute({"command": "shutdown -s"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_dd_blocked(self, tool):
        result = await tool.execute({"command": "dd if=/dev/zero of=/dev/sda"})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_safe_command_allowed(self, tool):
        """安全命令不被拦截"""
        result = await tool.execute({"command": "echo safe"})
        assert result.success is True


class TestShellToolTimeout:
    """TC-00-08-03: 超时终止"""

    @pytest.mark.asyncio
    async def test_timeout_termination(self, tool):
        """TC-00-08-03: 超时终止"""
        sleep_cmd = "timeout /t 10" if __import__("sys").platform.startswith("win") else "sleep 10"
        result = await tool.execute({"command": sleep_cmd, "timeout": 1})
        assert result.success is False
        assert "超时" in result.error


class TestShellToolOutput:
    """TC-00-08-04: 输出截断"""

    @pytest.mark.asyncio
    async def test_output_truncation(self, tool):
        """TC-00-08-04: 输出截断"""
        # 生成大量输出
        if __import__("sys").platform.startswith("win"):
            cmd = "for /L %i in (1,1,2000) do @echo line_%i"
        else:
            cmd = "seq 1 2000"
        result = await tool.execute({"command": cmd})
        assert result.success is True
        # 输出应被截断
        assert len(result.output) <= 8192 + 100  # 允许截断提示的额外长度


class TestShellToolValidation:
    """参数校验"""

    @pytest.mark.asyncio
    async def test_missing_command(self, tool):
        result = await tool.execute({})
        assert result.success is False
        assert "缺少 command" in result.error

    @pytest.mark.asyncio
    async def test_invalid_command_type(self, tool):
        result = await tool.execute({"command": 123})
        assert result.success is False


class TestShellToolProperties:
    """工具属性"""

    def test_tool_name(self, tool):
        assert tool.name == "shell"

    def test_tool_not_safe(self, tool):
        assert tool.is_safe is False

    def test_dangerous_detection(self, tool):
        assert tool._is_dangerous("rm -rf /") is True
        assert tool._is_dangerous("echo hello") is False

    def test_side_effect_detection(self, tool):
        assert tool._has_side_effects("pip install requests") is True
        assert tool._has_side_effects("echo hello") is False
