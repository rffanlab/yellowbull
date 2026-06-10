"""T00-09: 代码分析工具单元测试"""

import tempfile
from pathlib import Path

import pytest

from yellowbull.tools.code_tool import CodeTool


@pytest.fixture
def tool():
    return CodeTool(llm_client=None)


@pytest.fixture
def test_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestCodeToolAnalyze:
    """代码分析"""

    @pytest.mark.asyncio
    async def test_analyze_file(self, tool, test_dir):
        file_path = Path(test_dir) / "test.py"
        file_path.write_text("def hello():\n    print('world')\n")
        result = await tool.execute({"action": "analyze", "file_path": str(file_path), "analysis_type": "overview"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self, tool):
        result = await tool.execute({"action": "analyze", "file_path": "/nonexistent.py", "analysis_type": "overview"})
        assert result.success is False


class TestCodeToolGenerate:
    """代码生成"""

    @pytest.mark.asyncio
    async def test_generate_without_llm(self, tool):
        """无 LLM 客户端时生成不可用"""
        result = await tool.execute({"action": "generate", "prompt": "hello", "language": "python"})
        assert result.success is False or "不可用" in (result.error or "")

    @pytest.mark.asyncio
    async def test_generate_with_llm(self, test_dir):
        """有 LLM 客户端时正常生成"""
        from unittest.mock import AsyncMock

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="print('hi')")
        tool_with_llm = CodeTool(llm_client=mock_llm)
        result = await tool_with_llm.execute({"action": "generate", "prompt": "hello", "language": "python"})
        assert result.success is True


class TestCodeToolModify:
    """代码修改"""

    @pytest.mark.asyncio
    async def test_modify_file(self, tool, test_dir):
        file_path = Path(test_dir) / "test.py"
        file_path.write_text("original content")
        result = await tool.execute(
            {
                "action": "modify",
                "file_path": str(file_path),
                "instructions": "replace original with new",
                "replacement": "new content",
            }
        )
        assert result.success is True


class TestCodeToolValidation:
    """参数校验"""

    @pytest.mark.asyncio
    async def test_missing_action(self, tool):
        result = await tool.execute({})
        assert result.success is False

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute({"action": "unknown"})
        assert result.success is False


class TestCodeToolProperties:
    """工具属性"""

    def test_tool_name(self, tool):
        assert tool.name == "code"

    def test_tool_is_safe(self, tool):
        assert tool.is_safe is True
