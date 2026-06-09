"""Step 数据模型

定义执行步骤及其状态枚举，支持控制流（分支、循环）。
"""

from enum import Enum

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    """步骤状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class Step(BaseModel):
    """执行步骤模型"""

    step_id: str = Field(description="步骤唯一标识")
    description: str = Field(description="步骤描述")
    tool_hint: str = Field(description="工具类型提示: file | shell | code | search")
    depends_on: list[str] = Field(default_factory=list, description="依赖的前置步骤 ID 列表")
    is_critical: bool = Field(default=False, description="是否为关键步骤（失败则终止任务）")
    is_branch_point: bool = Field(default=False, description="是否为分支点")
    is_loop: bool = Field(default=False, description="是否为循环步骤")
    branch_condition: str | None = Field(default=None, description="分支条件表达式")
    true_next: list[str] = Field(default_factory=list, description="条件为真时的下一步 ID 列表")
    false_next: list[str] = Field(default_factory=list, description="条件为假时的下一步 ID 列表")
    loop_input_step: str | None = Field(default=None, description="循环输入步骤 ID")
    loop_item_variable: str | None = Field(default=None, description="循环项变量名")
    expected_output: str = Field(default="", description="期望输出描述")
    output_format: str = Field(default="text", description="输出格式: text / json / code")
    input_from: list[str] = Field(default_factory=list, description="输入来源步骤 ID 列表")
    input_format: str | None = Field(default=None, description="输入格式要求")
    status: StepStatus = Field(default=StepStatus.PENDING, description="当前步骤状态")
