"""Shell 命令执行工具

支持执行 shell 命令，包含危险命令检测、超时控制和输出截断。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from yellowbull.tools.base import SideEffectType, Tool, ToolResult

# 危险命令模式（正则）
_DANGEROUS_PATTERNS = [
    r"\brm\s+-[rRfF]",           # rm -rf / -rf
    r"\bformat\b",               # format 磁盘
    r"\bmkfs\b",                # mkfs 格式化
    r"\bdd\s+if=",              # dd 写入设备
    r":\(\)\{\s*:\|\:&\}\s*;",   # bash fork bomb
    r"\bchmod\s+[0-7]*[7-9]",   # 危险权限
    r"\bchown\s+root",          # 改为 root 所有权
    r"\bshutdown\b",            # 关机
    r"\breboot\b",              # 重启
]

_OUTPUT_MAX_LENGTH = 8192


class ShellTool(Tool):
    """Shell 命令执行工具"""

    def __init__(self, safe_mode: bool = True) -> None:
        """用途: 初始化 Shell 工具

        入参:
            safe_mode (bool): 是否启用安全模式（拦截危险命令）

        返回: 无
        """
        self._safe_mode = safe_mode
        super().__init__(
            name="shell",
            description="Shell 命令执行工具：支持执行系统命令，含安全检测和超时控制",
            side_effects=[SideEffectType.CONFIG_CHANGE],
            is_safe=False,
        )

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """用途: 执行 shell 命令

        入参:
            params (dict[str, Any]): 必须包含 command 字段，可选 timeout 字段（默认 120 秒）

        返回:
            ToolResult: 成功时 output 为命令输出，失败时 error 为错误信息
        """
        if not self.validate_params(params):
            return ToolResult(success=False, error="参数校验失败：缺少 command")

        command = params["command"]
        timeout = params.get("timeout", 120)

        # 安全模式：检测危险命令
        if self._safe_mode and self._is_dangerous(command):
            return ToolResult(
                success=False,
                error=f"安全模式拦截：命令包含危险操作: {command}",
            )

        try:
            stdout, stderr, returncode = await self._run_command(command, timeout)
            output_parts = []
            if stdout:
                output_parts.append(f"stdout:\n{stdout}")
            if stderr:
                output_parts.append(f"stderr:\n{stderr}")

            output = "\n".join(output_parts) if output_parts else "(无输出)"
            output = self._truncate_output(output)

            side_effects = []
            if self._has_side_effects(command):
                side_effects.append(f"shell_command:{command}")

            return ToolResult(
                success=returncode == 0,
                output=output,
                error=f"命令退出码: {returncode}" if returncode != 0 else None,
                side_effects=side_effects,
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"命令执行超时（>{timeout}秒）")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def validate_params(self, params: dict[str, Any]) -> bool:
        """用途: 校验参数是否包含 command 字段

        入参:
            params (dict[str, Any]): 待校验的参数

        返回:
            bool: 包含 command 字段返回 True
        """
        return "command" in params and isinstance(params["command"], str)

    async def _run_command(self, command: str, timeout: int) -> tuple[str, str, int]:
        """用途: 异步执行 shell 命令

        入参:
            command (str): 要执行的命令
            timeout (int): 超时秒数

        返回:
            tuple[str, str, int]: (stdout, stderr, returncode)
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            raise

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return stdout, stderr, process.returncode or 0

    def _is_dangerous(self, command: str) -> bool:
        """用途: 检测命令是否为危险操作

        入参:
            command (str): 待检测的命令

        返回:
            bool: 危险返回 True
        """
        for pattern in _DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return True
        return False

    def _has_side_effects(self, command: str) -> bool:
        """用途: 判断命令是否可能产生副作用

        入参:
            command (str): 待判断的命令

        返回:
            bool: 可能产生副作用返回 True
        """
        side_effect_keywords = [
            "install", "pip", "apt", "yum", "brew",
            "mkdir", "touch", "cp", "mv", "ln",
            "git", "npm", "cargo", "go",
        ]
        return any(kw in command.lower() for kw in side_effect_keywords)

    @staticmethod
    def _truncate_output(text: str) -> str:
        """用途: 截断过长的输出

        入参:
            text (str): 原始输出文本

        返回:
            str: 截断后的文本（超过 8192 字符时截断并附加提示）
        """
        if len(text) <= _OUTPUT_MAX_LENGTH:
            return text
        return (
            text[:_OUTPUT_MAX_LENGTH]
            + f"\n\n... [输出已截断，总长度 {len(text)} 字符，仅显示前 {_OUTPUT_MAX_LENGTH} 字符]"
        )
