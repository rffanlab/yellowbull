# 任务接收与步骤拆解 — 代码开发任务

> 对应设计文档：01-task-reception-and-breakdown.md
> 模块职责：接收用户输入 → 解析为结构化 Task → 拆解为 Step 列表

---

## 一、任务接收模块

### T01-01: 输入预处理

**对应设计**: 1.2 接收流程 → 步骤 1（预处理）

**文件**: `src/yellowbull/agent/receiver.py`

**需要实现的方法**:
```python
class TaskReceiver:
    async def preprocess_input(self, raw_input: str) -> PreprocessedInput:
        """
        预处理用户输入:
        1. 去噪/格式化（去除多余空白、统一换行）
        2. 超长截断（>4096 字符截断并标记）
        3. 代码块识别（\`\`\` 包裹的内容标记为代码上下文）
        4. 文件路径识别（提取 @file.md 或 path/to/file 引用）
        """
        ...

class PreprocessedInput(BaseModel):
    cleaned_text: str
    is_truncated: bool = False
    code_contexts: list[str] = []       # 提取的代码块
    file_references: list[str] = []     # 提取的文件引用
```

**测试点**:
- [ ] 超长输入正确截断
- [ ] 代码块正确提取
- [ ] 文件路径正确识别

### T01-02: 意图分类

**对应设计**: 1.2 接收流程 → 步骤 2（意图分类）

**文件**: `src/yellowbull/agent/receiver.py`

**需要实现的方法**:
```python
class InputIntent(str, Enum):
    NEW_TASK = "new_task"
    SUPPLEMENT = "supplement"           # 对上一轮的补充
    CHAT = "chat"                      # 问候/闲聊
    CONTROL = "control"                # 退出/取消/状态查询

class TaskReceiver:
    async def classify_intent(self, input_text: str, has_context: bool) -> InputIntent:
        """
        判断用户输入意图:
        - 新任务 → 走完整接收流程
        - 补充 → 追加到对话上下文
        - 闲聊 → 直接友好回应
        - 控制指令 → 执行控制逻辑
        """
        ...
```

**控制指令处理**:
```python
    CONTROL_COMMANDS: dict[str, Callable] = {
        "退出": handle_exit,
        "quit": handle_exit,
        "取消": handle_cancel,
        "停": handle_cancel,
        "帮助": handle_help,
        "状态": handle_status,
    }

    def handle_control_command(self, command: str) -> str | None:
        """处理控制指令，返回响应文本或 None（表示内部处理）"""
        ...
```

**测试点**:
- [ ] 新任务正确分类
- [ ] 控制指令正确识别
- [ ] 无上下文时的补充输入降级为新任务

### T01-03: 对话上下文管理

**对应设计**: 1.5 对话上下文管理

**文件**: `src/yellowbull/agent/receiver.py`

**需要实现的方法**:
```python
class ConversationBuffer:
    def __init__(self, max_rounds: int = 10):
        self.rounds: list[ConversationRound] = []
        self.max_rounds = max_rounds

    def add_round(self, user_input: str, assistant_response: str):
        ...

    def get_full_context(self) -> str:
        """合并所有轮次为完整上下文文本"""
        ...

    def is_empty(self) -> bool:
        ...

    def clear(self):
        ...

class ConversationRound(BaseModel):
    user_input: str
    assistant_response: str
    timestamp: datetime = Field(default_factory=datetime.now)
```

**测试点**:
- [ ] 超过 max_rounds 自动淘汰旧轮次
- [ ] get_full_context 正确拼接

### T01-04: LLM 任务解析

**对应设计**: 1.2 接收流程 → 步骤 4（LLM 解析）、1.9 Prompt 设计

**文件**: `src/yellowbull/agent/receiver.py`

**需要实现的方法**:
```python
class TaskParseResult(BaseModel):
    goal: str
    constraints: list[str] = []
    success_criteria: list[str] = []
    context_files: list[str] = []
    confidence: float
    clarification_needed: str = ""
    clarification_options: list[str] = []

class TaskReceiver:
    async def parse_task(self, input_text: str, context: str = "") -> TaskParseResult:
        """
        使用 LLM 将用户输入解析为结构化 Task:
        1. 组装解析 Prompt（角色 + 规则 + 示例 + 当前输入）
        2. 调用 LLM structured_chat
        3. 异常处理：JSON 错误重试 1 次，仍失败则降级
        """
        ...

    def _build_parse_prompt(self, input_text: str, context: str) -> str:
        """构建任务解析 Prompt"""
        ...
```

**Prompt 模板**（存于 `src/yellowbull/prompts/task_parse.py`）:
```python
TASK_PARSE_SYSTEM_PROMPT = """
你是一个任务解析专家。从用户输入中提取结构化任务信息。
...
"""

TASK_PARSE_FEW_SHOT_EXAMPLES = [
    # 示例 1: 简单任务
    # 示例 2: 复杂任务
    # 示例 3: 模糊任务（需澄清）
]
```

**降级逻辑**:
```python
    async def _fallback_parse(self, input_text: str) -> TaskParseResult:
        """LLM 解析失败时的降级方案:
        - goal = 原始输入
        - confidence = 0.5
        - 其他字段为空
        """
        ...
```

**测试点**:
- [ ] 正常输入正确解析
- [ ] 低置信度输入正确标记
- [ ] LLM 异常时正确降级
- [ ] 需要澄清的任务正确输出澄清问题

### T01-05: 置信度评估与确认流程

**对应设计**: 1.2 接收流程 → 步骤 5（置信度评估）、1.7 置信度规则

**文件**: `src/yellowbull/agent/receiver.py`

**需要实现的方法**:
```python
class TaskReceiver:
    async def evaluate_and_confirm(
        self,
        parse_result: TaskParseResult,
        on_confirm: Callable[[str], Awaitable[bool]],  # 用户确认回调
        on_clarify: Callable[[str, list[str]], Awaitable[str]],  # 追问回调
    ) -> Task | None:
        """
        根据置信度决定流程:
        - >= 0.8 → 直接创建 Task
        - 0.5 ~ 0.8 → 展示计划让用户确认
        - < 0.5 → 追问澄清（最多 3 轮）
        """
        ...

    async def _clarify_with_user(
        self,
        parse_result: TaskParseResult,
        on_clarify: Callable[[str, list[str]], Awaitable[str]],
        max_rounds: int = 3,
    ) -> TaskParseResult | None:
        """追问澄清流程"""
        ...
```

**测试点**:
- [ ] 高置信度直接通过
- [ ] 中置信度触发确认
- [ ] 低置信度触发追问
- [ ] 追问超过 3 轮使用默认假设

### T01-06: 危险操作检查

**对应设计**: 1.2 接收流程 → 步骤 6、1.8 危险操作识别

**文件**: `src/yellowbull/agent/receiver.py`

**需要实现的方法**:
```python
class DangerLevel(str, Enum):
    RED = "red"                        # 必须确认
    YELLOW = "yellow"                  # 建议确认
    GREEN = "green"                    # 自动执行

class DangerCheckResult(BaseModel):
    level: DangerLevel
    reasons: list[str] = []

class TaskReceiver:
    async def check_danger_level(self, task: Task) -> DangerCheckResult:
        """
        检查任务是否包含危险操作:
        1. 先用规则匹配（关键词/正则）
        2. 再用 LLM 综合判断
        """
        ...

    def _rule_based_check(self, text: str) -> DangerCheckResult:
        """规则匹配:
        红色: rm -rf, DROP TABLE, 文件删除
        黄色: 批量修改, 网络请求
        绿色: 读取, 搜索, 分析
        """
        ...
```

**危险模式匹配表**:
```python
DANGER_PATTERNS = {
    DangerLevel.RED: [
        r'\brm\s+(-r|-f|-rf|-fr)\b',
        r'\bformat\b',
        r'\bDROP\s+TABLE\b',
        r'\bTRUNCATE\b',
        r'\bmkfs\b',
    ],
    DangerLevel.YELLOW: [
        r'\binstall\b',
        r'\brequest\b',
        r'\bPOST\b',
    ],
}
```

**测试点**:
- [ ] 危险命令正确识别为红色
- [ ] 安全操作正确识别为绿色
- [ ] 混合操作取最高危险级别

---

## 二、步骤拆解模块

### T01-07: LLM 步骤拆解

**对应设计**: 3.2 拆解流程 → 步骤 2（LLM 拆解）、3.10 Prompt 设计

**文件**: `src/yellowbull/agent/breakdown.py`

**需要实现的方法**:
```python
class StepBreakdown:
    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry, settings: ExecutionSettings):
        ...

    async def breakdown(
        self,
        task: Task,
        experiences: list[Experience] | None = None,
    ) -> list[Step]:
        """
        将任务拆解为步骤列表:
        1. 构建拆解 Prompt（7 层组装）
        2. 调用 LLM 获取步骤列表
        3. 质量校验
        4. 步骤排序
        5. 步骤数校验
        """
        ...
```

**Prompt 组装**（存于 `src/yellowbull/prompts/breakdown.py`）:
```python
def build_breakdown_prompt(
    task: Task,
    tools: list[Tool],
    experiences: list[Experience] | None,
    few_shot_examples: list[dict],
) -> tuple[str, str]:
    """
    返回 (system_prompt, user_message)
    按 7 层组装:
    1. 角色 + 任务说明
    2. 可用工具清单
    3. 拆解规则
    4. 经验提示（若有）
    5. Few-shot 示例
    6. 当前任务信息
    7. 输出格式约束
    """
    ...
```

**测试点**:
- [ ] 简单任务拆解为 1-3 步
- [ ] 复杂任务拆解为 3-8 步
- [ ] 经验正确注入 Prompt
- [ ] 工具清单正确列出

### T01-08: 质量校验

**对应设计**: 3.2 拆解流程 → 步骤 3、3.3 质量校验

**文件**: `src/yellowbull/agent/breakdown.py`

**需要实现的方法**:
```python
class StepBreakdown:
    async def _validate_steps(self, steps: list[Step], task: Task) -> ValidationReport:
        """
        校验拆解质量:
        1. 完整性检查（LLM 反向验证）
        2. 工具可用性检查
        3. 循环依赖检测（拓扑排序）
        4. 孤立步骤检测
        5. 可执行性检查
        """
        ...

    def _check_circular_dependency(self, steps: list[Step]) -> bool:
        """拓扑排序检测循环依赖"""
        ...

    def _check_orphan_steps(self, steps: list[Step]) -> list[str]:
        """检测孤立步骤"""
        ...

    def _check_tool_availability(self, steps: list[Step]) -> list[str]:
        """检查每步的 tool_hint 是否有对应工具"""
        ...

class ValidationReport(BaseModel):
    is_valid: bool
    issues: list[str] = []
    suggestions: list[str] = []
```

**测试点**:
- [ ] 循环依赖正确检测
- [ ] 孤立步骤正确检测
- [ ] 无匹配工具正确报告
- [ ] 校验失败后 LLM 修正 1 次

### T01-09: 步骤排序与合并

**对应设计**: 3.2 拆解流程 → 步骤 4/5、3.5 步骤合并策略

**文件**: `src/yellowbull/agent/breakdown.py`

**需要实现的方法**:
```python
class StepBreakdown:
    def _sort_steps(self, steps: list[Step]) -> list[Step]:
        """
        拓扑排序 + 优先级:
        1. 关键步骤优先
        2. 读操作优先于写操作
        3. 拓扑序靠前的优先
        """
        ...

    def _merge_steps_if_needed(
        self,
        steps: list[Step],
        max_steps: int,
    ) -> list[Step]:
        """
        步骤数超过 max_steps 时合并:
        1. 合并同类操作
        2. 合并紧邻无依赖步骤
        3. 合并非关键步骤
        """
        ...
```

**测试点**:
- [ ] 依赖关系正确的步骤排在前面
- [ ] 超过 max_steps 时正确合并
- [ ] 关键步骤不被合并

### T01-10: 步骤间数据传递（ContextStore）

**对应设计**: 3.4 步骤间数据传递

**文件**: `src/yellowbull/agent/context_store.py`

**需要实现的类**:
```python
class ContextStore:
    """
    步骤间中间结果存储:
    - Step 执行完后将结果存入 context_store
    - 后续步骤通过引用 key 获取数据
    - 支持 input_from / input_format / output_format
    """

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._data: dict[str, StepOutput] = {}

    def store(self, step_id: str, output: StepOutput):
        """存储步骤输出"""
        ...

    def get(self, step_id: str) -> StepOutput | None:
        """按 step_id 获取输出"""
        ...

    def gather_inputs(self, step: Step) -> dict[str, StepOutput]:
        """
        根据 step.input_from 收集上游步骤输出:
        1. 遍历 input_from 中的 step_id
        2. 从 _data 中获取对应输出
        3. 若有缺失 → 抛异常（依赖未满足）
        """
        ...

    def has_all_inputs(self, step: Step) -> bool:
        """检查步骤的所有输入是否已就绪"""
        ...

class StepOutput(BaseModel):
    step_id: str
    data: any
    output_format: str
    timestamp: datetime = Field(default_factory=datetime.now)
```

**测试点**:
- [ ] 存储/读取正确
- [ ] gather_inputs 正确收集上游输出
- [ ] 缺失输入正确报异常
- [ ] has_all_inputs 正确判断

### T01-11: 拆解失败兜底策略

**对应设计**: 3.12 拆解失败兜底策略

**文件**: `src/yellowbull/agent/breakdown.py`

**需要实现的方法**:
```python
class StepBreakdown:
    async def _breakdown_with_fallback(
        self,
        task: Task,
        experiences: list[Experience] | None = None,
    ) -> list[Step]:
        """
        拆解兜底流程:
        1. 正常 LLM 拆解
        2. JSON 格式错误 → 重试 1 次
        3. 校验不通过 → 让 LLM 修正（带校验失败详情）
        4. 修正仍不通过 → 降级为"单步任务"
        5. LLM 调用本身失败 → 不降级，抛异常等用户重试
        """
        ...

    async def _degrade_to_single_step(self, task: Task) -> list[Step]:
        """
        降级为单步任务:
        - 整个 task 作为 1 个步骤
        - 标记低置信
        - tool_hint 由 LLM 快速猜测或默认为 file
        """
        ...
```

**测试点**:
- [ ] JSON 错误重试 1 次
- [ ] 校验失败触发 LLM 修正
- [ ] 修正失败降级为单步
- [ ] LLM 调用失败不降级

### T01-12: 计划展示与用户确认

**对应设计**: 3.13 用户展示格式

**文件**: `src/yellowbull/agent/plan_display.py`

**需要实现的类**:
```python
class PlanDisplay:
    """
    仅中低置信任务展示计划确认:
    1. 渲染步骤列表（含工具图标）
    2. 显示危险操作警告
    3. 等待用户确认
    """

    def render_plan(
        self,
        task: Task,
        steps: list[Step],
        danger_level: DangerLevel,
    ) -> str:
        """
        渲染任务计划文本:
        - 目标描述
        - 步骤列表（带工具类型标签）
        - 危险操作警告（若有）
        - 预计步骤数
        - 确认提示
        """
        ...

    def render_step_line(self, index: int, step: Step) -> str:
        """渲染单行步骤: "[工具] 描述"""
        ...

    def render_warning(self, danger_level: DangerLevel, steps: list[Step]) -> str | None:
        """渲染危险操作警告"""
        ...
```

**测试点**:
- [ ] 步骤列表正确渲染
- [ ] 危险操作正确警告
- [ ] 工具类型标签正确显示

### T01-13: 核心数据结构定义

**对应设计**: 四、数据结构

**文件**: `src/yellowbull/models/task_models.py`

**需要实现的模型**:
```python
class Task(BaseModel):
    id: str
    goal: str
    constraints: list[str] = []
    success_criteria: list[str] = []
    context: str = ""
    status: TaskStatus = TaskStatus.PENDING
    confidence: float = 1.0
    conversation_history: list[ConversationTurn] = []

class Step(BaseModel):
    id: str
    task_id: str
    description: str
    tool_hint: str
    depends_on: list[str] = []
    expected_output: str = ""
    status: StepStatus = StepStatus.PENDING
    is_critical: bool = False
    is_branch_point: bool = False
    is_loop: bool = False
    branch_condition: str | None = None
    true_next: list[str] = []
    false_next: list[str] = []
    loop_input_step: str | None = None
    loop_item_variable: str | None = None
    input_from: list[str] = []
    input_format: str | None = None
    output_format: str | None = None

class StepResult(BaseModel):
    step_id: str
    tool_used: str
    output: str
    error: str | None = None
    success: bool
    retry_count: int = 0
    duration_ms: int

class ConversationTurn(BaseModel):
    role: str  # "user" | "agent"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)

class Experience(BaseModel):
    id: str
    task_type: str
    tool_chain: list[str]
    pattern: str
    lesson: str
    score: float  # -1.0 ~ 1.0
    created_at: datetime = Field(default_factory=datetime.now)

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
```

**测试点**:
- [ ] 所有模型字段正确定义
- [ ] 枚举值与设计文档一致
- [ ] 默认值正确

---

## 三、任务依赖顺序

```
T01-01 (输入预处理)
    │
    ├─→ T01-02 (意图分类)
    │       │
    │       ├─→ T01-03 (对话上下文)
    │       │
    │       ├─→ T01-04 (LLM 解析)
    │       │       │
    │       │       ├─→ T01-05 (置信度+确认)
    │       │       │
    │       │       └─→ T01-06 (危险检查)
    │       │
    │       └─→ T01-07 (LLM 拆解)
    │               │
    │               ├─→ T01-08 (质量校验)
    │               │
    │               ├─→ T01-09 (排序合并)
    │               │       │
    │               │       ├─→ T01-10 (数据传递/ContextStore)
    │               │       │
    │               │       ├─→ T01-11 (拆解兜底)
    │               │       │
    │               │       └─→ T01-12 (计划展示)
    │               │
    │               └─→ T01-13 (动态工具) [可选]
```

---

## 四、MVP 范围

| 任务 | MVP 是否必须 | 说明 |
|------|-------------|------|
| T01-01 | ✅ 是 | 输入预处理 |
| T01-02 | ✅ 是 | 意图分类 |
| T01-03 | ✅ 是 | 对话上下文 |
| T01-04 | ✅ 是 | LLM 解析 |
| T01-05 | ✅ 是 | 置信度+确认 |
| T01-06 | ✅ 是 | 危险检查 |
| T01-07 | ✅ 是 | LLM 拆解 |
| T01-08 | ✅ 是 | 质量校验 |
| T01-09 | ✅ 是 | 排序合并 |
| T01-10 | ✅ 是 | 步骤间数据传递 |
| T01-11 | ✅ 是 | 拆解兜底策略 |
| T01-12 | ✅ 是 | 计划展示确认 |
| T01-13 | ⏺ 可选 | 动态工具生成 |
