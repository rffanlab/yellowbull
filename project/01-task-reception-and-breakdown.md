# 任务接收与步骤拆解 — 详细设计

> 对应主流程第 1 步（任务接收）和第 2 步（经验回顾）和第 3 步（步骤拆解）

---

## 一、任务接收

### 1.1 用户输入形式

| 输入类型 | 示例 | 特点 |
|---------|------|------|
| 一句话任务 | "帮我把项目里的日志级别改成 debug" | 简短，意图明确 |
| 多轮对话任务 | "我想重构用户模块" → "重点改认证部分" | 需要上下文累积 |
| 复杂任务 | "分析这个接口的性能瓶颈并优化" | 需要多步骤、多工具 |
| 模糊任务 | "看看代码有什么问题" | 需要追问澄清 |
| 附带上下文 | "参考 docs/api.md，生成对应的客户端代码" | 有文件/路径引用 |

### 1.2 接收流程

```
用户输入
    │
    ▼
┌─────────────────┐
│ 1. 预处理         │
│ - 去噪/格式化     │
│ - 超长截断        │
│ - 代码/文件识别   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 意图分类       │
│ - 新任务          │
│ - 补充/追问       │──→ 加入对话上下文
│ - 问候/闲聊       │──→ 友好回应
│ - 控制指令        │──→ 执行控制逻辑
└────────┬────────┘
         │ 新任务
         ▼
┌─────────────────┐
│ 3. 上下文组装     │
│ 合并多轮对话       │
│ 形成完整任务描述   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. LLM 解析      │
│ 输出结构化 Task   │
│ 异常 → 重试/降级  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. 置信度评估     │
│ ≥0.8 → 直接执行   │
│ 0.5~0.8 → 确认   │
│ <0.5 → 追问      │──→ 提供选项供用户选择
└────────┬────────┘         （最多 3 轮）
         │
         ▼
┌─────────────────┐
│ 6. 危险操作检查   │
│ 红色 → 必须确认   │
│ 黄色 → 建议确认   │
│ 绿色 → 自动执行   │
└────────┬────────┘
         │
         ▼
    结构化 Task
```

### 1.3 输入处理规则

```
- 超长输入（>4096字）→ 截断或提示用户精简
- 代码粘贴 → 自动识别编程语言，作为上下文附加
- 文件路径引用 → 验证路径是否存在，不存在则提示
- 特殊字符/注入攻击 → 基础过滤
```

### 1.4 非任务输入处理

| 输入类型 | 示例 | 处理方式 |
|---------|------|---------|
| 问候/闲聊 | "你好"、"在吗" | 友好回应，等待任务 |
| 帮助指令 | "帮助"、"怎么用" | 输出使用说明 |
| 退出指令 | "退出"、"quit" | 退出程序 |
| 状态查询 | "当前在做什么" | 返回当前任务状态 |
| 取消指令 | "停"、"取消" | 中断当前任务 |
| 配置指令 | "切换模型" | 修改配置 |

### 1.5 对话上下文管理

```
- 维护一个 conversation_buffer，存储最近 N 轮对话
- 每次用户输入先判断: 是"新任务"还是"对上一轮的补充"？
- 判断方式: LLM 快速分类（新任务 / 补充 / 无关对话）
- 确认是最终任务后，将完整上下文一起送给解析 Prompt
```

### 1.6 追问澄清机制

```
澄清维度:
  1. 范围不明确 → "你想重构整个模块还是某个函数？"
  2. 目标不明确 → "优化是指性能、可读性还是其他？"
  3. 约束不明确 → "有没有限制不能改接口？"
  4. 上下文缺失 → "你说的'那个接口'具体是哪个？"

追问规则:
  - 最多追问 3 轮，超过则给出默认假设并告知用户
  - 每次只问 1-2 个问题，避免信息过载
  - ★ 提供选项让用户快速选择（用户往往不知道需要澄清什么）
    例: "请确认操作范围: [1] 整个项目  [2] src/ 目录  [3] 仅当前文件"

MVP 阶段: MVP 不做任务类型分类，直接解析目标+约束+成功标准
```

### 1.7 置信度规则

```
- confidence >= 0.8 → 高置信，直接执行
- 0.5 <= confidence < 0.8 → 中置信，展示计划让用户确认
- confidence < 0.5 → 低置信，追问澄清
- 该阈值可通过配置调整
```

### 1.8 危险操作识别

```
红色（必须确认）:
  - 文件删除 (rm, del, 覆盖写入)
  - Shell 危险命令 (rm -rf, format, mkfs, :(){ :|:& };:)
  - 数据库 DROP / TRUNCATE

黄色（建议确认）:
  - 批量文件修改
  - 网络请求（对外部有副作用）

绿色（自动执行）:
  - 文件读取
  - 代码分析
  - 搜索操作
```

### 1.9 LLM 解析 Prompt 设计

```
System Prompt 结构:
  角色设定 → 你是任务解析专家
  任务说明 → 从用户输入中提取结构化信息
  输出格式 → JSON Schema 约束
  示例     → Few-shot 示范
  置信度规则 → 何时标记低置信

输出 Schema:
{
  "goal": "清晰的任务目标描述",
  "constraints": ["约束1", "约束2"],
  "success_criteria": ["标准1"],
  "context_files": ["path1"],
  "confidence": 0.0 ~ 1.0,
  "clarification_needed": "需澄清的问题（若无则为空）",
  "clarification_options": ["选项1", "选项2"]   # 供用户选择
}
```

### 1.10 LLM 解析异常处理

```
- LLM 返回 JSON 格式错误 → 重试 1 次，仍失败则降级为原始文本
- LLM 调用超时 → 提示网络问题，让用户重试
- LLM 返回空/无意义 → 视为低置信，进入澄清流程
```

---

## 二、经验回顾

> MVP 阶段决策：代码结构预留经验库接口，MVP 阶段返回空列表

### 2.1 未来完整流程

```
输入: 结构化 Task 对象
输出: 相关经验列表（可能为空）

子流程:
  1. 从经验库检索相似任务
     - 按任务描述相似度匹配
     - 按工具使用模式匹配
     - 按失败模式匹配
  2. 若有成功经验 → 提取可复用策略
  3. 若有失败经验 → 提取避坑指南
  4. 将经验作为提示注入后续步骤
```

---

## 三、步骤拆解

### 3.1 拆解策略

```
拆解原则:
  1. 原子性 — 每步只做一件事，便于独立评估和重试
  2. 有序性 — 有依赖关系的步骤按序排列
  3. 可回退 — 每步失败不影响全局
  4. 工具对齐 — 每步应能映射到一个具体工具

拆解粒度:
  - 太粗 → 一步包含多个操作，失败难以定位
  - 太细 → 步骤过多，LLM 调用成本高
  - 适中 → 一般 3-8 步，最多不超过 max_steps
```

### 3.2 拆解流程

```
结构化 Task + 经验提示
        │
        ▼
┌──────────────────────────┐
│ 1. 构建拆解 Prompt        │
│ (7 层组装，见 3.10)       │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ 2. LLM 拆解              │
│ 输出 Step 列表            │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ 3. 质量校验               │
│ - 完整性校验 (3.3.1)      │
│ - 工具可用性校验 (3.3.2)  │──→ 不足 → 动态生成临时工具
│ - 循环依赖检测 (3.3.3)    │
│ - 孤立步骤检测 (3.3.4)    │
│ - 可执行性校验 (3.3.5)    │
│ 不通过 → 让 LLM 修正(1次) │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ 4. 步骤排序               │
│ - 拓扑排序 (依赖优先)      │
│ - 关键步骤优先            │
│ - 轻量操作优先            │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ 5. 步骤数校验             │
│ 超限 → 合并步骤 (3.5)     │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ 6. 置信度判断             │
│ 中低置信 → 展示计划确认    │
│ 高置信 → 直接执行         │
└────────┬─────────────────┘
         │
         ▼
    最终 Step 列表
    （附带 context_store 准备就绪）
```

### 3.3 质量校验

#### 3.3.1 完整性检查

```
问题: 所有步骤完成后能否达成目标？

校验方式:
  1. 让 LLM 做一次"反向验证"
     输入: 拆解结果 + 原始目标
     Prompt: "以下步骤完成后是否足以达成目标？
             若不足，缺少什么？"
  2. 检查最后一步的输出是否匹配 success_criteria
  3. 检查是否存在"中间断层"（某步输出未被后续使用）

不通过 → 让 LLM 补充缺失步骤（最多 1 次）
```

#### 3.3.2 工具可用性检查

```
遍历每个 step.tool_hint:
  - 在已注册工具列表中查找
  - 找到 → 通过
  - 未找到 → 尝试用现有工具组合替代
  - 无法替代 → 触发动态工具生成流程 (3.6)
  - 动态工具也失败 → 标记步骤为 "needs_user_help"
```

#### 3.3.3 循环依赖检测

```
算法: 拓扑排序

  1. 构建有向图（step → depends_on）
  2. 尝试拓扑排序
  3. 排序失败 → 存在循环依赖
  4. 定位环 → 让 LLM 修正依赖关系

示例:
  step_1 depends_on [step_3]
  step_2 depends_on [step_1]
  step_3 depends_on [step_2]
  → 环: step_1 → step_3 → step_2 → step_1
```

#### 3.3.4 孤立步骤检测

```
孤立步骤特征:
  - 没有步骤依赖它（非最后一步）
  - 它也不依赖任何其他步骤（非第一步）
  - 描述与目标无关

检测:
  - 遍历所有步骤，检查 depends_on 引用关系
  - 第一步和最后一步豁免
  - 其余步骤必须至少被一个后续步骤引用
```

#### 3.3.5 步骤可执行性检查

```
问题: 每步描述是否足够具体，能被执行引擎理解？

校验方式:
  - 检查 description 是否包含具体操作对象
    ❌ "处理配置文件" → 太模糊
    ✅ "读取 config/app.yaml 中的 database 配置"
  - 检查是否有明确的输入来源
    - 第一步: 必须自带输入或从 Task context 获取
    - 后续步骤: 必须有 depends_on 或 input_from
  - 检查 tool_hint 是否与 description 匹配
    ❌ description="分析代码" + tool_hint="shell" → 不匹配
    ✅ description="运行测试" + tool_hint="shell" → 匹配
```

### 3.4 步骤间数据传递

```
每步增加字段:
  - input_from: 从哪些步骤获取输入数据
  - input_format: 期望的输入数据格式
  - output_format: 该步骤输出的数据格式

中间结果存储（ContextStore）:
  - Step 执行完后将结果存入 context_store
  - 后续步骤通过引用 key 获取数据

示例:
  Step 1: 搜索配置文件 → output_format: file_list
  Step 2: 读取配置文件 → input_from: [step_1], input_format: file_path
```

### 3.5 步骤合并策略

```
触发条件: 步骤数超过 max_steps

合并优先级:
  1. 合并同类操作
     例: "读取文件 A" + "读取文件 B" → "读取文件 A 和 B"
  2. 合并紧邻的无依赖步骤
     例: "搜索 X" + "搜索 Y" → "搜索 X 和 Y"
  3. 合并非关键步骤
     is_critical=false 的步骤优先被合并

不合并原则:
  - 关键步骤不合并
  - 有外部依赖的步骤不合并
  - 读操作和写操作不合并
```

### 3.6 动态工具生成

```
触发条件: 某步骤没有合适工具，或现有工具组合仍无法满足

流程:
  1. LLM 分析缺口 — "需要做什么？缺什么能力？"
  2. LLM 生成 Python 函数 — 包含函数签名、docstring、实现
  3. 安全审查 — 检查函数是否包含危险操作
  4. 用户确认 — 展示生成的代码，询问是否允许执行
  5. 注册为临时工具 — 注入当前任务的工具链
  6. 执行该步骤
  7. 任务结束后可选择保留或丢弃该工具
```

### 3.7 工具不足时的处理策略

```
执行优先级:
  1. 用现有工具完成
  2. 用现有工具组合完成
  3. 动态生成临时工具完成
  4. 调整任务范围（收缩目标）
  5. 以上都失败 → 抛出给用户，附详细原因和建议

不再简单标记 "unsupported" 就跳过，而是尝试自救。
```

### 3.8 条件分支步骤

```
MVP 支持条件分支：根据某步结果决定下一步。

数据结构:
  is_branch_point: true            # 标记为分支判断点
  branch_condition: str            # 条件描述
  true_next: list[str]            # 条件满足时的下一步
  false_next: list[str]           # 条件不满足时的下一步

执行引擎处理:
  1. 执行到 is_branch_point=true 的步骤
  2. 根据该步骤结果评估 branch_condition
  3. 满足 → 执行 true_next 中的步骤
  4. 不满足 → 执行 false_next 中的步骤
  5. 未被选中的分支 → 标记为 skipped

示例:
  Step 1: 检查服务状态          (is_branch_point=true)
    branch_condition: "服务返回码不为 0 或日志中包含 ERROR"
    true_next: [step_2]         # 有报错 → 进入修复
    false_next: [step_4]        # 无报错 → 直接完成

  Step 2: 分析并修复报错         (depends_on: step_1)
  Step 3: 验证修复结果           (depends_on: step_2)
  Step 4: 完成任务               (depends_on: step_1)
```

### 3.9 循环迭代步骤

```
MVP 支持循环步骤：对集合中每个元素执行相同操作。

数据结构:
  is_loop: true                      # 标记为循环步骤
  loop_input_step: str              # 循环数据源步骤 ID
  loop_item_variable: str           # 循环项变量名（用于 description 替换）

执行引擎处理:
  1. 从 loop_input_step 结果拿到集合数据
  2. 对每个元素执行一次该步骤（替换 description 中的变量）
  3. 累积所有循环迭代的结果
  4. 将累积结果作为该步骤的最终输出

示例:
  Step 1: 搜索所有 .py 文件         (output_format: file_list)
  Step 2: 检查 {file} 的 import     (is_loop=true, loop_input_step: step_1)
  Step 3: 汇总检查结果              (depends_on: step_2)
```

### 3.10 LLM 拆解 Prompt 设计

#### 3.10.1 Prompt 组装顺序

```
第 1 层 — 角色 + 任务说明
  "你是一个软件工程任务规划专家，
   你的职责是将用户任务拆解为可执行的步骤。"

第 2 层 — 可用工具清单（动态生成）
  "当前可用工具:
   - file: 读取/写入/搜索文件
   - shell: 执行 Shell/PowerShell 命令
   - code: 分析/生成/修改代码
   - search: 语义搜索代码库"
  ← 若有动态工具，实时追加

第 3 层 — 拆解规则
  "拆解时必须遵守:
   1. 每步只做一件事
   2. 每步必须能映射到上述工具之一
   3. 步骤间用 depends_on 表达依赖
   4. 关键步骤标记 is_critical=true
   5. 条件判断步骤标记 is_branch_point=true
   6. 循环操作使用 is_loop=true"

第 4 层 — 经验提示（动态注入）
  "历史经验:
   - 类似任务通常需要 4-6 步
   - 注意: 该项目配置文件在 config/ 目录下"

第 5 层 — Few-shot 示例
  提供 2-3 个完整拆解示例（见 3.11）

第 6 层 — 当前任务
  "现在请拆解以下任务:
   目标: {goal}
   约束: {constraints}
   成功标准: {success_criteria}
   上下文: {context}"

第 7 层 — 输出格式约束
  "请严格按以下 JSON Schema 输出: ..."
```

#### 3.10.2 输出 JSON Schema

```json
{
  "steps": [
    {
      "step_id": "string",                    // 唯一标识
      "description": "string",                // 具体操作描述
      "tool_hint": "string",                 // 工具类型
      "depends_on": ["string"],              // 依赖的上游步骤
      "is_critical": true,                   // 是否关键步骤
      "is_branch_point": false,              // 是否为条件分支点
      "is_loop": false,                      // 是否为循环步骤
      "branch_condition": null,              // 分支条件（仅 branch_point 有效）
      "true_next": [],                       // 条件满足时的下一步
      "false_next": [],                      // 条件不满足时的下一步
      "loop_input_step": null,               // 循环数据源步骤 ID
      "loop_item_variable": null,            // 循环项变量名
      "expected_output": "string",           // 期望结果描述
      "output_format": "string",             // 输出数据格式
      "input_from": [],                      // 从哪些步骤获取输入
      "input_format": "string"               // 期望的输入数据格式
    }
  ],
  "reasoning": "string",                     // 拆解思路说明
  "estimated_steps": 5                       // 预估总步数
}
```

#### 3.10.3 数据格式枚举

```
output_format / input_format 可选值:

  基础类型:
    - text          纯文本
    - json          JSON 数据
    - boolean       布尔值（条件分支常用）
    - number        数字

  文件相关:
    - file_path     单个文件路径
    - file_list     文件路径列表
    - file_content  文件内容

  代码相关:
    - code          代码片段
    - diff          代码差异

  命令相关:
    - command       Shell 命令字符串
    - command_output 命令执行输出

  混合类型:
    - structured    结构化文本（带格式的非 JSON）
    - mixed         混合格式（由执行引擎自动解析）
```

### 3.11 Few-shot 示例

#### 示例 1 — 简单任务

```
输入: "查看当前目录结构"

输出:
{
  "steps": [
    {
      "step_id": "step_1",
      "description": "列出当前工作目录下的所有文件和文件夹",
      "tool_hint": "shell",
      "depends_on": [],
      "is_critical": true,
      "is_branch_point": false,
      "is_loop": false,
      "expected_output": "目录树形结构",
      "output_format": "text",
      "input_from": [],
      "input_format": null
    }
  ],
  "reasoning": "单步任务，直接列出目录即可",
  "estimated_steps": 1
}
```

#### 示例 2 — 条件分支任务

```
输入: "检查服务是否正常，有报错就修复"

输出:
{
  "steps": [
    {
      "step_id": "step_1",
      "description": "检查服务运行状态和日志",
      "tool_hint": "shell",
      "depends_on": [],
      "is_critical": true,
      "is_branch_point": true,
      "is_loop": false,
      "branch_condition": "服务返回码不为 0 或日志中包含 ERROR",
      "true_next": ["step_2"],
      "false_next": ["step_4"],
      "expected_output": "服务状态信息",
      "output_format": "text",
      "input_from": [],
      "input_format": null
    },
    {
      "step_id": "step_2",
      "description": "分析报错原因",
      "tool_hint": "code",
      "depends_on": ["step_1"],
      "is_critical": true,
      "is_branch_point": false,
      "is_loop": false,
      "expected_output": "报错原因分析",
      "output_format": "text",
      "input_from": ["step_1"],
      "input_format": "text"
    },
    {
      "step_id": "step_3",
      "description": "根据分析结果修复问题",
      "tool_hint": "file",
      "depends_on": ["step_2"],
      "is_critical": true,
      "is_branch_point": false,
      "is_loop": false,
      "expected_output": "修复后的文件",
      "output_format": "text",
      "input_from": ["step_2"],
      "input_format": "text"
    },
    {
      "step_id": "step_4",
      "description": "确认任务完成",
      "tool_hint": "shell",
      "depends_on": ["step_1", "step_3"],
      "is_critical": false,
      "is_branch_point": false,
      "is_loop": false,
      "expected_output": "任务完成确认",
      "output_format": "text",
      "input_from": [],
      "input_format": null
    }
  ],
  "reasoning": "先检查服务，有报错就分析修复，无报错直接完成",
  "estimated_steps": 3
}
```

#### 示例 3 — 循环迭代任务

```
输入: "遍历项目所有 .py 文件，检查是否有未使用的 import"

输出:
{
  "steps": [
    {
      "step_id": "step_1",
      "description": "搜索项目中所有 .py 文件",
      "tool_hint": "search",
      "depends_on": [],
      "is_critical": true,
      "is_branch_point": false,
      "is_loop": false,
      "expected_output": "Python 文件路径列表",
      "output_format": "file_list",
      "input_from": [],
      "input_format": null
    },
    {
      "step_id": "step_2",
      "description": "检查 {file} 中是否有未使用的 import",
      "tool_hint": "code",
      "depends_on": ["step_1"],
      "is_critical": false,
      "is_branch_point": false,
      "is_loop": true,
      "loop_input_step": "step_1",
      "loop_item_variable": "file",
      "expected_output": "该文件的未使用 import 列表",
      "output_format": "json",
      "input_from": ["step_1"],
      "input_format": "file_path"
    },
    {
      "step_id": "step_3",
      "description": "汇总所有文件的检查结果，生成报告",
      "tool_hint": "code",
      "depends_on": ["step_2"],
      "is_critical": false,
      "is_branch_point": false,
      "is_loop": false,
      "expected_output": "未使用 import 汇总报告",
      "output_format": "text",
      "input_from": ["step_2"],
      "input_format": "json"
    }
  ],
  "reasoning": "先收集文件列表，再逐个检查，最后汇总",
  "estimated_steps": 3
}
```

### 3.12 拆解失败兜底策略

```
LLM 拆解可能失败的情况:

  1. JSON 格式错误
     → 重试 1 次，仍失败则降级为原始文本描述

  2. 拆解结果校验不通过
     → 让 LLM 修正（带上校验失败的详细信息）
     → 最多修正 1 次

  3. 修正后仍不通过
     → 降级为"单步任务"（整个任务作为 1 个步骤）
     → 标记为低置信，需要用户确认

  4. LLM 调用本身失败（网络/超时）
     → 提示用户检查网络
     → 不进入降级，等待用户重试
```

### 3.13 用户展示格式

```
仅中低置信任务展示计划确认：

  📋 任务计划
  目标: 将数据库连接从 MySQL 迁移到 PostgreSQL

  步骤:
  1. [搜索] 查找所有数据库配置文件
  2. [读取] 读取配置文件内容
  3. [搜索] 查找 MySQL 相关代码
  4. [修改] 更新配置文件为 PostgreSQL
  5. [修改] 更新代码中的 MySQL 语法
  6. [修改] 更新依赖文件
  7. [测试] 运行项目测试验证

  ⚠️ 注意: 此任务涉及 4 处文件修改
  预计步骤: 7 步

  是否开始执行？ [Y/n]
```

---

## 四、数据结构

```python
Task {
  id: str
  goal: str
  constraints: list[str]
  success_criteria: list[str]
  context: str
  status: "pending" | "running" | "done" | "failed" | "cancelled"
  confidence: float
  conversation_history: list[ConversationTurn]
}

Step {
  id: str
  task_id: str
  description: str
  tool_hint: str
  depends_on: list[str]
  expected_output: str
  status: "pending" | "running" | "done" | "failed" | "skipped" | "unsupported"
  is_critical: bool
  is_branch_point: bool                 # 是否为条件分支点
  is_loop: bool                        # 是否为循环步骤
  branch_condition: str | None         # 分支条件描述
  true_next: list[str]                 # 条件满足时的下一步
  false_next: list[str]                # 条件不满足时的下一步
  loop_input_step: str | None          # 循环数据源步骤 ID
  loop_item_variable: str | None       # 循环项变量名
  input_from: list[str]
  input_format: str                    # 期望的输入数据格式
  output_format: str                   # 输出的数据格式
}

StepResult {
  step_id: str
  tool_used: str
  output: str
  error: str | None
  success: bool
  retry_count: int
  duration_ms: int
}

ContextStore {
  task_id: str
  data: dict[str, any]    # key: step_id, value: 该步输出结果
}

ConversationTurn {
  role: "user" | "agent"
  content: str
  timestamp: datetime
}

Experience {
  id: str
  task_type: str
  tool_chain: list[str]
  pattern: str
  lesson: str
  score: float                # -1.0 ~ 1.0
  created_at: datetime
}
```

---

## 五、MVP 阶段决策汇总

| 设计点 | 决策 |
|-------|------|
| 任务类型分类 | MVP 不做，直接解析目标+约束+成功标准 |
| 经验回顾 | 预留接口，MVP 返回空列表 |
| 工具扩展 | 支持动态生成临时工具 |
| 部分完成策略 | Agent 尽力自救，彻底无法解决才抛给用户 |
| 确认机制 | 危险操作必须确认，复杂任务建议确认，简单任务自动执行 |
| 追问澄清 | 提供选项让用户选择，最多 3 轮 |
| 步骤并行 | MVP 暂不实现，按序执行 |
| 条件分支 | MVP 支持，执行引擎根据条件自动跳步 |
| 循环迭代 | MVP 支持，循环步骤对集合元素逐个执行 |
| 计划确认 | 仅中低置信任务展示计划让用户确认 |
