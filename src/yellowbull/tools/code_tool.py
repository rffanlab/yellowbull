"""代码分析工具

提供代码分析、代码生成（委托 LLM）和代码修改功能。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from yellowbull.tools.base import SideEffectType, Tool, ToolResult


class CodeTool(Tool):
    """代码分析工具"""

    def __init__(self, llm_client: Any = None) -> None:
        """用途: 初始化代码工具

        入参:
            llm_client (Any): LLM 客户端实例，用于代码生成（可选，未提供时生成能力不可用）

        返回: 无
        """
        super().__init__(
            name="code",
            description="代码分析工具：支持代码分析、代码生成（委托LLM）、代码修改",
            side_effects=[SideEffectType.FILE_WRITE],
            is_safe=True,
        )
        self._llm = llm_client

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """用途: 根据 action 参数分发到对应的代码操作

        入参:
            params (dict[str, Any]): 必须包含 action 字段，可选值:
                - analyze: 需 file_path, analysis_type
                - generate: 需 prompt, language
                - modify: 需 file_path, instructions

        返回:
            ToolResult: 执行结果
        """
        if not self.validate_params(params):
            return ToolResult(success=False, error="参数校验失败")

        action = params.get("action", "").lower()

        try:
            if action == "analyze":
                return await self._analyze_code(params)
            elif action == "generate":
                return await self._generate_code(params)
            elif action == "modify":
                return await self._modify_code(params)
            else:
                return ToolResult(success=False, error=f"未知的代码操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def validate_params(self, params: dict[str, Any]) -> bool:
        """用途: 校验参数是否包含 action 字段

        入参:
            params (dict[str, Any]): 待校验的参数

        返回:
            bool: 包含 action 字段返回 True
        """
        return "action" in params

    async def _analyze_code(self, params: dict[str, Any]) -> ToolResult:
        """用途: 分析代码文件结构（静态分析，不依赖 LLM）

        入参:
            params (dict[str, Any]): 需包含 file_path 和 analysis_type 字段
                analysis_type 可选: structure, imports, functions, classes

        返回:
            ToolResult: 成功时 output 为分析结果字典
        """
        file_path = Path(params["file_path"])
        analysis_type = params.get("analysis_type", "structure")

        if not file_path.exists():
            return ToolResult(success=False, error=f"文件不存在: {file_path}")

        content = file_path.read_text(encoding="utf-8", errors="replace")

        result = {
            "file": str(file_path),
            "lines": content.count("\n") + 1,
            "size_bytes": file_path.stat().st_size,
        }

        if analysis_type == "structure":
            result["structure"] = self._get_structure(content)
        elif analysis_type == "imports":
            result["imports"] = self._get_imports(content)
        elif analysis_type == "functions":
            result["functions"] = self._get_functions(content)
        elif analysis_type == "classes":
            result["classes"] = self._get_classes(content)
        else:
            result["structure"] = self._get_structure(content)

        return ToolResult(success=True, output=result)

    async def _generate_code(self, params: dict[str, Any]) -> ToolResult:
        """用途: 通过 LLM 生成代码

        入参:
            params (dict[str, Any]): 需包含 prompt 和 language 字段

        返回:
            ToolResult: 成功时 output 为生成的代码文本
        """
        if self._llm is None:
            return ToolResult(success=False, error="LLM 客户端未配置，无法生成代码")

        prompt = params["prompt"]
        language = params.get("language", "python")

        system_prompt = (
            f"你是一个代码生成助手。请根据用户的需求生成 {language} 代码。"
            "只输出代码，不要添加解释。"
        )

        code = await self._llm.chat(
            system_prompt=system_prompt,
            user_messages=[prompt],
        )

        return ToolResult(success=True, output=code)

    async def _modify_code(self, params: dict[str, Any]) -> ToolResult:
        """用途: 读取代码文件并通过 LLM 生成修改建议或直接替换

        入参:
            params (dict[str, Any]): 需包含 file_path 和 instructions 字段。
                如果提供 replacement 字段，则直接替换文件内容（不依赖 LLM）。

        返回:
            ToolResult: 成功时 output 为修改后的代码
        """
        file_path = Path(params["file_path"])

        if not file_path.exists():
            return ToolResult(success=False, error=f"文件不存在: {file_path}")

        # 直接替换模式（不依赖 LLM）
        if "replacement" in params:
            file_path.write_text(params["replacement"], encoding="utf-8")
            return ToolResult(success=True, output=params["replacement"])

        if self._llm is None:
            return ToolResult(success=False, error="LLM 客户端未配置，无法修改代码")

        instructions = params["instructions"]

        content = file_path.read_text(encoding="utf-8", errors="replace")

        system_prompt = (
            "你是一个代码修改助手。请根据用户的修改指令修改以下代码。"
            "只输出修改后的完整代码，不要添加解释。"
        )

        user_msg = f"修改指令: {instructions}\n\n当前代码:\n{content}"

        modified_code = await self._llm.chat(
            system_prompt=system_prompt,
            user_messages=[user_msg],
        )

        return ToolResult(
            success=True,
            output=modified_code,
            side_effects=[f"code_modified:{file_path}"],
        )

    @staticmethod
    def _get_structure(content: str) -> list[dict[str, Any]]:
        """用途: 提取代码顶层结构（类、函数、变量定义）

        入参:
            content (str): 代码文本

        返回:
            list[dict[str, Any]]: 结构列表，每项包含 type 和 name
        """
        structure = []
        for line in content.splitlines():
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(stripped)
            if indent == 0:
                if stripped.startswith("def "):
                    structure.append({"type": "function", "line": stripped[:80]})
                elif stripped.startswith("class "):
                    structure.append({"type": "class", "line": stripped[:80]})
                elif stripped.startswith(("import ", "from ")):
                    structure.append({"type": "import", "line": stripped[:80]})
                elif "=" in stripped and not stripped.startswith(("if", "for", "while")):
                    structure.append({"type": "variable", "line": stripped[:80]})
        return structure

    @staticmethod
    def _get_imports(content: str) -> list[str]:
        """用途: 提取所有 import 语句

        入参:
            content (str): 代码文本

        返回:
            list[str]: import 语句列表
        """
        imports = []
        for line in content.splitlines():
            stripped = line.lstrip()
            if stripped.startswith(("import ", "from ")):
                imports.append(stripped)
        return imports

    @staticmethod
    def _get_functions(content: str) -> list[dict[str, Any]]:
        """用途: 提取所有函数定义

        入参:
            content (str): 代码文本

        返回:
            list[dict[str, Any]]: 函数列表，每项包含 name 和 signature
        """
        functions = []
        import re
        pattern = re.compile(r"def\s+(\w+)\s*\(([^)]*)\)")
        for match in pattern.finditer(content):
            functions.append({
                "name": match.group(1),
                "params": match.group(2),
            })
        return functions

    @staticmethod
    def _get_classes(content: str) -> list[dict[str, Any]]:
        """用途: 提取所有类定义

        入参:
            content (str): 代码文本

        返回:
            list[dict[str, Any]]: 类列表，每项包含 name 和 bases
        """
        classes = []
        import re
        pattern = re.compile(r"class\s+(\w+)(?:\(([^)]*)\))?\s*:")
        for match in pattern.finditer(content):
            classes.append({
                "name": match.group(1),
                "bases": match.group(2) or None,
            })
        return classes
