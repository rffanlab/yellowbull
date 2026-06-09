"""工具系统基类

定义工具的抽象基类、执行结果模型和工具注册表。
所有具体工具都应继承 Tool 基类并实现 execute() 方法。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SideEffectType(str, Enum):
    """副作用类型枚举"""

    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    CONFIG_CHANGE = "config_change"
    DEPENDENCY_INSTALL = "dependency_install"
    NETWORK_REQUEST = "network_request"


class ToolResult(BaseModel):
    """工具执行结果"""

    success: bool = Field(description="是否执行成功")
    output: Any = Field(default=None, description="执行输出数据")
    error: str | None = Field(default=None, description="错误信息")
    side_effects: list[str] = Field(default_factory=list, description="实际产生的副作用描述列表")


class Tool(BaseModel):
    """工具抽象基类"""

    name: str = Field(description="工具名称")
    description: str = Field(description="工具功能描述")
    side_effects: list[SideEffectType] = Field(default_factory=list, description="声明的副作用类型列表")
    is_safe: bool = Field(default=True, description="是否安全（无需用户确认即可执行）")

    model_config = {"arbitrary_types_allowed": True}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """用途: 执行工具操作，返回执行结果

        入参:
            params (dict[str, Any]): 执行参数字典

        返回:
            ToolResult: 包含成功状态、输出数据、错误信息和副作用的执行结果

        异常:
            NotImplementedError: 子类必须重写此方法
        """
        raise NotImplementedError("子类必须实现 execute() 方法")

    def validate_params(self, params: dict[str, Any]) -> bool:
        """用途: 校验执行参数是否合法

        入参:
            params (dict[str, Any]): 待校验的参数字典

        返回:
            bool: 参数合法返回 True，否则返回 False
        """
        return True


class ToolRegistry:
    """工具注册表（类级别单例存储）"""

    _tools: dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool) -> None:
        """用途: 注册工具到全局注册表

        入参:
            tool (Tool): 待注册的工具实例

        返回: 无
        """
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> Tool | None:
        """用途: 按名称获取已注册的工具

        入参:
            name (str): 工具名称

        返回:
            Tool | None: 找到返回工具实例，未找到返回 None
        """
        return cls._tools.get(name)

    @classmethod
    def list_all(cls) -> list[Tool]:
        """用途: 获取所有已注册的工具列表

        入参: 无
        返回:
            list[Tool]: 所有已注册工具的列表
        """
        return list(cls._tools.values())

    @classmethod
    def match_by_hint(cls, hint: str) -> list[Tool]:
        """用途: 根据 tool_hint 关键字匹配工具列表

        入参:
            hint (str): 工具类型提示（如 file, shell, code, search）

        返回:
            list[Tool]: 名称或描述中包含 hint 的工具列表
        """
        hint_lower = hint.lower()
        return [
            tool for tool in cls._tools.values()
            if hint_lower in tool.name.lower() or hint_lower in tool.description.lower()
        ]
