"""子任务数据模型

当主任务遇到障碍时，可拆分为子任务递归执行。
"""

from uuid import uuid4

from pydantic import BaseModel, Field

from yellowbull.models.step import Step
from yellowbull.models.task import TaskStatus


class SubTask(BaseModel):
    """子任务模型"""

    id: str = Field(default_factory=lambda: str(uuid4()), description="子任务唯一标识")
    parent_task_id: str = Field(description="父任务 ID")
    parent_step_id: str = Field(description="触发子任务的步骤 ID")
    goal: str = Field(description="子任务目标")
    obstacle_description: str = Field(description="遇到的障碍描述")
    steps: list[Step] = Field(description="子任务步骤列表")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="子任务状态")
    context_inherit: bool = Field(default=True, description="是否继承父任务上下文")
    max_steps: int = Field(default=3, description="子任务最大步骤数")
