"""步骤选择器

从 pending 步骤中选择下一步执行。
优先级规则：关键优先 → 读优先 → 拓扑序。
"""

from __future__ import annotations

import logging

from yellowbull.agent.step_state import StepState
from yellowbull.models.step import Step, StepStatus

logger = logging.getLogger(__name__)


# 读操作工具列表
_READ_TOOLS = {"file", "search"}


class StepSelector:
    """从 pending 步骤中选择下一步

    1. 过滤: pending + depends_on 满足 + 未被分支跳过
    2. 排序: 关键优先 → 读优先 → 拓扑序
    3. 返回最高优先级步骤或 None
    """

    def __init__(self, step_states: dict[str, StepState]):
        self.step_states = step_states

    def get_next(self, steps: list[Step]) -> Step | None:
        """选择下一步

        1. 过滤不可执行的步骤
        2. 按优先级排序
        3. 返回最高优先级步骤

        返回 None 表示无可执行步骤
        """
        candidates = [
            step for step in steps if self._can_execute(step)
        ]

        if not candidates:
            return None

        sorted_candidates = self._sort_by_priority(candidates)
        return sorted_candidates[0] if sorted_candidates else None

    def _can_execute(self, step: Step) -> bool:
        """检查步骤是否可执行

        - status == pending
        - depends_on 全部 done 或 skipped
        - 未被分支跳过
        """
        state = self.step_states.get(step.step_id)
        if state is None:
            return False

        if state.status != StepStatus.PENDING:
            return False

        # 检查依赖是否全部完成或跳过
        for dep_id in step.depends_on:
            dep_state = self.step_states.get(dep_id)
            if dep_state is None:
                continue
            if dep_state.status not in (StepStatus.DONE, StepStatus.SKIPPED):
                return False

        return True

    def _sort_by_priority(self, candidates: list[Step]) -> list[Step]:
        """排序规则

        1. is_critical=True 优先
        2. is_branch_point=True 优先
        3. is_loop=True 优先
        4. 读操作优先于写操作
        5. 拓扑序靠前的优先
        """
        return sorted(
            candidates,
            key=lambda s: (
                # 关键步骤排前面 (0 < 1)
                0 if s.is_critical else 1,
                # 分支点排前面
                0 if s.is_branch_point else 1,
                # 循环步骤排前面
                0 if s.is_loop else 1,
                # 读操作排前面
                0 if s.tool_hint in _READ_TOOLS else 1,
            ),
        )

    def _cascade_skip(self, steps: list[Step], failed_id: str) -> list[str]:
        """级联跳过: 当步骤的依赖 failed 时，递归将所有依赖它的步骤标记为 skipped

        返回: 被跳过的步骤 ID 列表
        """
        skipped = []

        def _skip_dependents(fail_id: str) -> None:
            for step in steps:
                if fail_id in step.depends_on:
                    state = self.step_states.get(step.step_id)
                    if state and state.status == StepStatus.PENDING:
                        state.mark_skipped(by_dependency=True)
                        skipped.append(step.step_id)
                        _skip_dependents(step.step_id)

        _skip_dependents(failed_id)
        return skipped

    def get_all_executable(self, steps: list[Step]) -> list[Step]:
        """获取所有当前可执行的步骤（用于并行场景）"""
        return [step for step in steps if self._can_execute(step)]
