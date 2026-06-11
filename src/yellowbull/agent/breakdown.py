"""步骤拆解模块

将结构化 Task 拆解为可执行的 Step 列表。
包含：LLM 拆解、质量校验、步骤排序与合并、拆解兜底策略。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.config.settings import ExecutionSettings, Settings
from yellowbull.llm.client import LLMClient
from yellowbull.models.step import Step, StepStatus
from yellowbull.models.task import Task
from yellowbull.prompts.breakdown import build_breakdown_prompt
from yellowbull.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


# ==================== 质量校验 ====================

class ValidationReport(BaseModel):
    """校验报告"""

    is_valid: bool
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class StepBreakdown:
    """步骤拆解器"""

    def __init__(self, llm_client: LLMClient, settings: Settings):
        self._llm = llm_client
        self._settings = settings
        self._execution = settings.execution

    # --- T01-07: LLM 步骤拆解 ---

    async def breakdown(
        self,
        task: Task,
        experiences: list[Any] | None = None,
    ) -> list[Step]:
        """将任务拆解为步骤列表。

        流程:
        1. 构建拆解 Prompt（7 层组装）
        2. 调用 LLM 获取步骤列表
        3. 质量校验
        4. 步骤排序
        5. 步骤数校验
        """
        return await self._breakdown_with_fallback(task, experiences)

    async def _breakdown_with_fallback(
        self,
        task: Task,
        experiences: list[Any] | None = None,
    ) -> list[Step]:
        """拆解兜底流程。

        1. 正常 LLM 拆解
        2. JSON 格式错误 → 重试 1 次
        3. 校验不通过 → 让 LLM 修正（带校验失败详情）
        4. 修正仍不通过 → 降级为"单步任务"
        5. LLM 调用本身失败 → 不降级，抛异常等用户重试
        """
        # 第 1 次尝试
        try:
            steps = await self._llm_breakdown(task, experiences)
        except ValueError as e:
            # JSON 解析失败 → 重试 1 次
            logger.warning("JSON 解析失败，重试: %s", e)
            try:
                steps = await self._llm_breakdown(task, experiences)
            except ValueError as e:
                # 重试仍失败 → 降级为单步任务
                logger.warning("JSON 解析重试失败，降级为单步任务: %s", e)
                return self._degrade_to_single_step(task)
            except Exception as e:
                logger.error("LLM 拆解调用失败: %s", e)
                raise
        except Exception as e:
            logger.error("LLM 拆解调用失败: %s", e)
            raise

        # 校验
        report = self._validate_steps(steps, task)
        if report.is_valid:
            steps = self._sort_steps(steps)
            return self._merge_steps_if_needed(steps)

        # 校验失败 → 让 LLM 修正 1 次
        try:
            steps = await self._llm_fix_breakdown(task, report)
            report = self._validate_steps(steps, task)
            if report.is_valid:
                steps = self._sort_steps(steps)
                return self._merge_steps_if_needed(steps)
        except Exception:
            pass

        # 修正仍失败 → 降级为单步任务
        logger.warning("拆解校验修正失败，降级为单步任务")
        return self._degrade_to_single_step(task)

    async def _llm_breakdown(
        self,
        task: Task,
        experiences: list[Any] | None = None,
    ) -> list[Step]:
        """调用 LLM 进行步骤拆解。"""
        tools = ToolRegistry.list_all()
        system_prompt, user_message = build_breakdown_prompt(
            task=task,
            tools=tools,
            experiences=experiences,
        )

        raw_text = await self._llm.chat(
            system_prompt=system_prompt,
            user_messages=[user_message],
            json_mode=True,
        )

        return self._parse_steps_json(raw_text)

    async def _llm_fix_breakdown(
        self,
        task: Task,
        report: ValidationReport,
    ) -> list[Step]:
        """让 LLM 修正拆解结果。"""
        issues_text = "\n".join(f"- {issue}" for issue in report.issues)
        fix_prompt = (
            f"上次的拆解存在问题:\n{issues_text}\n\n"
            f"请修正这些问题，重新输出步骤列表的 JSON。"
        )

        tools = ToolRegistry.list_all()
        system_prompt, user_message = build_breakdown_prompt(
            task=task,
            tools=tools,
        )
        user_message += "\n\n" + fix_prompt

        raw_text = await self._llm.chat(
            system_prompt=system_prompt,
            user_messages=[user_message],
            json_mode=True,
        )

        return self._parse_steps_json(raw_text)

    def _parse_steps_json(self, raw_text: str) -> list[Step]:
        """解析 LLM 返回的 JSON 为 Step 列表。"""
        import json

        text = raw_text.strip()
        # 移除 markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"步骤拆解 JSON 解析失败: {e}") from e

        steps_data = data.get("steps", data if isinstance(data, list) else [])
        if not steps_data:
            raise ValueError("步骤拆解结果为空")

        steps = []
        for item in steps_data:
            step = Step(
                step_id=item.get("step_id", ""),
                description=item.get("description", ""),
                tool_hint=item.get("tool_hint", "file"),
                depends_on=item.get("depends_on", []),
                is_critical=item.get("is_critical", False),
                is_branch_point=item.get("is_branch_point", False),
                is_loop=item.get("is_loop", False),
                expected_output=item.get("expected_output", ""),
                input_from=item.get("input_from", []),
            )
            steps.append(step)

        return steps

    def _degrade_to_single_step(self, task: Task) -> list[Step]:
        """降级为单步任务。"""
        return [
            Step(
                step_id="step_1",
                description=task.goal,
                tool_hint="file",
                is_critical=True,
                expected_output="任务执行结果",
            )
        ]

    # --- T01-08: 质量校验 ---

    def _validate_steps(
        self,
        steps: list[Step],
        task: Task,
    ) -> ValidationReport:
        """校验拆解质量。"""
        issues = []
        suggestions = []

        # 1. 循环依赖检测
        if self._check_circular_dependency(steps):
            issues.append("检测到循环依赖")
            suggestions.append("请确保步骤依赖关系无环")

        # 2. 孤立步骤检测
        orphans = self._check_orphan_steps(steps)
        if orphans:
            issues.append(f"检测到孤立步骤: {', '.join(orphans)}")
            suggestions.append("请确保所有步骤都在依赖链中")

        # 3. 工具可用性检查
        unavailable_tools = self._check_tool_availability(steps)
        if unavailable_tools:
            issues.append(f"工具不可用: {', '.join(unavailable_tools)}")
            suggestions.append("请使用已注册的工具")

        # 4. 步骤 ID 唯一性
        ids = [s.step_id for s in steps]
        if len(ids) != len(set(ids)):
            issues.append("步骤 ID 不唯一")
            suggestions.append("请确保每个步骤有唯一的 step_id")

        # 5. 依赖引用有效性
        valid_ids = set(ids)
        for step in steps:
            for dep in step.depends_on:
                if dep not in valid_ids:
                    issues.append(f"步骤 {step.step_id} 引用了不存在的依赖 {dep}")

        return ValidationReport(
            is_valid=len(issues) == 0,
            issues=issues,
            suggestions=suggestions,
        )

    def _check_circular_dependency(self, steps: list[Step]) -> bool:
        """拓扑排序检测循环依赖。返回 True 表示有环。"""
        step_map = {s.step_id: s for s in steps}
        visited = set()
        rec_stack = set()

        def dfs(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            step = step_map.get(step_id)
            if step:
                for dep in step.depends_on:
                    if dep not in visited:
                        if dfs(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.discard(step_id)
            return False

        for step in steps:
            if step.step_id not in visited:
                if dfs(step.step_id):
                    return True
        return False

    def _check_orphan_steps(self, steps: list[Step]) -> list[str]:
        """检测孤立步骤（既不依赖其他步骤，也没有步骤依赖它，且不是第一步）。"""
        if len(steps) <= 1:
            return []

        all_ids = {s.step_id for s in steps}
        connected = set()

        for step in steps:
            connected.add(step.step_id)
            connected.update(step.depends_on)

        # 被其他步骤依赖的 ID
        depended_on = set()
        for step in steps:
            depended_on.update(step.depends_on)

        # 孤立 = 既不依赖别人也不被别人依赖（排除无依赖的第一步）
        orphans = []
        for step in steps:
            has_deps = bool(step.depends_on)
            is_depended = step.step_id in depended_on
            if not has_deps and not is_depended and step.step_id != steps[0].step_id:
                orphans.append(step.step_id)

        return orphans

    def _check_tool_availability(self, steps: list[Step]) -> list[str]:
        """检查每步的 tool_hint 是否有对应工具。"""
        unavailable = []
        for step in steps:
            matches = ToolRegistry.match_by_hint(step.tool_hint)
            if not matches:
                unavailable.append(step.tool_hint)
        return list(set(unavailable))

    # --- T01-09: 步骤排序与合并 ---

    def _sort_steps(self, steps: list[Step]) -> list[Step]:
        """拓扑排序 + 优先级。

        1. 关键步骤优先
        2. 读操作优先于写操作
        3. 拓扑序靠前的优先
        """
        if not steps:
            return steps

        # 拓扑排序
        step_map = {s.step_id: s for s in steps}
        in_degree = {s.step_id: 0 for s in steps}
        for step in steps:
            for dep in step.depends_on:
                if dep in in_degree:
                    in_degree[step.step_id] += 1

        # Kahn 算法
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        queue.sort(key=lambda sid: not step_map[sid].is_critical)  # 关键步骤优先
        sorted_ids = []

        while queue:
            # 关键步骤优先出队
            queue.sort(key=lambda sid: (not step_map[sid].is_critical, sid))
            current = queue.pop(0)
            sorted_ids.append(current)

            for step in steps:
                if current in step.depends_on:
                    in_degree[step.step_id] -= 1
                    if in_degree[step.step_id] == 0:
                        queue.append(step.step_id)

        # 如果拓扑排序未包含所有步骤（有环），追加剩余
        remaining = [s for s in steps if s.step_id not in sorted_ids]
        result = [step_map[sid] for sid in sorted_ids] + remaining
        return result

    def _merge_steps_if_needed(self, steps: list[Step]) -> list[Step]:
        """步骤数超过 max_steps 时合并。"""
        max_steps = self._execution.max_subtask_steps or 8
        if len(steps) <= max_steps:
            return steps

        # 保护关键步骤不被合并
        merged = []
        skip = set()

        for i, step in enumerate(steps):
            if i in skip:
                continue

            if step.is_critical:
                merged.append(step)
                continue

            # 尝试与下一步合并（同类 tool_hint 且紧邻）
            if i + 1 < len(steps):
                next_step = steps[i + 1]
                if (
                    not next_step.is_critical
                    and step.tool_hint == next_step.tool_hint
                    and not next_step.depends_on
                ):
                    # 合并
                    merged_step = Step(
                        step_id=f"{step.step_id}_merged",
                        description=f"{step.description}; {next_step.description}",
                        tool_hint=step.tool_hint,
                        depends_on=step.depends_on,
                        is_critical=False,
                        expected_output=next_step.expected_output or step.expected_output,
                    )
                    merged.append(merged_step)
                    skip.add(i + 1)
                    continue

            merged.append(step)

        # 如果仍然超过，直接截断（保留关键步骤）
        if len(merged) > max_steps:
            critical = [s for s in merged if s.is_critical]
            non_critical = [s for s in merged if not s.is_critical]
            merged = critical + non_critical[: max_steps - len(critical)]

        return merged
