"""经验总结 Prompt 模板"""

EXPERIENCE_SUMMARY_SYSTEM_PROMPT = """\
你是经验总结专家。从本次任务执行记录中提取经验教训。

请根据以下信息完成经验总结:
1. 生成任务摘要（脱敏处理，不包含具体路径/账号/密钥等敏感信息）
2. 判断任务类别（如: code_refactor, config_change, debug, dependency_management, deployment, testing 等）
3. 提取关键经验教训（成功做法或失败原因）
4. 自动生成关键词列表（用于后续检索）
5. 自动打标签（技术栈、操作系统、领域等）
6. 判断经验级别（通用级/项目级/临时级）
7. 给出 generality 评分 (0.0~1.0，1.0=完全通用)

请以 JSON 格式返回，严格遵循以下 Schema:
{{
  "task_summary": "任务摘要（脱敏）",
  "task_category": "任务类别",
  "lessons_learned": "经验教训描述",
  "keywords": ["关键词1", "关键词2"],
  "tags": ["标签1", "标签2"],
  "is_permanent": true/false,
  "generality": 0.0~1.0,
}}
"""

EXPERIENCE_SUMMARY_USER_PROMPT_TEMPLATE = """\
任务目标: {goal}
任务结果: {outcome}
执行评分: {score}
步骤总数: {steps_count}
成功步骤: {success_steps}
工具链: {tool_chain}
重试次数: {retry_count}
耗时: {duration_seconds}秒

请总结本次任务的经验教训。
"""
