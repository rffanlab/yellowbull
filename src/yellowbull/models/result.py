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


# ── Aggregation models ─────────────────────────────────────

class TerminationReason(str, Enum):
    """异常终止原因枚举"""

    NORMAL = "normal"
    USER_CANCEL = "user_cancel"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    USER_MODIFIED_GOAL = "user_modified_goal"
    SYSTEM_ERROR = "system_error"


class SideEffect(BaseModel):
    """副作用记录"""

    type: str = Field(description="副作用类型: FileWrite / FileDelete / ConfigChange / DependencyInstall")
    description: str = Field(default="", description="副作用描述")
    reversible: bool = Field(default=True, description="是否可逆")


class StepDetail(BaseModel):
    """步骤详细信息"""

    step_id: str = Field(description="步骤 ID")
    description: str = Field(default="", description="步骤描述")
    status: StepStatus = Field(description="执行状态")
    output_summary: str = Field(default="", description="执行结果摘要")
    duration_seconds: float = Field(default=0, description="耗时秒数")
    error: str | None = Field(default=None, description="失败原因")
    retry_count: int = Field(default=0, description="重试次数")
    is_critical: bool = Field(default=False, description="是否为关键步骤")


class SubTaskRecord(BaseModel):
    """子任务执行记录"""

    subtask_id: str = Field(description="子任务 ID")
    parent_step_id: str = Field(description="触发子任务的步骤 ID")
    obstacle_description: str = Field(default="", description="障碍描述")
    status: str = Field(default="", description="子任务状态")
    step_results: list[StepDetail] = Field(default_factory=list, description="子任务步骤详情")


class UserInteraction(BaseModel):
    """用户交互记录"""

    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    type: str = Field(description="交互类型: confirmation / feedback / clarification")
    content: str = Field(default="", description="交互内容")


class ExecutionSummary(BaseModel):
    """执行数据汇总"""

    task_id: str = Field(description="任务 ID")
    goal: str = Field(default="", description="任务目标")
    success_criteria: list[str] = Field(default_factory=list, description="成功标准")
    total_steps: int = Field(default=0, description="总步骤数")
    done_steps: int = Field(default=0, description="完成步骤数")
    failed_steps: int = Field(default=0, description="失败步骤数")
    skipped_steps: int = Field(default=0, description="跳过步骤数")
    step_details: list[StepDetail] = Field(default_factory=list, description="步骤详情列表")
    subtask_records: list[SubTaskRecord] = Field(default_factory=list, description="子任务记录")
    termination_reason: str = Field(default="", description="终止原因")
    total_duration_seconds: float = Field(default=0, description="总耗时秒数")
    steps_consumed: int = Field(default=0, description="消耗步骤预算")
    user_interactions: list[UserInteraction] = Field(default_factory=list, description="用户交互记录")
    side_effects: list[SideEffect] = Field(default_factory=list, description="副作用列表")


class MechanicalResult(BaseModel):
    """机械统计结果"""

    total_steps: int = Field(default=0)
    done_steps: int = Field(default=0)
    failed_steps: int = Field(default=0)
    skipped_steps: int = Field(default=0)
    critical_failed: bool = Field(default=False, description="有关键步骤失败")
    completion_rate: float = Field(default=0.0, description="完成率 0.0~1.0")


class RuleResult(BaseModel):
    """规则判定结果"""

    conclusion: TaskConclusion = Field(description="结论")
    achievement_score: float = Field(default=0.0, description="达成度评分")
    reason: str = Field(default="", description="判定原因")


class EvaluationResult(BaseModel):
    """评估结果"""

    conclusion: TaskConclusion = Field(description="最终结论")
    achievement_score: float = Field(default=0.0, description="达成度评分 0.0~1.0")
    failure_analysis: str | None = Field(default=None, description="失败原因分析")
    side_effects: list[str] = Field(default_factory=list, description="副作用说明")
    suggestions: list[str] = Field(default_factory=list, description="后续建议")
    report_level: int = Field(default=2, description="报告级别 1=简洁 2=标准 3=详细 4=调试")


class ConsistencyReport(BaseModel):
    """数据一致性检查报告"""

    is_consistent: bool = Field(default=True, description="是否一致")
    warnings: list[str] = Field(default_factory=list, description="警告列表")
    resolved_issues: list[str] = Field(default_factory=list, description="已解决的问题")


class LoopSummary(BaseModel):
    """循环结果汇总"""

    total_iterations: int = Field(default=0, description="总迭代次数")
    success_count: int = Field(default=0, description="成功次数")
    failure_count: int = Field(default=0, description="失败次数")
    head_results: list[StepResult] = Field(default_factory=list, description="前 N 条结果")
    tail_results: list[StepResult] = Field(default_factory=list, description="后 N 条结果")
    statistics: dict = Field(default_factory=dict, description="统计信息")


class UserFeedback(BaseModel):
    """用户反馈"""

    task_id: str = Field(description="任务 ID")
    satisfaction: str = Field(description="满意度: satisfied / neutral / dissatisfied")
    comment: str | None = Field(default=None, description="用户评论")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class RetryOption(BaseModel):
    """重试选项"""

    mode: str = Field(description="重试模式: full / partial / fix / abandon")
    description: str = Field(default="", description="选项描述")


class RetryMode(str, Enum):
    """重试模式枚举"""

    FULL = "full"
    PARTIAL = "partial"
    FIX = "fix"
    ABANDON = "abandon"


class AggregationResult(BaseModel):
    """结果汇总输出"""

    report: str = Field(default="", description="生成的报告文本")
    evaluation: EvaluationResult | None = Field(default=None, description="评估结果")
    feedback: UserFeedback | None = Field(default=None, description="用户反馈")
    experience_recorded: bool = Field(default=False, description="经验是否已记录")


class StepSummary(BaseModel):
    """步骤摘要（用于持久化）"""

    step_id: str = Field(description="步骤 ID")
    status: str = Field(description="执行状态")
    duration_seconds: float = Field(default=0, description="耗时秒数")
