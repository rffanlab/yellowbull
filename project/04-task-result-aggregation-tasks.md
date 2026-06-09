# 任务结果汇总 — 代码开发任务

> 对应设计文档：04-task-result-aggregation.md
> 模块职责：收集执行数据、评估任务达成度、生成用户报告、记录经验、等待用户反馈

---

## 一、数据收集模块

### T04-01: 执行数据收集器

**对应设计**: 二、输入数据

**文件**: `src/yellowbull/agent/aggregator.py`

**需要实现的类**:
```python
class ExecutionDataCollector:
    """
    从执行引擎收集所有数据:
    1. Task 原始定义
    2. 步骤执行记录
    3. 子任务执行记录
    4. 执行元数据
    5. 用户交互记录
    """

    def __init__(
        self,
        task: Task,
        step_states: dict[str, StepState],
        context_store: ContextStore,
        budget_guard: BudgetGuard,
        execution_stack: ExecutionStack,
    ):
        self.task = task
        self.step_states = step_states
        self.context_store = context_store
        self.budget_guard = budget_guard
        self.execution_stack = execution_stack

    def collect(self) -> ExecutionSummary:
        """
        收集所有执行数据，生成汇总结构:
        
        返回 ExecutionSummary:
        {
            "task": Task,
            "total_steps": int,
            "done_steps": int,
            "failed_steps": int,
            "skipped_steps": int,
            "step_details": list[StepDetail],
            "subtask_records": list[SubTaskRecord],
            "termination_reason": str,
            "total_duration": float,
            "steps_consumed": int,
            "user_interactions": list[UserInteraction],
            "side_effects": list[SideEffect],
        }
        """
        ...

    def _collect_step_details(self) -> list[StepDetail]:
        """
        收集每个步骤的详细信息:
        - step_id, description, status
        - 执行结果摘要
        - 耗时
        - 失败原因
        - 重试次数
        """
        ...

    def _collect_subtask_records(self) -> list[SubTaskRecord]:
        """
        收集子任务执行记录:
        - 触发原因（障碍描述）
        - 子任务步骤及结果
        - 子任务状态
        - 嵌套关系树
        """
        ...

    def _detect_side_effects(self) -> list[SideEffect]:
        """
        检测副作用:
        - 从工具声明中收集已声明副作用
        - 工具类型: FileWrite, FileDelete, ConfigChange, DependencyInstall
        """
        ...
```

**测试点**:
- [ ] 正确统计各状态步骤数
- [ ] 步骤详情完整收集
- [ ] 子任务记录正确关联
- [ ] 副作用正确检测
- [ ] 耗时统计正确

---

## 二、结果评估模块

### T04-02: 机械统计与规则判定

**对应设计**: 三、结果评估流程（第 1 层 + 第 2 层）

**文件**: `src/yellowbull/agent/aggregator.py`

**需要实现的类**:
```python
class ResultEvaluator:
    """
    结果评估:
    第 1 层: 机械统计
    第 2 层: 规则判定
    第 3 层: LLM 综合评估
    """

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def evaluate(
        self,
        summary: ExecutionSummary,
    ) -> EvaluationResult:
        """
        三层评估流程:
        1. 机械统计 → 快速判断
        2. 规则判定 → 明确规则
        3. LLM 综合评估 → 模糊边界
        
        返回 EvaluationResult:
        {
            "conclusion": "success" | "partial_success" | "failure" | "cancelled",
            "achievement_score": float,  # 0.0 ~ 1.0
            "failure_analysis": str | None,
            "side_effects": list[str],
            "suggestions": list[str],
            "report_level": int,  # 1=简洁, 2=标准, 3=详细, 4=调试
        }
        """
        ...

    def _mechanical_check(self, summary: ExecutionSummary) -> MechanicalResult:
        """
        第 1 层: 机械统计
        - done / failed / skipped 数量
        - 关键步骤是否全部完成
        - 完成率 = done / total
        """
        ...

    def _rule_based_check(
        self,
        summary: ExecutionSummary,
        mechanical: MechanicalResult,
    ) -> RuleResult | None:
        """
        第 2 层: 规则判定
        - 关键步骤有 failed → 任务失败
        - 全部 done → 完全成功
        - 完成率 >= 80% → 良好（部分成功）
        - 完成率 < 80% → 返回 None，交给 LLM 评估
        - 用户取消 → 已取消
        """
        ...

    async def _llm_comprehensive_evaluation(
        self,
        summary: ExecutionSummary,
    ) -> EvaluationResult:
        """
        第 3 层: LLM 综合评估
        
        构建 Prompt（来自设计文档第四章）:
        【任务目标】+【成功标准】+【执行统计】
        +【关键步骤状态】+【失败步骤详情】
        +【子任务记录】+【耗时统计】+【约束违反情况】
        
        LLM 返回:
        1. 最终结论
        2. 达成度评分
        3. 未完成原因分析
        4. 副作用说明
        5. 后续建议
        """
        ...

    def _determine_report_level(
        self,
        summary: ExecutionSummary,
        conclusion: str,
    ) -> int:
        """
        确定报告详略级别:
        - 级别 1: 完全成功 + 无副作用 → 简洁
        - 级别 2: 默认 → 标准
        - 级别 3: 部分成功/失败 + 有子任务 + 有副作用 → 详细
        - 级别 4: 异常终止 → 调试
        """
        ...
```

**测试点**:
- [ ] 机械统计正确
- [ ] 关键步骤失败 → 任务失败
- [ ] 全部完成 → 完全成功
- [ ] 高完成率 → 部分成功
- [ ] 低完成率触发 LLM 评估
- [ ] LLM 评估返回完整结果
- [ ] 报告级别正确选择

---

## 三、报告生成模块

### T04-03: 报告格式化

**对应设计**: 五、报告生成

**文件**: `src/yellowbull/agent/report_generator.py`

**需要实现的类**:
```python
class ReportGenerator:
    """
    报告生成器:
    将评估结果格式化为结构化 Markdown 报告
    """

    def __init__(self, settings: ReportSettings):
        self.settings = settings

    def generate(
        self,
        summary: ExecutionSummary,
        evaluation: EvaluationResult,
    ) -> str:
        """
        生成完整报告:
        
        报告结构:
        1. 报告头部（目标 + 结论 + 耗时）
        2. 执行摘要
        3. 完成详情
        4. 问题说明
        5. 副作用说明
        6. 后续建议
        
        按 report_level 控制详略
        """
        ...

    def _generate_header(
        self,
        summary: ExecutionSummary,
        evaluation: EvaluationResult,
    ) -> str:
        """
        报告头部:
        - 任务目标
        - 最终结论（带达成度评分）
        - 总耗时
        """
        ...

    def _generate_summary(
        self,
        summary: ExecutionSummary,
        evaluation: EvaluationResult,
    ) -> str:
        """一句话执行摘要"""
        ...

    def _generate_completion_details(
        self,
        summary: ExecutionSummary,
    ) -> str:
        """
        完成详情:
        - 完成的步骤列表（简要）
        - 关键成果
        """
        ...

    def _generate_problem_section(
        self,
        summary: ExecutionSummary,
    ) -> str:
        """
        问题说明:
        - 失败的步骤及原因
        - 跳过的步骤及原因
        - 障碍排除记录
        """
        ...

    def _generate_side_effects_section(
        self,
        summary: ExecutionSummary,
    ) -> str:
        """
        副作用说明:
        - 文件变更
        - 配置修改
        - 依赖安装
        - 可逆性标注
        """
        ...

    def _generate_suggestions_section(
        self,
        evaluation: EvaluationResult,
    ) -> str:
        """后续建议"""
        ...

    def _apply_detail_level(
        self,
        sections: dict[str, str],
        level: int,
    ) -> str:
        """
        根据详略级别组装报告:
        - 级别 1: 头部 + 摘要
        - 级别 2: 头部 + 摘要 + 完成详情 + 问题说明
        - 级别 3: 全部章节 + 子任务详情
        - 级别 4: 级别 3 + 原始日志
        """
        ...
```

**测试点**:
- [ ] 报告头部格式正确
- [ ] 执行摘要简洁明了
- [ ] 完成详情正确列出
- [ ] 问题说明清晰
- [ ] 副作用正确标注
- [ ] 详略级别控制正确
- [ ] 详细部分使用折叠语法

---

### T04-04: 结果脱敏

**对应设计**: 六、边界问题 → 6.10 结果脱敏

**文件**: `src/yellowbull/agent/report_generator.py`

**需要实现的方法**:
```python
class ReportGenerator:
    def _sanitize(self, text: str) -> str:
        """
        结果脱敏:
        - 匹配常见敏感模式
        - password=, token:, api_key, secret
        - 正则: (?i)(password|token|secret|key|api_key)\\s*[=:]\\s*\\S+
        - 脱敏后显示: [REDACTED]
        """
        ...

    def _sanitize_step_results(
        self,
        step_details: list[StepDetail],
    ) -> list[StepDetail]:
        """对步骤结果做脱敏处理"""
        ...
```

**测试点**:
- [ ] 密码/密钥正确脱敏
- [ ] token 正确脱敏
- [ ] 正常文本不受影响
- [ ] 脱敏标记正确显示

---

## 四、用户反馈模块

### T04-05: 反馈收集与处理

**对应设计**: 六、边界问题 → 6.4 用户不满意、6.12 用户反馈收集

**文件**: `src/yellowbull/agent/feedback.py`

**需要实现的类**:
```python
class FeedbackCollector:
    """用户反馈收集与处理"""

    def __init__(
        self,
        llm_client: LLMClient,
        experience_repo: ExperienceRepo | None = None,
    ):
        self.llm_client = llm_client
        self.experience_repo = experience_repo

    async def collect_feedback(
        self,
        task_id: str,
        report: str,
    ) -> UserFeedback:
        """
        报告输出后主动询问用户满意度:
        - 满意 / 一般 / 不满意
        - 用户未响应 → 默认"一般"
        
        返回 UserFeedback:
        {
            "task_id": str,
            "satisfaction": "satisfied" | "neutral" | "dissatisfied",
            "comment": str | None,
            "timestamp": str,
        }
        """
        ...

    async def handle_dissatisfaction(
        self,
        task: Task,
        evaluation: EvaluationResult,
        user_comment: str | None,
    ) -> RetryOption:
        """
        用户不满意时给出选项:
        a. 重新执行（完全重新拆解）
        b. 补充执行（只做缺失部分）
        c. 修正结果（手动修复）
        d. 放弃
        """
        ...

    async def handle_disagreement(
        self,
        task: Task,
        evaluation: EvaluationResult,
        user_comment: str | None,
    ) -> EvaluationResult:
        """
        任务标记失败，但用户说"其实已经够了":
        1. 更新达成度评分
        2. 将此次经验标记为"可接受的部分成功"
        """
        ...

    def _adjust_experience_score(
        self,
        task_id: str,
        feedback: UserFeedback,
    ) -> float:
        """
        根据用户反馈调整经验评分:
        - 用户满意 → +0.2 加成
        - 用户不满意 → -0.2 惩罚
        - 用户未响应 → 不变
        """
        ...
```

**测试点**:
- [ ] 反馈正确收集
- [ ] 不满意时给出正确选项
- [ ] 用户认可部分成功时更新评分
- [ ] 经验评分正确调整
- [ ] 超时未响应默认"一般"

---

## 五、重试模块

### T04-06: 失败重试

**对应设计**: 九、重试机制

**文件**: `src/yellowbull/agent/retry.py`

**需要实现的类**:
```python
class RetryManager:
    """任务失败后重试管理"""

    def __init__(
        self,
        task_breakdown: TaskBreakdown,
        engine: TaskEngine,
        experience_repo: ExperienceRepo | None = None,
    ):
        self.task_breakdown = task_breakdown
        self.engine = engine
        self.experience_repo = experience_repo

    async def retry(
        self,
        original_task: Task,
        original_summary: ExecutionSummary,
        mode: RetryMode | None = None,
    ) -> TaskResult:
        """
        两种重试方式:
        
        方式 A — 完全重新拆解:
        - 从头开始
        - 根据失败经验调整拆解策略
        
        方式 B — 仅重试失败步骤:
        - 保留已完成步骤
        - 只重新执行 failed 步骤
        
        自动选择逻辑:
        - 失败步骤 < 30% → 方式 B
        - 失败步骤 >= 30% → 方式 A
        """
        ...

    async def _retry_full(
        self,
        task: Task,
        failure_reason: str,
    ) -> TaskResult:
        """完全重新拆解并执行"""
        ...

    async def _retry_failed_steps(
        self,
        task: Task,
        summary: ExecutionSummary,
    ) -> TaskResult:
        """仅重试失败步骤"""
        ...

    def _apply_failure_experience(
        self,
        failure_reasons: list[str],
    ) -> dict:
        """
        利用失败经验调整重试策略:
        - 调整工具选择
        - 调整步骤顺序
        - 预判可能障碍
        """
        ...
```

**测试点**:
- [ ] 失败率低自动选择部分重试
- [ ] 失败率高自动选择完全重试
- [ ] 用户明确指定时按指定执行
- [ ] 失败经验正确应用

---

## 六、结果持久化模块

### T04-07: 结果存储

**对应设计**: 八、结果持久化

**文件**: `src/yellowbull/agent/result_repo.py`

**需要实现的类**:
```python
class ResultRepository:
    """
    任务结果持久化:
    1. 任务执行记录（必存）
    2. 详细执行日志（可选）
    3. 经验数据（必存）
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def save_task_result(
        self,
        task_id: str,
        goal: str,
        conclusion: str,
        achievement_score: float,
        duration: float,
        step_summary: list[StepSummary],
    ) -> str:
        """保存任务执行摘要（必存）"""
        ...

    async def save_detailed_log(
        self,
        task_id: str,
        step_details: list[StepDetail],
        user_interactions: list[UserInteraction],
        enabled: bool,
    ) -> None:
        """保存详细执行日志（可选，用户配置）"""
        ...

    async def save_experience_data(
        self,
        task_type: str,
        tool_chain: list[str],
        score: float,
        obstacles: list[str],
    ) -> None:
        """保存经验数据（必存，永久保留）"""
        ...

    async def get_task_result(self, task_id: str) -> TaskResult | None:
        """按 ID 查询历史任务结果"""
        ...

    async def list_task_results(
        self,
        task_type: str | None = None,
        limit: int = 20,
    ) -> list[TaskResult]:
        """列出历史任务结果（MVP 仅当前任务）"""
        ...
```

**测试点**:
- [ ] 任务摘要正确保存
- [ ] 详细日志可选保存
- [ ] 经验数据正确保存
- [ ] 按 ID 查询正确返回
- [ ] 历史列表正确返回

---

## 七、经验提炼模块

### T04-08: 经验 → 技能演化

**对应设计**: 七、经验记录 → 7.2 经验 → 技能演化

**文件**: `src/yellowbull/agent/skill_evolver.py`

**需要实现的类**:
```python
class SkillEvolver:
    """
    经验积累到阈值自动提炼为技能:
    1. 同类经验 N 次（默认 5 次）
    2. 成功率稳定 > 0.7
    3. 工具链模式一致
    4. LLM 提炼技能
    5. 技能入库
    """

    def __init__(
        self,
        experience_repo: ExperienceRepo,
        skill_repo: SkillRepo,
        llm_client: LLMClient,
        threshold: int = 5,
    ):
        self.experience_repo = experience_repo
        self.skill_repo = skill_repo
        self.llm_client = llm_client
        self.threshold = threshold

    async def check_and_evolve(self, new_experience: Experience) -> bool:
        """
        检查是否满足技能提炼条件:
        1. 查找同类经验
        2. 统计数量、成功率、工具链一致性
        3. 满足条件 → LLM 提炼技能
        4. 技能入库
        
        返回: 是否成功提炼新技能
        """
        ...

    async def _find_similar_experiences(
        self,
        task_type: str,
    ) -> list[Experience]:
        """查找同类经验"""
        ...

    def _check_tool_chain_consistency(
        self,
        experiences: list[Experience],
    ) -> bool:
        """检查工具链模式是否一致"""
        ...

    async def _extract_skill_with_llm(
        self,
        experiences: list[Experience],
    ) -> Skill:
        """
        LLM 提炼技能:
        
        Prompt:
        "以下 N 次任务经验具有相似模式:
         - 工具链一致: ...
         - 成功率: 平均 ...
         - 常见障碍: ...
         请提炼为可复用技能:
         - 技能名称
         - 适用场景
         - 标准步骤
         - 预检清单
         - 常见障碍及排除方案"
        """
        ...

    async def _degrade_skill(self, skill_id: str, failure_count: int):
        """
        技能退化:
        - 连续失败 → 权重下降
        - 降至阈值以下 → 降级为普通经验
        """
        ...
```

**测试点**:
- [ ] 同类经验正确统计
- [ ] 工具链一致性正确判断
- [ ] LLM 提炼技能正确
- [ ] 技能正确入库
- [ ] 技能退化机制正确

---

## 八、主汇总入口

### T04-09: 结果汇总主流程

**对应设计**: 一、模块定位、三、结果评估流程

**文件**: `src/yellowbull/agent/aggregator.py`

**需要实现的类**:
```python
class ResultAggregator:
    """
    结果汇总主入口:
    1. 收集所有执行数据
    2. 评估任务达成度
    3. 生成用户报告
    4. 记录经验
    5. 等待用户反馈
    """

    def __init__(
        self,
        data_collector: ExecutionDataCollector,
        evaluator: ResultEvaluator,
        report_generator: ReportGenerator,
        feedback_collector: FeedbackCollector,
        result_repo: ResultRepository,
        experience_recorder: ExperienceRecorder,
    ):
        ...

    async def aggregate(
        self,
        task: Task,
        step_states: dict[str, StepState],
        context_store: ContextStore,
        budget_guard: BudgetGuard,
        execution_stack: ExecutionStack,
    ) -> AggregationResult:
        """
        完整汇总流程:
        1. 收集数据
        2. 评估达成度
        3. 生成报告
        4. 记录经验
        5. 持久化结果
        6. 收集用户反馈
        
        返回 AggregationResult:
        {
            "report": str,
            "evaluation": EvaluationResult,
            "feedback": UserFeedback | None,
            "experience_recorded": bool,
        }
        """
        ...
```

**测试点**:
- [ ] 完整流程正确执行
- [ ] 报告生成正确
- [ ] 经验记录正确
- [ ] 结果持久化正确
- [ ] 反馈收集正确
- [ ] 报告生成本身失败时降级

---

### T04-10: 异常终止处理

**对应设计**: 六、边界问题 → 6.1 任务异常终止

**文件**: `src/yellowbull/agent/aggregator.py`

**需要实现的方法**:
```python
class ResultAggregator:
    async def handle_abnormal_termination(
        self,
        task: Task,
        termination_reason: TerminationReason,
        step_states: dict[str, StepState],
        context_store: ContextStore,
    ) -> TaskResult:
        """
        处理各种异常终止场景:
        1. 用户中途取消 → 结论"已取消"，列出已完成步骤
        2. 超时终止 → 判断已完成部分是否"够用"
        3. 预算耗尽 → 同超时终止
        4. 用户中途修改目标 → 原任务标记 interrupted
        """
        ...

    def _judge_partial_success(
        self,
        completed_steps: list[Step],
        total_steps: int,
        success_criteria: list[str],
    ) -> tuple[bool, float]:
        """
        判断部分完成是否"够用":
        - 关键步骤完成率
        - 成功标准达成度
        - 返回 (是否部分成功, 达成度)
        """
        ...

class TerminationReason(str, Enum):
    USER_CANCEL = "user_cancel"
    TIMEOUT = "timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    USER_MODIFIED_GOAL = "user_modified_goal"
    SYSTEM_ERROR = "system_error"
```

**测试点**:
- [ ] 用户取消正确标记
- [ ] 超时终止正确判断部分成功
- [ ] 预算耗尽正确处理
- [ ] 用户修改目标正确标记 interrupted

---

### T04-11: 数据一致性保障

**对应设计**: 六、边界问题 → 6.6 数据一致性

**文件**: `src/yellowbull/agent/aggregator.py`

**需要实现的方法**:
```python
class ResultAggregator:
    def _ensure_data_consistency(
        self,
        step_states: dict[str, StepState],
        context_store: ContextStore,
    ) -> ConsistencyReport:
        """
        数据一致性检查:
        1. step_status 与 context_store 一致性
           - step 标记 done 但 context_store 无结果 → "静默成功"
           - step 标记 failed 但有部分结果 → 保留部分结果
        2. 子任务写入父任务 context_store → 检测并记录警告
        3. 不一致时按最保守方式处理
        """
        ...

    def _handle_missing_context(
        self,
        step: Step,
        step_state: StepState,
    ) -> StepResult:
        """
        done 但 context_store 无结果:
        - 视为"静默成功"（如删除操作）
        - 注明"执行成功，无输出"
        """
        ...

    def _handle_partial_failure(
        self,
        step: Step,
        step_state: StepState,
        context_store: ContextStore,
    ) -> StepResult:
        """
        failed 但有部分结果:
        - 保留部分结果
        - 同时展示失败原因
        """
        ...

class ConsistencyReport(BaseModel):
    is_consistent: bool
    warnings: list[str] = []
    resolved_issues: list[str] = []
```

**测试点**:
- [ ] step 与 context 不一致时正确警告
- [ ] 子任务写入父任务 context 被检测
- [ ] 静默成功正确处理
- [ ] 部分失败保留结果

---

### T04-12: 大数据量处理（MVP 可选）

**对应设计**: 六、边界问题 → 6.7 结果数据量过大

**文件**: `src/yellowbull/agent/aggregator.py`

**需要实现的方法**:
```python
class ResultAggregator:
    def _truncate_large_results(
        self,
        step_results: list[StepResult],
        max_report_length: int = 4096,
    ) -> list[StepResult]:
        """
        大数据量处理:
        1. 循环 100 次迭代 → 只展示汇总 + 前 N + 后 N
        2. 报告超过 4096 字 → 自动折叠详细部分
        3. 保留摘要 + 统计
        """
        ...

    def _summarize_loop_results(
        self,
        loop_results: list[StepResult],
        head_count: int = 5,
        tail_count: int = 5,
    ) -> LoopSummary:
        """
        循环结果汇总:
        - 不逐条列出
        - 汇总统计 + 前 N 条 + 后 N 条
        - 详细结果可展开
        """
        ...

class LoopSummary(BaseModel):
    total_iterations: int
    success_count: int
    failure_count: int
    head_results: list[StepResult]
    tail_results: list[StepResult]
    statistics: dict[str, any]
```

**测试点**:
- [ ] 循环结果正确汇总
- [ ] 超长报告自动折叠
- [ ] 摘要统计正确保留

---

## 九、任务依赖顺序

```
T04-01 (数据收集)
    │
    ├─→ T04-02 (结果评估)
    │       │
    │       └─→ T04-03 (报告格式化)
    │               │
    │               └─→ T04-04 (结果脱敏)
    │                       │
    │                       └─→ T04-10 (异常终止处理)
    │                               │
    │                               └─→ T04-11 (数据一致性)
    │                                       │
    │                                       └─→ T04-12 (大数据量) [可选]
    │
    ├─→ T04-05 (用户反馈)
    │
    ├─→ T04-06 (失败重试)
    │
    ├─→ T04-07 (结果持久化)
    │
    ├─→ T04-08 (经验提炼)
    │
    └─→ T04-09 (主汇总入口)
```

---

## 十、MVP 范围

| 任务 | MVP 是否必须 | 说明 |
|------|-------------|------|
| T04-01 | ✅ 是 | 数据收集是基础 |
| T04-02 | ✅ 是 | 结果评估是核心 |
| T04-03 | ✅ 是 | 报告生成是核心 |
| T04-04 | ✅ 是 | 脱敏是安全要求 |
| T04-05 | ⏺ 可选 | MVP 可简化为固定评分 |
| T04-06 | ⏺ 可选 | MVP 可暂不实现重试 |
| T04-07 | ✅ 是 | 结果持久化是基础 |
| T04-08 | ⏺ 可选 | MVP 暂不提炼技能 |
| T04-09 | ✅ 是 | 主入口必须 |
| T04-10 | ✅ 是 | 异常终止处理 |
| T04-11 | ✅ 是 | 数据一致性保障 |
| T04-12 | ⏺ 可选 | 大数据量处理 |
