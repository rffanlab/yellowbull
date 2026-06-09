"""经验数据模型

记录任务执行后的经验教训，用于后续检索复用。
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Experience(BaseModel):
    """经验记录模型"""

    id: str = Field(description="经验唯一标识")
    task_summary: str = Field(description="任务摘要")
    task_category: str = Field(description="任务分类")
    outcome: str = Field(description="执行结果: success / partial / failed")
    score: float = Field(description="综合评分 -1.0~1.0")
    lessons_learned: str = Field(default="", description="经验教训")
    tool_chain: list[str] = Field(default_factory=list, description="使用的工具链")
    steps_count: int = Field(default=0, description="总步骤数")
    success_rate: float = Field(default=0.0, description="成功率")
    retry_count: int = Field(default=0, description="总重试次数")
    duration_seconds: int = Field(default=0, description="耗时秒数")
    is_permanent: bool = Field(default=False, description="是否为永久经验")
    generality: float = Field(default=0.5, description="通用性评分 0.0~1.0")
    project_name: str | None = Field(default=None, description="关联项目名称")
    keywords: list[str] = Field(default_factory=list, description="关键词列表")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
