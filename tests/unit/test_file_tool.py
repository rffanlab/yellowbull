"""T00-07: 文件工具单元测试"""

import os
import tempfile
from pathlib import Path

import pytest

from yellowbull.tools.file_tool import FileTool
from yellowbull.tools.base import SideEffectType


@pytest.fixture
def tool():
    return FileTool()


@pytest.fixture
def test_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestFileToolRead:
    """TC-00-07-01: 读取文件"""

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tool, test_dir):
        file_path = Path(test_dir) / "test.txt"
        file_path.write_text("hello world")
        result = await tool.execute({"action": "read", "path": str(file_path)})
        assert result.success is True
        assert result.output == "hello world"

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tool):
        """TC-00-07-05: 文件不存在"""
        result = await tool.execute({"action": "read", "path": "/invalid/path/file.txt"})
        assert result.success is False
        assert "文件不存在" in result.error

    @pytest.mark.asyncio
    async def test_read_directory_as_file(self, tool, test_dir):
        """TC-00-13-06: 目录当文件读取"""
        result = await tool.execute({"action": "read", "path": test_dir})
        assert result.success is False
        assert "不是文件" in result.error

    @pytest.mark.asyncio
    async def test_read_empty_file(self, tool, test_dir):
        """TC-00-13-05: 空文件处理"""
        file_path = Path(test_dir) / "empty.txt"
        file_path.write_text("")
        result = await tool.execute({"action": "read", "path": str(file_path)})
        assert result.success is True
        assert result.output == ""

    @pytest.mark.asyncio
    async def test_read_file_with_chinese(self, tool, test_dir):
        """TC-00-13-02: 特殊字符路径"""
        file_path = Path(test_dir) / "测试文件.txt"
        file_path.write_text("中文内容", encoding="utf-8")
        result = await tool.execute({"action": "read", "path": str(file_path)})
        assert result.success is True
        assert result.output == "中文内容"


class TestFileToolWrite:
    """TC-00-07-02: 写入文件"""

    @pytest.mark.asyncio
    async def test_write_file(self, tool, test_dir):
        file_path = Path(test_dir) / "new_file.txt"
        result = await tool.execute({"action": "write", "path": str(file_path), "content": "test content"})
        assert result.success is True
        assert file_path.read_text() == "test content"

    @pytest.mark.asyncio
    async def test_write_file_creates_parent_dirs(self, tool, test_dir):
        file_path = Path(test_dir) / "sub" / "dir" / "file.txt"
        result = await tool.execute({"action": "write", "path": str(file_path), "content": "nested"})
        assert result.success is True
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_write_side_effect_recorded(self, tool, test_dir):
        file_path = Path(test_dir) / "side.txt"
        result = await tool.execute({"action": "write", "path": str(file_path), "content": "data"})
        assert any("file_write" in se for se in result.side_effects)


class TestFileToolSearch:
    """TC-00-07-03: 搜索文件"""

    @pytest.mark.asyncio
    async def test_search_files(self, tool, test_dir):
        (Path(test_dir) / "a.py").write_text("")
        (Path(test_dir) / "b.py").write_text("")
        (Path(test_dir) / "c.txt").write_text("")

        result = await tool.execute({"action": "search", "pattern": "*.py", "directory": test_dir})
        assert result.success is True
        assert len(result.output) == 2

    @pytest.mark.asyncio
    async def test_search_no_matches(self, tool, test_dir):
        result = await tool.execute({"action": "search", "pattern": "*.xyz", "directory": test_dir})
        assert result.success is True
        assert result.output == []


class TestFileToolList:
    """TC-00-07-04: 列出目录"""

    @pytest.mark.asyncio
    async def test_list_directory(self, tool, test_dir):
        (Path(test_dir) / "file1.txt").write_text("a")
        (Path(test_dir) / "file2.txt").write_text("bb")
        (Path(test_dir) / "subdir").mkdir()

        result = await tool.execute({"action": "list", "path": test_dir})
        assert result.success is True
        entries = result.output
        assert len(entries) == 3
        names = [e["name"] for e in entries]
        assert "file1.txt" in names

    @pytest.mark.asyncio
    async def test_list_nonexistent_directory(self, tool):
        result = await tool.execute({"action": "list", "path": "/nonexistent/dir"})
        assert result.success is False


class TestFileToolValidation:
    """参数校验"""

    @pytest.mark.asyncio
    async def test_missing_action(self, tool):
        result = await tool.execute({"path": "some/path"})
        assert result.success is False
        assert "参数校验失败" in result.error

    @pytest.mark.asyncio
    async def test_unknown_action(self, tool):
        result = await tool.execute({"action": "delete", "path": "some/path"})
        assert result.success is False
        assert "未知的文件操作" in result.error


class TestFileToolProperties:
    """工具属性"""

    def test_tool_name(self, tool):
        assert tool.name == "file"

    def test_tool_not_safe(self, tool):
        assert tool.is_safe is False

    def test_tool_has_side_effects(self, tool):
        assert SideEffectType.FILE_WRITE in tool.side_effects
