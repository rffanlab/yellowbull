# 任务执行引擎 — 代码开发任务

> 对应设计文档：03-task-execution-engine.md
> 模块职责：接收拆解后的 Step 列表，按依赖序执行每步，处理失败、分支、循环、障碍排除，最终判定任务结果。

---

## 一、核心数据模型

### T03-01: 步骤状态与上下文存储

**对应设计**: 十二、状态机设计、十三、上下文传递规则

**文件**: `src/yellowbull/agent/step_state.py`

**需要实现的类**:
```python
class StepStatus:
    """步骤状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

class StepState:
    """单步执行状态"""

    def __init__(self, step_id: str):
        self.step_id = step_id
        self.status = StepStatus.PENDING
        self.result: Any = None
        self.error: str | None = None
        self.retry_count = 0
        self.skipped_by_branch: bool = False
        self.skipped_by_dependency: bool = False

class TaskState:
    """任务级状态"""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ContextStore:
    """
    执行上下文存储:
    - 命名空间隔离: task:{task_id}:{step_id} / subtask:{subtask_id}:{step_id}
    - 子任务可读取父任务 context（只读）
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._store: dict[str, Any] = {}
        self._parent_store: ContextStore | None = None

    def set(self, step_id: str, data: Any):
        key = f"task:{self.task_id}:{step_id}"
        self._store[key] = data

    def get(self, step_id: str) -> Any | None:
        """优先本地查找，未命中则回退到父任务 context"""
        key = f"task:{self.task_id}:{step_id}"
        if key in self._store:
            return self._store[key]
        if self._parent_store:
            return self._parent_store.get(step_id)
        return None

    def set_parent(self, parent: ContextStore):
        self._parent_store = parent

    def to_dict(self) -> dict:
        return dict(self._store)
```

**测试点**:
- [ ] 步骤状态正常流转
- [ ] 上下文读写正确
- [ ] 子任务 context 可读取父任务数据
- [ ] 子任务不能修改父任务 context

---

### T03-02: 执行栈

**对应设计**: 八、执行栈设计

**文件**: `src/yellowbull/agent/execution_stack.py`

**需要实现的类**:
```python
class TaskContext:
    """被暂停的任务上下文快照"""

    def __init__(
        self,
        task_id: str,
        step_states: dict[str, StepState],
        context_store: ContextStore,
        current_step_index: int,
        paused_at: str | None = None,
    ):
        self.task_id = task_id
        self.step_states = step_states
        self.context_store = context_store
        self.current_step_index = current_step_index
        self.paused_at = paused_at  # 暂停时的步骤 ID

class ExecutionStack:
    """
    执行栈: 支持子任务压栈/恢复
    """

    def __init__(self, max_depth: int | None = None):
        self.current: Task | SubTask = None
        self.paused: list[TaskContext] = []
        self.results: dict[str, Any] = {}
        self.nesting_depth = 0

    def push(self, subtask: SubTask, parent_context: TaskContext):
        """
        压栈: 保存当前任务上下文，切换到子任务
        """
        ...

    def pop(self) -> TaskContext | None:
        """
        弹栈: 子任务完成，恢复父任务上下文
        """
        ...

    @property
    def is_nested(self) -> bool:
        return self.nesting_depth > 0

    @property
    def depth(self) -> int:
        return self.nesting_depth
```

**测试点**:
- [ ] 压栈保存上下文正确
- [ ] 弹栈恢复上下文正确
- [ ] 嵌套深度正确计数
- [ ] 空栈弹栈返回 None

---

## 二、步骤校验模块

### T03-03: 步骤预校验

**对应设计**: 二、执行流程全景（预校验阶段）

**文件**: `src/yellowbull/agent/validator.py`

**需要实现的类**:
```python
class StepValidator:
    """步骤预校验"""

    @staticmethod
    def validate_steps(steps: list[Step]) -> ValidationResult:
        """
        校验所有步骤:
        1. 拓扑排序 — 确保无循环依赖
        2. 孤立步骤检测 — 未连接任何依赖链的步骤
        3. 循环步骤 + 分支点互斥 — 不允许同时存在
        4. 嵌套循环检测 — 不允许循环嵌套循环
        
        返回 ValidationResult:
        {
            "valid": bool,
            "errors": list[str],
            "sorted_steps": list[Step],  # 拓扑排序后的步骤
        }
        """
        ...

    @staticmethod
    def _topological_sort(
        steps: list[Step],
    ) -> tuple[list[Step], list[str]]:
        """
        对步骤做拓扑排序:
        - 使用 Kahn 算法
        - 检测到环 → 返回错误
        """
        ...

    @staticmethod
    def _detect_orphan_steps(steps: list[Step]) -> list[str]:
        """
        检测孤立步骤:
        - 既没有 depends_on，也没有其他步骤 depends_on 它
        - 且不是第一步
        """
        ...

    @staticmethod
    def _check_loop_branch_conflict(steps: list[Step]) -> list[str]:
        """循环步骤不允许同时是分支点"""
        ...

    @staticmethod
    def _check_nested_loops(steps: list[Step]) -> list[str]:
        """循环步骤的 depends_on 中不能有另一个循环步骤"""
        ...
```

**测试点**:
- [ ] 合法步骤列表校验通过
- [ ] 循环依赖正确检测
- [ ] 孤立步骤正确检测
- [ ] 循环+分支互斥检测
- [ ] 嵌套循环检测
- [ ] 拓扑排序结果正确

---

## 三、步骤选择器

### T03-04: 获取下一步

**对应设计**: 七、步骤选择策略

**文件**: `src/yellowbull/agent/step_selector.py`

**需要实现的类**:
```python
class StepSelector:
    """
    从 pending 步骤中选择下一步:
    1. 过滤: pending + depends_on 满足 + 未被分支跳过
    2. 排序: 关键优先 → 读优先 → 拓扑序
    3. 返回最高优先级步骤或 None
    """

    def __init__(self, step_states: dict[str, StepState]):
        self.step_states = step_states

    def get_next(self, steps: list[Step]) -> Step | None:
        """
        选择下一步:
        1. 过滤不可执行的步骤
        2. 按优先级排序
        3. 返回最高优先级步骤
        
        返回 None 表示无可执行步骤
        """
        ...

    def _can_execute(self, step: Step) -> bool:
        """
        检查步骤是否可执行:
        - status == pending
        - depends_on 全部 done 或 skipped
        - 未被分支跳过
        """
        ...

    def _sort_by_priority(self, candidates: list[Step]) -> list[Step]:
        """
        排序规则:
        1. is_critical=True 优先
        2. 读操作优先于写操作
        3. 拓扑序靠前的优先
        """
        ...

    def _cascade_skip(self, steps: list[Step]) -> list[str]:
        """
        级联跳过: 当步骤的依赖 failed 时，
        递归将所有依赖它的步骤标记为 skipped
        
        返回: 被跳过的步骤 ID 列表
        """
        ...
```

**测试点**:
- [ ] 正确选择关键步骤
- [ ] 读操作优先于写操作
- [ ] 依赖未满足的步骤被跳过
- [ ] 级联跳过正确传播
- [ ] 无可执行步骤返回 None

---

## 四、单步执行器

### T03-05: 普通步骤执行

**对应设计**: 三、普通步骤执行

**文件**: `src/yellowbull/agent/executor.py`

**需要实现的类**:
```python
class StepExecutor:
    """单步执行器"""

    def __init__(
        self,
        context_store: ContextStore,
        tool_router: ToolRouter,
        llm_client: LLMClient,
        step_timeout: int = 120,
    ):
        self.context_store = context_store
        self.tool_router = tool_router
        self.llm_client = llm_client
        self.step_timeout = step_timeout

    async def execute(self, step: Step) -> StepResult:
        """
        执行单步:
        1. 前置检查: depends_on 全部 done/skipped
        2. 收集输入数据: 从 context_store 按 input_from 取数据
        3. 格式校验: 按 input_format 校验
        4. 工具路由: tool_hint → 匹配工具
        5. 构建执行 Prompt
        6. 调用工具执行 (timeout=120s)
        7. 结果处理: 成功存入 context_store，失败返回错误
        
        返回 StepResult:
        {
            "step_id": str,
            "success": bool,
            "result": Any,
            "error": str | None,
            "tool_used": str,
            "duration_ms": int,
        }
        """
        ...

    def _collect_inputs(self, step: Step) -> dict:
        """从 context_store 收集输入数据"""
        ...

    def _validate_input_format(
        self,
        inputs: dict,
        expected_format: str | None,
    ) -> tuple[bool, str | None]:
        """
        校验输入格式:
        - MVP 仅支持基础类型转换
        - 格式不匹配 → 尝试自动转换
        - 转换失败 → 返回错误
        """
        ...

    def _build_execution_prompt(
        self,
        step: Step,
        inputs: dict,
        tool: Tool,
    ) -> tuple[str, str]:
        """
        构建执行 Prompt:
        - step.description
        - 输入数据
        - 工具说明
        - expected_output 约束
        """
        ...

    async def _invoke_tool(
        self,
        tool: Tool,
        prompt: tuple[str, str],
        timeout: int,
    ) -> StepResult:
        """
        调用工具执行:
        - 使用 asyncio.wait_for 控制超时
        - 捕获所有异常
        """
        ...
```

**测试点**:
- [ ] 正常步骤执行成功
- [ ] 依赖失败导致步骤跳过
- [ ] 输入格式校验正确
- [ ] 工具超时正确处理
- [ ] 空结果视为失败
- [ ] 结果正确存入 context_store

---

### T03-06: 条件分支步骤执行

**对应设计**: 四、条件分支步骤执行

**文件**: `src/yellowbull/agent/executor.py`

**需要实现的方法**:
```python
class StepExecutor:
    async def execute_branch(self, step: Step) -> BranchResult:
        """
        执行条件分支步骤:
        1. 正常执行该步骤（如"检查服务状态"）
        2. LLM 评估 branch_condition
        3. 根据结果标记 true_next/false_next 为 pending/skipped
        
        返回 BranchResult:
        {
            "condition_met": bool,
            "activated_steps": list[str],
            "skipped_steps": list[str],
        }
        """
        ...

    async def _evaluate_branch_condition(
        self,
        condition: str,
        step_result: Any,
    ) -> bool:
        """
        使用 LLM 评估分支条件:
        
        Prompt:
        "以下条件是否满足？
         条件: {condition}
         依据: {step_result}
         请回答 true 或 false。"
        
        边界:
        - LLM 无法判断 → 默认 false
        - true_next/false_next 为空 → 该分支末端
        - 未声明 depends_on → 自动补全
        """
        ...
```

**测试点**:
- [ ] 条件满足时正确激活 true 分支
- [ ] 条件不满足时正确激活 false 分支
- [ ] LLM 无法判断时默认 false
- [ ] 空分支末端正确处理
- [ ] 自动补全依赖关系

---

### T03-07: 循环迭代步骤执行

**对应设计**: 五、循环迭代步骤执行

**文件**: `src/yellowbull/agent/executor.py`

**需要实现的方法**:
```python
class StepExecutor:
    async def execute_loop(
        self,
        loop_step: Step,
        step_states: dict[str, StepState],
        budget_guard: BudgetGuard,
    ) -> LoopResult:
        """
        执行循环步骤:
        1. 从 context_store 取 loop_input_step 的结果
        2. 校验结果是否为可迭代集合
        3. 遍历集合元素，逐个执行
        4. 检查全局保护（预算/超时）
        5. 累积结果存入 context_store
        
        返回 LoopResult:
        {
            "iterations": int,
            "success_count": int,
            "failed_count": int,
            "results": list[Any],
        }
        """
        ...

    def _expand_loop_collection(self, data: Any) -> list[Any]:
        """
        将循环输入展开为集合:
        - 列表/数组 → 直接使用
        - 单个值 → 包装为单元素列表
        - 空集合 → 返回空列表
        - 不可迭代 → 抛出异常
        """
        ...

    async def _execute_loop_iteration(
        self,
        step: Step,
        item: Any,
        iteration_index: int,
    ) -> StepResult:
        """
        执行单次循环迭代:
        1. 替换 description 中的变量
        2. 构建独立执行上下文
        3. 执行该步骤
        4. 返回结果
        """
        ...
```

**测试点**:
- [ ] 正常循环正确遍历
- [ ] 空集合标记 skipped
- [ ] 不可迭代数据标记 failed
- [ ] 预算耗尽截断循环
- [ ] 超时截断循环
- [ ] 单次迭代失败不影响后续迭代

---

## 五、失败处理模块

### T03-08: 重试与失败分析

**对应设计**: 六、失败处理与智能障碍排除

**文件**: `src/yellowbull/agent/failure_handler.py`

**需要实现的类**:
```python
class FailureHandler:
    """步骤失败处理"""

    def __init__(
        self,
        llm_client: LLMClient,
        max_retries: int = 2,
    ):
        self.llm_client = llm_client
        self.max_retries = max_retries
        self._obstacle_signatures: set[str] = set()

    async def handle_failure(
        self,
        step: Step,
        error: str,
        retry_count: int,
    ) -> FailureStrategy:
        """
        处理步骤失败:
        1. 判断是否可重试（网络/超时/工具内部错误）
        2. 可重试且 retry_count < max_retries → 退避重试
        3. 不可重试/重试耗尽 → LLM 分析
        4. 返回策略: retry / resolve / skip / abort
        """
        ...

    def _is_retryable(self, error: str) -> bool:
        """判断错误是否可重试"""
        ...

    async def _analyze_with_llm(
        self,
        step: Step,
        error: str,
        retry_count: int,
    ) -> FailureStrategy:
        """
        使用 LLM 分析失败原因:
        
        Prompt:
        "步骤 '{step.description}' 执行失败。
         错误: {error}
         已重试 {retry_count} 次。
         请分析:
         a. 这是可恢复的错误吗？
         b. 需要做什么才能排除这个障碍？
         请返回处理策略: retry / resolve / skip / abort"
        """
        ...

    def _record_obstacle_signature(self, step_id: str, error_type: str):
        """记录障碍签名: hash(step_id + error_type)"""
        ...

    def _is_repeated_obstacle(self, step_id: str, error_type: str) -> bool:
        """同一障碍出现 2 次 → 不再尝试排除"""
        ...
```

**测试点**:
- [ ] 可重试错误正确重试
- [ ] 重试耗尽后交给 LLM
- [ ] LLM 返回正确策略
- [ ] 重复障碍正确检测
- [ ] 退避重试间隔正确

---

### T03-09: 障碍排除子任务

**对应设计**: 六、失败处理与智能障碍排除 → 6.2 障碍排除流程

**文件**: `src/yellowbull/agent/obstacle_resolver.py`

**需要实现的类**:
```python
class ObstacleResolver:
    """障碍排除器"""

    def __init__(
        self,
        llm_client: LLMClient,
        execution_stack: ExecutionStack,
        step_executor: StepExecutor,
    ):
        self.llm_client = llm_client
        self.execution_stack = execution_stack
        self.step_executor = step_executor

    async def resolve(
        self,
        step: Step,
        error: str,
        parent_context: ContextStore,
    ) -> SubTaskResult:
        """
        障碍排除流程:
        1. LLM 生成排除方案（最多 3 步）
        2. 创建子任务
        3. 暂停当前流程（压栈）
        4. 执行子任务
        5. 子任务完成 → 恢复原流程
        
        返回 SubTaskResult:
        {
            "success": bool,
            "steps_executed": int,
            "subtask_id": str,
        }
        """
        ...

    async def _generate_resolution_plan(
        self,
        step: Step,
        error: str,
        nesting_depth: int,
    ) -> list[Step]:
        """
        LLM 生成障碍排除方案:
        
        Prompt:
        "步骤 '{step.description}' 因 '{error}' 失败。
         当前嵌套深度: {nesting_depth}
         请给出排除障碍的子任务:
         - 障碍描述
         - 排除步骤（最多 3 步）"
        """
        ...

    def _create_subtask(
        self,
        steps: list[Step],
        obstacle_description: str,
        parent_task_id: str,
        parent_step_id: str,
    ) -> SubTask:
        """创建障碍排除子任务"""
        ...
```

**测试点**:
- [ ] LLM 正确生成排除方案
- [ ] 子任务正确创建
- [ ] 压栈/弹栈正确
- [ ] 子任务成功恢复原流程
- [ ] 子任务失败跳过原步骤

---

## 六、全局保护模块

### T03-10: 预算与超时控制

**对应设计**: 九、无限嵌套防护、十一、超时与中断

**文件**: `src/yellowbull/agent/guard.py`

**需要实现的类**:
```python
class BudgetGuard:
    """
    全局保护: 预算 + 超时 + 取消检测
    """

    def __init__(
        self,
        max_total_steps: int = 100,
        total_timeout: int = 1800,
        step_timeout: int = 120,
    ):
        self.max_total_steps = max_total_steps
        self.total_timeout = total_timeout
        self.step_timeout = step_timeout
        self.steps_consumed = 0
        self._start_time: float | None = None
        self._cancelled = False

    def start(self):
        self._start_time = time.time()

    def check(self) -> GuardResult:
        """
        全局保护检查:
        - step_budget > 0 ?
        - 未超时 ?
        - 用户未取消 ?
        
        返回 GuardResult:
        {
            "ok": bool,
            "reason": str | None,  # 终止原因
        }
        """
        ...

    def consume_step(self):
        self.steps_consumed += 1

    def cancel(self):
        self._cancelled = True

    @property
    def remaining_budget(self) -> int:
        return max(0, self.max_total_steps - self.steps_consumed)

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0
        return time.time() - self._start_time
```

**测试点**:
- [ ] 预算耗尽正确终止
- [ ] 超时正确终止
- [ ] 用户取消正确终止
- [ ] 剩余预算计算正确
- [ ] 已用时间计算正确

---

## 七、任务完成判定

### T03-11: 完成评估与补救

**对应设计**: 十、任务完成判定

**文件**: `src/yellowbull/agent/completion_evaluator.py`

**需要实现的类**:
```python
class CompletionEvaluator:
    """任务完成判定"""

    def __init__(
        self,
        llm_client: LLMClient,
        max_remedy_rounds: int = 2,
    ):
        self.llm_client = llm_client
        self.max_remedy_rounds = max_remedy_rounds

    async def evaluate(
        self,
        task: Task,
        step_states: dict[str, StepState],
    ) -> TaskResult:
        """
        任务完成判定:
        1. 统计 critical_failed / non_critical_failed / done_count
        2. 判定结果:
           - critical_failed > 0 → 任务失败
           - 全部 done → 完全成功
           - 非关键 failed 且 完成率 >= 80% → 部分成功
           - 非关键 failed 且 完成率 < 80% → 补救判定
        
        返回 TaskResult:
        {
            "task_id": str,
            "status": "success" | "partial_success" | "failed",
            "done_count": int,
            "failed_count": int,
            "skipped_count": int,
            "critical_failed": list[str],
            "remedy_rounds": int,
        }
        """
        ...

    async def _remedy_check(
        self,
        task: Task,
        done_count: int,
        total_count: int,
        non_critical_failed: int,
    ) -> TaskResult:
        """
        补救判定 (最多 2 轮):
        交给 LLM:
        "已完成 {done_count}/{total} 步
         失败 {non_critical_failed} 步（均为非关键）
         目标: {goal}
         成功标准: {success_criteria}
         请判断:
         a. 已完成的部分是否足够满足目标？
         b. 若不够，能否通过补救达成？
         c. 补救需要哪些步骤？（最多 3 步）"
        """
        ...
```

**测试点**:
- [ ] 关键步骤失败 → 任务失败
- [ ] 全部完成 → 完全成功
- [ ] 非关键失败且完成率高 → 部分成功
- [ ] 完成率低触发补救判定
- [ ] LLM 判定足够 → 部分成功
- [ ] 补救 2 轮仍失败 → 任务失败

---

## 八、主执行引擎

### T03-12: 执行引擎主循环

**对应设计**: 二、执行流程全景

**文件**: `src/yellowbull/agent/engine.py`

**需要实现的类**:
```python
class TaskEngine:
    """
    任务执行引擎主入口:
    接收拆解后的 Step 列表，按依赖序执行，
    处理失败/分支/循环/障碍排除，最终判定结果。
    """

    def __init__(
        self,
        step_executor: StepExecutor,
        failure_handler: FailureHandler,
        step_selector: StepSelector,
        completion_evaluator: CompletionEvaluator,
        budget_guard: BudgetGuard,
        execution_stack: ExecutionStack,
    ):
        ...

    async def run(self, task: Task, steps: list[Step]) -> TaskResult:
        """
        执行任务主流程:
        1. 初始化 context_store、step_status_map
        2. 预校验: 拓扑排序、孤立步骤、循环依赖
        3. 主循环: 获取下一步 → 全局保护检查 → 执行步骤
        4. 无下一步 → 完成判定
        5. 生成报告
        """
        ...

    async def _main_loop(
        self,
        steps: list[Step],
        step_states: dict[str, StepState],
    ) -> None:
        """
        主执行循环:
        WHILE 有可执行步骤:
          1. 全局保护检查
          2. 获取下一步
          3. 判断步骤类型（普通/分支/循环）
          4. 执行步骤
          5. 记录结果
          6. 失败 → 级联标记 skipped
        """
        ...

    async def _handle_step_failure(
        self,
        step: Step,
        error: str,
        step_states: dict[str, StepState],
    ) -> None:
        """
        步骤失败统一处理:
        1. 交给 failure_handler
        2. 根据策略执行:
           - retry → 重试
           - resolve → 创建障碍排除子任务
           - skip → 标记 failed，继续
           - abort → 标记 failed，中断
        3. 级联标记依赖步骤为 skipped
        """
        ...

    def _build_task_result(
        self,
        task: Task,
        step_states: dict[str, StepState],
        budget_guard: BudgetGuard,
    ) -> TaskResult:
        """
        构建任务结果:
        - 统计各状态步骤数
        - 计算完成率
        - 收集耗时
        """
        ...
```

**测试点**:
- [ ] 正常任务完整执行
- [ ] 预校验失败直接终止
- [ ] 全局保护检查生效
- [ ] 步骤失败正确处理
- [ ] 主循环正确终止
- [ ] 任务结果正确构建

---

## 九、任务依赖顺序

```
T03-01 (步骤状态与上下文)
    │
    ├─→ T03-02 (执行栈)
    │
    ├─→ T03-03 (步骤预校验)
    │
    ├─→ T03-04 (步骤选择器)
    │
    ├─→ T03-05 (普通步骤执行)
    │       │
    │       ├─→ T03-06 (条件分支执行)
    │       │
    │       └─→ T03-07 (循环迭代执行)
    │
    ├─→ T03-08 (失败处理)
    │       │
    │       └─→ T03-09 (障碍排除)
    │
    ├─→ T03-10 (预算与超时)
    │
    ├─→ T03-11 (完成判定)
    │
    └─→ T03-12 (主执行引擎)
```

---

## 十、MVP 范围

| 任务 | MVP 是否必须 | 说明 |
|------|-------------|------|
| T03-01 | ✅ 是 | 核心状态管理 |
| T03-02 | ✅ 是 | 支持子任务嵌套 |
| T03-03 | ✅ 是 | 预校验保证安全 |
| T03-04 | ✅ 是 | 步骤调度核心 |
| T03-05 | ✅ 是 | 基础执行能力 |
| T03-06 | ✅ 是 | 分支是核心功能 |
| T03-07 | ✅ 是 | 循环是核心功能 |
| T03-08 | ✅ 是 | 失败处理是核心 |
| T03-09 | ✅ 是 | 障碍排除是核心 |
| T03-10 | ✅ 是 | 全局保护必须 |
| T03-11 | ✅ 是 | 完成判定必须 |
| T03-12 | ✅ 是 | 引擎主入口 |

> 执行引擎是 MVP 核心模块，所有任务均为必须实现。
