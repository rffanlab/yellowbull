"""步骤预校验

校验步骤列表的合法性：拓扑排序、孤立步骤、循环+分支互斥、嵌套循环检测。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.models.step import Step

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    """校验结果"""

    valid: bool = Field(description="是否校验通过")
    errors: list[str] = Field(default_factory=list, description="错误列表")
    sorted_steps: list[Step] = Field(default_factory=list, description="拓扑排序后的步骤")


class StepValidator:
    """步骤预校验"""

    @staticmethod
    def validate_steps(steps: list[Step]) -> ValidationResult:
        """校验所有步骤

        1. 重复 ID 检测
        2. 缺失依赖检测
        3. 拓扑排序 — 确保无循环依赖
        4. 孤立步骤检测 — 未连接任何依赖链的步骤
        5. 循环步骤 + 分支点互斥 — 不允许同时存在
        6. 嵌套循环检测 — 不允许循环嵌套循环
        """
        errors: list[str] = []

        # 1. 重复 ID 检测
        duplicate_errors = StepValidator._check_duplicate_ids(steps)
        errors.extend(duplicate_errors)

        # 2. 缺失依赖检测
        missing_errors = StepValidator._check_missing_dependencies(steps)
        errors.extend(missing_errors)

        if errors:
            return ValidationResult(valid=False, errors=errors, sorted_steps=steps)

        # 3. 拓扑排序
        sorted_steps, sort_errors = StepValidator._topological_sort(steps)
        errors.extend(sort_errors)

        # 4. 孤立步骤检测
        orphan_errors = StepValidator._detect_orphan_steps(steps)
        errors.extend(orphan_errors)

        # 5. 循环+分支互斥
        conflict_errors = StepValidator._check_loop_branch_conflict(steps)
        errors.extend(conflict_errors)

        # 6. 嵌套循环检测
        nested_errors = StepValidator._check_nested_loops(steps)
        errors.extend(nested_errors)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            sorted_steps=sorted_steps if not sort_errors else steps,
        )

    @staticmethod
    def _check_duplicate_ids(steps: list[Step]) -> list[str]:
        """检测重复的 step_id"""
        errors = []
        seen = {}
        for step in steps:
            if step.step_id in seen:
                errors.append(f"重复的步骤 ID: {step.step_id}")
            else:
                seen[step.step_id] = step
        return errors

    @staticmethod
    def _check_missing_dependencies(steps: list[Step]) -> list[str]:
        """检测缺失的依赖"""
        errors = []
        step_ids = {s.step_id for s in steps}
        for step in steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    errors.append(f"步骤 {step.step_id} 依赖不存在的步骤: {dep}")
        return errors

    @staticmethod
    def _topological_sort(
        steps: list[Step],
    ) -> tuple[list[Step], list[str]]:
        """对步骤做 Kahn 算法拓扑排序

        检测到环 → 返回错误
        """
        step_map = {s.step_id: s for s in steps}
        in_degree = {s.step_id: 0 for s in steps}
        adjacency: dict[str, list[str]] = {s.step_id: [] for s in steps}

        # 构建图
        for step in steps:
            for dep in step.depends_on:
                if dep in step_map:
                    adjacency[dep].append(step.step_id)
                    in_degree[step.step_id] += 1

        # Kahn 算法
        queue = deque(sid for sid, deg in in_degree.items() if deg == 0)
        result = []
        errors = []

        while queue:
            current = queue.popleft()
            result.append(current)
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(steps):
            errors.append(
                f"检测到循环依赖，无法完成拓扑排序。"
                f"已排序 {len(result)}/{len(steps)} 个步骤"
            )
            # 返回已排序的部分
            sorted_steps = [step_map[sid] for sid in result if sid in step_map]
            return sorted_steps, errors

        sorted_steps = [step_map[sid] for sid in result]
        return sorted_steps, errors

    @staticmethod
    def _detect_orphan_steps(steps: list[Step]) -> list[str]:
        """检测孤立步骤

        既没有 depends_on，也没有其他步骤 depends_on 它，且不是第一步
        """
        if not steps:
            return []

        errors = []
        step_ids = {s.step_id for s in steps}

        # 第一步（无依赖的步骤）不算孤立
        for step in steps:
            has_deps = bool(step.depends_on)
            is_depended_on = any(
                step.step_id in s.depends_on for s in steps if s.step_id != step.step_id
            )

            if not has_deps and not is_depended_on and steps.index(step) > 0:
                # 只有一个无依赖步骤是正常的
                root_count = sum(
                    1 for s in steps if not s.depends_on
                )
                if root_count > 1:
                    errors.append(
                        f"步骤 {step.step_id} 可能是孤立步骤：无依赖且未被其他步骤依赖"
                    )

        return errors

    @staticmethod
    def _check_loop_branch_conflict(steps: list[Step]) -> list[str]:
        """循环步骤不允许同时是分支点"""
        errors = []
        for step in steps:
            if step.is_loop and step.is_branch_point:
                errors.append(
                    f"步骤 {step.step_id} 同时标记为循环和分支点，不允许"
                )
        return errors

    @staticmethod
    def _check_nested_loops(steps: list[Step]) -> list[str]:
        """循环步骤的 depends_on 中不能有另一个循环步骤"""
        errors = []
        loop_steps = {s.step_id for s in steps if s.is_loop}

        for step in steps:
            if not step.is_loop:
                continue
            for dep in step.depends_on:
                if dep in loop_steps:
                    errors.append(
                        f"步骤 {step.step_id} 是循环步骤，但依赖了另一个循环步骤 {dep}，"
                        f"不允许嵌套循环"
                    )
        return errors
