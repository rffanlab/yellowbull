# 基础设施 — 代码开发任务

> 对应主文档：基础设施层（LLM 接口、配置管理、持久化）
> 为所有业务模块提供公共支撑

---

## 一、项目初始化

### T00-01: 项目脚手架

**目标**: 建立 Python 项目基础结构

**产出**:
```
yellowbull/
├── pyproject.toml          # 项目配置（依赖、版本、入口）
├── src/yellowbull/
│   ├── __init__.py
│   ├── main.py             # CLI 入口
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py     # 配置管理
│   ├── models/             # 数据模型
│   │   ├── __init__.py
│   │   └── ...
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py       # LLM 客户端
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py         # 工具基类
│   │   └── ...
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── receiver.py     # 任务接收
│   │   ├── breakdown.py    # 步骤拆解
│   │   ├── engine.py       # 执行引擎
│   │   └── aggregator.py   # 结果汇总
│   ├── experience/
│   │   ├── __init__.py
│   │   ├── repo.py         # 经验仓库
│   │   ├── retriever.py    # 经验检索
│   │   └── recorder.py     # 经验记录
│   └── storage/
│       ├── __init__.py
│       └── db.py           # SQLite 连接管理
├── tests/
│   ├── __init__.py
│   └── ...
└── README.md
```

**具体任务**:
1. 创建 `pyproject.toml`，配置项目元数据、依赖（pydantic、aiosqlite 等）
2. 创建上述目录结构和 `__init__.py`
3. 创建 `.gitignore`

---

## 二、配置管理模块

### T00-02: Settings 配置类

**对应设计**: 主文档基础设施层 → 配置管理

**目标**: 提供全局配置管理，支持环境变量覆盖

**文件**: `src/yellowbull/config/settings.py`

**需要实现的类**:
```python
class LLMSettings(BaseSettings):
    provider: str = "openai"           # openai / anthropic / ...
    model: str = "gpt-4o"
    api_key: str                       # 从环境变量读取
    base_url: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout: int = 60

class ExecutionSettings(BaseSettings):
    step_timeout: int = 120            # 单步超时秒数
    task_timeout: int = 1800           # 任务总超时秒数
    max_total_steps: int = 100         # 总步数预算
    max_retries_per_step: int = 2      # 单步重试次数
    max_subtask_steps: int = 3         # 子任务最大步骤
    max_remedy_rounds: int = 2         # 补救轮数

class ExperienceSettings(BaseSettings):
    enabled: bool = True
    max_retrieve_count: int = 5
    min_relevance_score: float = 0.3
    aging_period_temporary: int = 30
    aging_period_project: int = 180
    cleanup_threshold_days: int = 365
    score_weight_success_rate: float = 0.5
    score_weight_efficiency: float = 0.2
    score_weight_tool: float = 0.2
    score_weight_retry: float = 0.1

class DatabaseSettings(BaseSettings):
    path: str = "./data/yellowbull.db"  # SQLite 路径

class Settings(BaseSettings):
    llm: LLMSettings = LLMSettings()
    execution: ExecutionSettings = ExecutionSettings()
    experience: ExperienceSettings = ExperienceSettings()
    database: DatabaseSettings = DatabaseSettings()
    project_root: str = "."             # 当前工作目录

    class Config:
        env_prefix = "YELLOWBULL_"
```

**测试点**:
- [ ] 默认值正确加载
- [ ] 环境变量覆盖生效（如 `YELLOWBULL_LLM_MODEL=claude`）
- [ ] 缺失必填项时报错（如 api_key）

---

## 三、LLM 客户端模块

### T00-03: LLM Client 封装

**对应设计**: 主文档基础设施层 → LLM 接口

**目标**: 统一 LLM 调用接口，支持多种 provider

**文件**: `src/yellowbull/llm/client.py`

**需要实现的类**:
```python
class LLMClient:
    """LLM 调用客户端"""

    def __init__(self, settings: LLMSettings):
        ...

    async def chat(
        self,
        system_prompt: str,
        user_messages: list[str],
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        """发起对话请求，返回 LLM 回复文本"""
        ...

    async def structured_chat(
        self,
        system_prompt: str,
        user_messages: list[str],
        response_model: Type[BaseModel],
    ) -> BaseModel:
        """发起对话请求，自动解析为 Pydantic 模型"""
        ...
```

**需要实现的功能**:
1. 基于 `openai` 库封装（MVP 先用 OpenAI 兼容接口）
2. `chat()` 方法：拼接 system + user messages，发起请求，返回文本
3. `structured_chat()` 方法：设置 `response_format={"type": "json_object"}`，解析 JSON 为 Pydantic 模型
4. 超时处理：使用 settings.timeout
5. 重试装饰器：网络错误自动重试 1 次
6. 调用日志：记录每次请求的 token 消耗（如 API 支持）

**测试点**:
- [ ] chat() 正常返回文本
- [ ] structured_chat() 正确解析 JSON 为模型
- [ ] JSON 解析失败时抛出清晰异常
- [ ] 超时正确处理

---

## 四、数据模型模块

### T00-04: 核心数据模型定义

**对应设计**: 主文档 + 各子文档中的数据模型

**目标**: 定义 Task、Step、ExecutionResult 等核心模型

**文件**: `src/yellowbull/models/`

#### T00-04-1: Task 模型

**文件**: `src/yellowbull/models/task.py`

```python
class Task(BaseModel):
    id: str                              # UUID
    goal: str                            # 任务目标
    constraints: list[str] = []          # 约束列表
    success_criteria: list[str] = []     # 成功标准
    context_files: list[str] = []        # 上下文文件
    confidence: float                    # 解析置信度 0.0~1.0
    clarification_needed: str = ""       # 需澄清的问题
    clarification_options: list[str] = [] # 澄清选项
    created_at: datetime = Field(default_factory=datetime.now)
    status: TaskStatus = TaskStatus.PENDING
```

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

#### T00-04-2: Step 模型

**文件**: `src/yellowbull/models/step.py`

```python
class Step(BaseModel):
    step_id: str
    description: str
    tool_hint: str                       # file | shell | code | search
    depends_on: list[str] = []
    is_critical: bool = False
    is_branch_point: bool = False
    is_loop: bool = False
    branch_condition: str | None = None
    true_next: list[str] = []
    false_next: list[str] = []
    loop_input_step: str | None = None
    loop_item_variable: str | None = None
    expected_output: str = ""
    output_format: str = "text"
    input_from: list[str] = []
    input_format: str | None = None
    status: StepStatus = StepStatus.PENDING
```

```python
class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
```

#### T00-04-3: 执行结果模型

**文件**: `src/yellowbull/models/result.py`

```python
class StepResult(BaseModel):
    step_id: str
    status: StepStatus
    output: any = None
    error: str | None = None
    retry_count: int = 0
    duration_seconds: float = 0
    side_effects: list[str] = []
    timestamp: datetime = Field(default_factory=datetime.now)

class TaskResult(BaseModel):
    task_id: str
    conclusion: TaskConclusion           # success / partial_success / failure / cancelled
    achievement_score: float            # 0.0 ~ 1.0
    step_results: list[StepResult]
    subtask_results: list["TaskResult"] = []
    total_duration_seconds: float = 0
    termination_reason: str = ""        # normal / timeout / budget_exhausted / cancelled
    side_effects: list[str] = []
    suggestions: list[str] = []
```

```python
class TaskConclusion(str, Enum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
```

#### T00-04-4: 子任务模型

**文件**: `src/yellowbull/models/subtask.py`

```python
class SubTask(BaseModel):
    id: str
    parent_task_id: str
    parent_step_id: str
    goal: str
    obstacle_description: str
    steps: list[Step]
    status: TaskStatus = TaskStatus.PENDING
    context_inherit: bool = True
    max_steps: int = 3
```

#### T00-04-5: 经验模型

**文件**: `src/yellowbull/models/experience.py`

```python
class Experience(BaseModel):
    id: str
    task_summary: str
    task_category: str
    outcome: str                         # success / partial / failed
    score: float                         # -1.0 ~ 1.0
    lessons_learned: str = ""
    tool_chain: list[str] = []
    steps_count: int = 0
    success_rate: float = 0.0
    retry_count: int = 0
    duration_seconds: int = 0
    is_permanent: bool = False
    generality: float = 0.5
    project_name: str | None = None
    keywords: list[str] = []
    tags: list[str] = []
    created_at: datetime = Field(default_factory=datetime.now)
```

**测试点**:
- [ ] 所有模型可正常实例化
- [ ] 枚举值正确序列化/反序列化
- [ ] 默认值正确设置
- [ ] 嵌套模型（TaskResult 含 StepResult）可正常序列化

---

## 五、数据库模块

### T00-05: SQLite 连接与初始化

**对应设计**: 主文档基础设施层 → 持久化

**文件**: `src/yellowbull/storage/db.py`

**需要实现的功能**:
1. 数据库连接管理（单例）
2. 建表 SQL 脚本（经验表、关键词表、标签表）
3. 初始化入口（首次运行时自动建表）
4. 提供 async 接口

```python
class DatabaseManager:
    _instance: ClassVar["DatabaseManager | None"] = None
    _db: aiosqlite.Connection | None = None

    @classmethod
    async def get(cls) -> "DatabaseManager":
        ...

    async def initialize(self):
        """创建所有表"""
        ...

    async def close(self):
        ...

    @property
    def connection(self) -> aiosqlite.Connection:
        ...
```

**建表 SQL**（来自 02-experience-system.md）:
```sql
CREATE TABLE IF NOT EXISTS experiences (...);
CREATE TABLE IF NOT EXISTS experience_keywords (...);
CREATE TABLE IF NOT EXISTS experience_tags (...);
-- 索引
```

**测试点**:
- [ ] 首次调用自动建表
- [ ] 重复调用不重复建表
- [ ] 连接正常关闭

---

## 六、工具系统基类

### T00-06: Tool 基类定义

**对应设计**: 主文档支撑层 → 工具系统

**目标**: 定义工具抽象基类，提供统一接口

**文件**: `src/yellowbull/tools/base.py`

**需要实现的类**:
```python
class SideEffectType(str, Enum):
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    CONFIG_CHANGE = "config_change"
    DEPENDENCY_INSTALL = "dependency_install"
    NETWORK_REQUEST = "network_request"

class Tool(BaseModel):
    name: str
    description: str
    side_effects: list[SideEffectType] = []
    is_safe: bool = True                # 是否安全（无需确认）

    async def execute(self, params: dict) -> ToolResult:
        """执行工具，返回结果"""
        raise NotImplementedError

    def validate_params(self, params: dict) -> bool:
        """校验参数"""
        return True

class ToolResult(BaseModel):
    success: bool
    output: any = None
    error: str | None = None
    side_effects: list[str] = []        # 实际产生的副作用描述
```

**需要实现的注册表**:
```python
class ToolRegistry:
    _tools: dict[str, Tool] = {}

    @classmethod
    def register(cls, tool: Tool):
        ...

    @classmethod
    def get(cls, name: str) -> Tool | None:
        ...

    @classmethod
    def list_all(cls) -> list[Tool]:
        ...

    @classmethod
    def match_by_hint(cls, hint: str) -> list[Tool]:
        """根据 tool_hint 匹配工具列表"""
        ...
```

**测试点**:
- [ ] 工具注册/获取正常
- [ ] match_by_hint 正确匹配
- [ ] 未知工具返回 None

---

## 七、内置工具实现

### T00-07: 文件工具

**文件**: `src/yellowbull/tools/file_tool.py`

**需要实现的能力**:
1. `read_file(path: str)` — 读取文件内容
2. `write_file(path: str, content: str)` — 写入文件
3. `search_files(pattern: str, directory: str)` — 搜索文件（glob/regex）
4. `list_directory(path: str)` — 列出目录

**副作用声明**: `FILE_WRITE`, `FILE_DELETE`（视操作而定）

### T00-08: Shell 工具

**文件**: `src/yellowbull/tools/shell_tool.py`

**需要实现的能力**:
1. `execute_command(command: str, timeout: int = 120)` — 执行 shell 命令
2. 危险命令检测（rm -rf、format 等）
3. 超时控制
4. 输出截断（超过 8192 字符截断并提示）

**副作用声明**: 根据命令类型动态判断

### T00-09: 代码分析工具

**文件**: `src/yellowbull/tools/code_tool.py`

**需要实现的能力**:
1. `analyze_code(file_path: str, analysis_type: str)` — 代码分析
2. `generate_code(prompt: str, language: str)` — 代码生成（委托 LLM）
3. `modify_code(file_path: str, instructions: str)` — 代码修改

### T00-10: 搜索工具

**文件**: `src/yellowbull/tools/search_tool.py`

**需要实现的能力**:
1. `search_codebase(query: str, directories: list[str])` — 代码库语义搜索
2. `grep(pattern: str, paths: list[str])` — 正则搜索

---

## 八、CLI 入口

### T00-11: 主入口与命令行参数

**文件**: `src/yellowbull/main.py`

**需要实现的功能**:
1. 解析命令行参数（`--model`, `--project-root`, `--config` 等）
2. 初始化 Settings
3. 初始化 LLMClient
4. 初始化 DatabaseManager
5. 注册所有工具到 ToolRegistry
6. 启动交互式 REPL 或执行单次任务

```python
async def main():
    # 1. 解析参数
    # 2. 初始化配置
    # 3. 初始化基础设施
    # 4. 启动 Agent 循环
    pass
```

**命令行参数**:
```
yellowbull [OPTIONS] [TASK]

Options:
  --model TEXT            LLM 模型名称
  --project-root PATH     项目根目录
  --config PATH           配置文件路径
  --verbose               详细输出
  --help                  显示帮助
```

---

## 九、任务依赖顺序

```
T00-01 (项目脚手架)
    │
    ├─→ T00-02 (配置管理)
    │       │
    │       ├─→ T00-03 (LLM Client)
    │       │
    │       └─→ T00-05 (数据库)
    │
    ├─→ T00-04 (数据模型)
    │       │
    │       ├─→ T00-06 (工具基类)
    │       │       │
    │       │       ├─→ T00-07 (文件工具)
    │       │       ├─→ T00-08 (Shell 工具)
    │       │       ├─→ T00-09 (代码工具)
    │       │       └─→ T00-10 (搜索工具)
    │       │
    │       └─→ T00-11 (CLI 入口)
    │               │
    │               └─→ 业务模块 (01~04)
```

---

## 十、MVP 范围

| 任务 | MVP 是否必须 | 说明 |
|------|-------------|------|
| T00-01 | ✅ 是 | 项目基础 |
| T00-02 | ✅ 是 | 配置管理 |
| T00-03 | ✅ 是 | LLM 调用 |
| T00-04 | ✅ 是 | 数据模型 |
| T00-05 | ✅ 是 | 数据库 |
| T00-06 | ✅ 是 | 工具基类 |
| T00-07 | ✅ 是 | 文件工具 |
| T00-08 | ✅ 是 | Shell 工具 |
| T00-09 | ✅ 是 | 代码工具 |
| T00-10 | ⏺ 可选 | MVP 可用 grep 替代 |
| T00-11 | ✅ 是 | CLI 入口 |
