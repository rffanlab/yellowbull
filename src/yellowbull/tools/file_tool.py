"""文件操作工具

提供文件的读取、写入、搜索和目录列出功能。
"""

from __future__ import annotations

import glob
import os
from pathlib import Path
from typing import Any

from yellowbull.tools.base import SideEffectType, Tool, ToolResult


class FileTool(Tool):
    """文件操作工具"""

    def __init__(self) -> None:
        """用途: 初始化文件工具实例

        入参: 无
        返回: 无
        """
        super().__init__(
            name="file",
            description="文件操作工具：支持读取、写入、搜索文件和列出目录",
            side_effects=[SideEffectType.FILE_WRITE, SideEffectType.FILE_DELETE],
            is_safe=False,
        )

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """用途: 根据 action 参数分发到对应的文件操作

        入参:
            params (dict[str, Any]): 必须包含 action 字段，可选值:
                - read: 需 path
                - write: 需 path, content
                - search: 需 pattern, directory
                - list: 需 path

        返回:
            ToolResult: 执行结果
        """
        if not self.validate_params(params):
            return ToolResult(success=False, error="参数校验失败")

        action = params.get("action", "").lower()

        try:
            if action == "read":
                return await self._read_file(params)
            elif action == "write":
                return await self._write_file(params)
            elif action == "search":
                return await self._search_files(params)
            elif action == "list":
                return await self._list_directory(params)
            else:
                return ToolResult(success=False, error=f"未知的文件操作: {action}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def validate_params(self, params: dict[str, Any]) -> bool:
        """用途: 校验文件操作参数是否包含必需的 action 字段

        入参:
            params (dict[str, Any]): 待校验的参数

        返回:
            bool: 包含 action 字段返回 True
        """
        return "action" in params

    async def _read_file(self, params: dict[str, Any]) -> ToolResult:
        """用途: 读取文件内容

        入参:
            params (dict[str, Any]): 需包含 path 字段

        返回:
            ToolResult: 成功时 output 为文件内容
        """
        file_path = Path(params["path"])
        if not file_path.exists():
            return ToolResult(success=False, error=f"文件不存在: {file_path}")
        if not file_path.is_file():
            return ToolResult(success=False, error=f"路径不是文件: {file_path}")

        content = file_path.read_text(encoding="utf-8", errors="replace")
        return ToolResult(success=True, output=content)

    async def _write_file(self, params: dict[str, Any]) -> ToolResult:
        """用途: 写入文件内容，自动创建父目录

        入参:
            params (dict[str, Any]): 需包含 path 和 content 字段

        返回:
            ToolResult: 成功时 side_effects 包含写入记录
        """
        file_path = Path(params["path"])
        content = params["content"]

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        return ToolResult(
            success=True,
            output=f"文件已写入: {file_path}",
            side_effects=[f"file_write:{file_path}"],
        )

    async def _search_files(self, params: dict[str, Any]) -> ToolResult:
        """用途: 使用 glob 模式搜索文件

        入参:
            params (dict[str, Any]): 需包含 pattern 和 directory 字段

        返回:
            ToolResult: 成功时 output 为匹配文件路径列表
        """
        pattern = params["pattern"]
        directory = params.get("directory", ".")
        search_path = os.path.join(directory, pattern)

        matches = glob.glob(search_path, recursive=True)
        return ToolResult(success=True, output=matches)

    async def _list_directory(self, params: dict[str, Any]) -> ToolResult:
        """用途: 列出目录下的文件和子目录

        入参:
            params (dict[str, Any]): 需包含 path 字段

        返回:
            ToolResult: 成功时 output 为目录条目列表
        """
        dir_path = Path(params["path"])
        if not dir_path.exists():
            return ToolResult(success=False, error=f"目录不存在: {dir_path}")
        if not dir_path.is_dir():
            return ToolResult(success=False, error=f"路径不是目录: {dir_path}")

        entries = []
        for item in dir_path.iterdir():
            entries.append({
                "name": item.name,
                "is_dir": item.is_dir(),
                "is_file": item.is_file(),
                "size": item.stat().st_size if item.is_file() else None,
            })

        return ToolResult(success=True, output=entries)
