"""Task 数据模型

定义任务及其状态枚举。
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    """任务模型"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    goal: str = Field(description="任务目标描述")
    constraints: list[str] = Field(default_factory=list, description="约束条件列表")
    success_criteria: list[str] = Field(default_factory=list, description="成功标准列表")
    context_files: list[str] = Field(default_factory=list, description="上下文文件路径列表")
    confidence: float = Field(description="解析置信度 0.0~1.0")
    clarification_needed: str = Field(default="", description="需要澄清的问题")
    clarification_options: list[str] = Field(default_factory=list, description="澄清选项列表")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="当前任务状态")
