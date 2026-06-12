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


class TestCodeToolAnalyzeTypes:
    """代码分析 - 各种 analysis_type"""

    @pytest.mark.asyncio
    async def test_analyze_imports(self, tool, test_dir):
        file_path = Path(test_dir) / "test.py"
        file_path.write_text("import os\nfrom pathlib import Path\nprint('hi')\n")
        result = await tool.execute({"action": "analyze", "file_path": str(file_path), "analysis_type": "imports"})
        assert result.success is True
        assert "imports" in result.output
        assert len(result.output["imports"]) == 2

    @pytest.mark.asyncio
    async def test_analyze_functions(self, tool, test_dir):
        file_path = Path(test_dir) / "test.py"
        file_path.write_text("def hello():\n    pass\n\ndef world(x):\n    return x\n")
        result = await tool.execute({"action": "analyze", "file_path": str(file_path), "analysis_type": "functions"})
        assert result.success is True
        assert "functions" in result.output
        assert len(result.output["functions"]) == 2

    @pytest.mark.asyncio
    async def test_analyze_classes(self, tool, test_dir):
        file_path = Path(test_dir) / "test.py"
        file_path.write_text("class Foo:\n    pass\n\nclass Bar(Baz):\n    pass\n")
        result = await tool.execute({"action": "analyze", "file_path": str(file_path), "analysis_type": "classes"})
        assert result.success is True
        assert "classes" in result.output
        assert len(result.output["classes"]) == 2

    @pytest.mark.asyncio
    async def test_analyze_unknown_type_defaults_to_structure(self, tool, test_dir):
        file_path = Path(test_dir) / "test.py"
        file_path.write_text("def hello():\n    pass\n")
        result = await tool.execute({"action": "analyze", "file_path": str(file_path), "analysis_type": "invalid"})
        assert result.success is True
        assert "structure" in result.output


class TestCodeToolModifyAdvanced:
    """代码修改 - 高级场景"""

    @pytest.mark.asyncio
    async def test_modify_without_llm_no_replacement(self, tool, test_dir):
        file_path = Path(test_dir) / "test.py"
        file_path.write_text("original content")
        result = await tool.execute({
            "action": "modify",
            "file_path": str(file_path),
            "instructions": "add comment",
        })
        assert result.success is False
        assert "未配置" in (result.error or "")

    @pytest.mark.asyncio
    async def test_modify_with_llm(self, test_dir):
        from unittest.mock import AsyncMock

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="modified code")
        tool_with_llm = CodeTool(llm_client=mock_llm)

        file_path = Path(test_dir) / "test.py"
        file_path.write_text("original content")
        result = await tool_with_llm.execute({
            "action": "modify",
            "file_path": str(file_path),
            "instructions": "add comment",
        })
        assert result.success is True
        assert result.output == "modified code"

    @pytest.mark.asyncio
    async def test_modify_nonexistent_file(self, tool):
        result = await tool.execute({
            "action": "modify",
            "file_path": "/nonexistent.py",
            "replacement": "new content",
        })
        assert result.success is False


class TestCodeToolHelperMethods:
    """静态辅助方法"""

    def test_get_structure(self):
        content = "import os\nclass Foo:\n    pass\n\ndef bar():\n    pass\nx = 1\n"
        structure = CodeTool._get_structure(content)
        types = [item["type"] for item in structure]
        assert "import" in types
        assert "class" in types
        assert "function" in types
        assert "variable" in types

    def test_get_imports(self):
        content = "import os\nfrom pathlib import Path\nprint('hi')\n"
        imports = CodeTool._get_imports(content)
        assert len(imports) == 2
        assert "import os" in imports

    def test_get_functions(self):
        content = "def hello():\n    pass\n\ndef world(x, y):\n    return x + y\n"
        functions = CodeTool._get_functions(content)
        assert len(functions) == 2
        names = [f["name"] for f in functions]
        assert "hello" in names
        assert "world" in names

    def test_get_classes(self):
        content = "class Foo:\n    pass\n\nclass Bar(Baz):\n    pass\n"
        classes = CodeTool._get_classes(content)
        assert len(classes) == 2
        names = [c["name"] for c in classes]
        assert "Foo" in names
        assert "Bar" in names

    def test_get_class_without_bases(self):
        content = "class Foo:\n    pass\n"
        classes = CodeTool._get_classes(content)
        assert len(classes) == 1
        assert classes[0]["bases"] is None


class TestCodeToolExceptionHandling:
    """异常处理"""

    @pytest.mark.asyncio
    async def test_execute_catches_exception(self, tool):
        from unittest.mock import patch

        with patch.object(tool, "_analyze_code", side_effect=RuntimeError("test error")):
            result = await tool.execute({"action": "analyze", "file_path": "/tmp/x.py"})
            assert result.success is False
            assert "test error" in (result.error or "")


class TestCodeToolValidateParams:
    """参数校验"""

    def test_validate_params_with_action(self, tool):
        assert tool.validate_params({"action": "analyze"}) is True

    def test_validate_params_without_action(self, tool):
        assert tool.validate_params({}) is False
