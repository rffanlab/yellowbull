"""步骤拆解 Prompt 模板

用于将结构化 Task 拆解为可执行的 Step 列表。
采用 7 层 Prompt 组装：
1. 角色 + 任务说明
2. 可用工具清单
3. 拆解规则
4. 经验提示（若有）
5. Few-shot 示例
6. 当前任务信息
7. 输出格式约束
"""

_BREAKDOWN_SYSTEM_PROMPT = """\
你是一个任务拆解专家。将用户任务拆解为可执行的步骤序列。

## 可用工具

{tools_list}

## 拆解规则

1. 每个步骤必须对应一个可用工具（通过 tool_hint 指定）
2. 步骤之间可以存在依赖关系（depends_on）
3. 关键步骤标记 is_critical=true（失败则终止整个任务）
4. 步骤描述应具体、可执行
5. 简单任务 1-3 步，复杂任务 3-8 步
6. 避免循环依赖

## 经验提示

{experience_hint}

## Few-shot 示例

示例 1（简单任务）：
任务: "读取 src/main.py 文件"
步骤:
[
  {{
    "step_id": "step_1",
    "description": "读取 src/main.py 文件内容",
    "tool_hint": "file",
    "depends_on": [],
    "is_critical": true,
    "expected_output": "文件内容"
  }}
]

示例 2（复杂任务）：
任务: "重构用户认证模块"
步骤:
[
  {{
    "step_id": "step_1",
    "description": "分析用户认证模块的代码结构和依赖关系",
    "tool_hint": "code",
    "depends_on": [],
    "is_critical": true,
    "expected_output": "代码结构分析报告"
  }},
  {{
    "step_id": "step_2",
    "description": "读取认证模块相关测试文件",
    "tool_hint": "file",
    "depends_on": ["step_1"],
    "is_critical": false,
    "expected_output": "测试文件内容"
  }},
  {{
    "step_id": "step_3",
    "description": "执行重构修改",
    "tool_hint": "file",
    "depends_on": ["step_1", "step_2"],
    "is_critical": true,
    "expected_output": "重构后的代码"
  }},
  {{
    "step_id": "step_4",
    "description": "运行测试验证重构正确性",
    "tool_hint": "shell",
    "depends_on": ["step_3"],
    "is_critical": true,
    "expected_output": "测试结果"
  }}
]

## 输出格式

返回 JSON 对象，包含 steps 数组。每个步骤包含：
- step_id: 唯一标识（格式: step_N）
- description: 步骤描述
- tool_hint: 工具类型（file / shell / code / search）
- depends_on: 依赖的前置步骤 ID 列表
- is_critical: 是否关键步骤
- expected_output: 期望输出描述
- is_branch_point: 是否分支点（默认 false）
- is_loop: 是否循环步骤（默认 false）
- input_from: 输入来源步骤 ID 列表
"""


def _build_tools_list(tools: list) -> str:
    """格式化工具清单。"""
    if not tools:
        return "无可用工具"
    lines = []
    for tool in tools:
        desc = getattr(tool, "description", "")
        lines.append(f"- {tool.name}: {desc}")
    return "\n".join(lines)


def _build_experience_hint(experiences: list | None) -> str:
    """格式化经验提示。"""
    if not experiences:
        return "无相关经验。"
    lines = []
    for exp in experiences:
        pattern = getattr(exp, "pattern", "")
        lesson = getattr(exp, "lesson", "")
        score = getattr(exp, "score", 0)
        lines.append(f"- [{score:+.1f}] {pattern} → {lesson}")
    return "\n".join(lines)


def build_breakdown_prompt(
    task,
    tools: list,
    experiences: list | None = None,
    few_shot_examples: list | None = None,
) -> tuple[str, str]:
    """构建步骤拆解的 7 层 Prompt。

    Args:
        task: Task 对象（需有 goal, constraints, success_criteria 字段）
        tools: 可用工具列表
        experiences: 相关经验列表（可选）
        few_shot_examples: 示例列表（可选，内置示例已包含）

    Returns:
        (system_prompt, user_message)
    """
    # 组装 system prompt
    tools_list = _build_tools_list(tools)
    experience_hint = _build_experience_hint(experiences)
    system_prompt = _BREAKDOWN_SYSTEM_PROMPT.format(
        tools_list=tools_list,
        experience_hint=experience_hint,
    )

    # 组装 user message（当前任务信息 + 输出约束）
    goal = getattr(task, "goal", str(task))
    constraints = getattr(task, "constraints", [])
    success_criteria = getattr(task, "success_criteria", [])

    user_parts = [f"任务目标: {goal}"]

    if constraints:
        constraint_text = "\n".join(f"  - {c}" for c in constraints)
        user_parts.append(f"约束条件:\n{constraint_text}")

    if success_criteria:
        criteria_text = "\n".join(f"  - {c}" for c in success_criteria)
        user_parts.append(f"成功标准:\n{criteria_text}")

    user_parts.append("请拆解为步骤列表，输出 JSON 格式。")

    return system_prompt, "\n\n".join(user_parts)
