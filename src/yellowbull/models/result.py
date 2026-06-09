"""执行结果数据模型

定义步骤结果、任务结果及结论枚举。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from yellowbull.models.step import StepStatus


class TaskConclusion(str, Enum):
    """任务结论枚举"""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class StepResult(BaseModel):
    """单步执行结果"""

    step_id: str = Field(description="步骤 ID")
    status: StepStatus = Field(description="执行状态")
    output: object | None = Field(default=None, description="执行输出")
    error: str | None = Field(default=None, description="错误信息")
    retry_count: int = Field(default=0, description="重试次数")
    duration_seconds: float = Field(default=0, description="耗时秒数")
    side_effects: list[str] = Field(default_factory=list, description="产生的副作用描述列表")
    timestamp: datetime = Field(default_factory=datetime.now, description="完成时间戳")


class TaskResult(BaseModel):
    """任务执行总结果"""

    task_id: str = Field(description="任务 ID")
    conclusion: TaskConclusion = Field(description="任务结论")
    achievement_score: float = Field(description="完成度评分 0.0~1.0")
    step_results: list[StepResult] = Field(description="各步骤执行结果")
    subtask_results: list["TaskResult"] = Field(default_factory=list, description="子任务结果列表")
    total_duration_seconds: float = Field(default=0, description="总耗时秒数")
    termination_reason: str = Field(default="", description="终止原因: normal / timeout / budget_exhausted / cancelled")
    side_effects: list[str] = Field(default_factory=list, description="任务级副作用列表")
    suggestions: list[str] = Field(default_factory=list, description="改进建议列表")
