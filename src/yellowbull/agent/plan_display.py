"""计划展示模块

仅中低置信任务展示计划确认：
1. 渲染步骤列表（含工具图标）
2. 显示危险操作警告
3. 等待用户确认
"""

from __future__ import annotations

from yellowbull.agent.receiver import DangerLevel
from yellowbull.models.step import Step
from yellowbull.models.task import Task

# 工具类型对应的显示标签
_TOOL_LABELS = {
    "file": "[文件]",
    "shell": "[终端]",
    "code": "[代码]",
    "search": "[搜索]",
}

_TOOL_ICONS = {
    "file": "📄",
    "shell": "⚙️",
    "code": "💻",
    "search": "🔍",
}

_DANGER_LABELS = {
    DangerLevel.RED: "⛔ 高危操作",
    DangerLevel.YELLOW: "⚠️ 注意操作",
    DangerLevel.GREEN: "",
}


class PlanDisplay:
    """任务计划展示器"""

    def render_plan(
        self,
        task: Task,
        steps: list[Step],
        danger_level: DangerLevel = DangerLevel.GREEN,
    ) -> str:
        """渲染任务计划文本。

        包含:
        - 目标描述
        - 步骤列表（带工具类型标签）
        - 危险操作警告（若有）
        - 预计步骤数
        - 确认提示
        """
        lines = []

        # 标题
        lines.append("=" * 50)
        lines.append("  任务执行计划")
        lines.append("=" * 50)

        # 目标
        lines.append(f"\n📌 任务目标: {task.goal}")

        if task.constraints:
            lines.append("\n📋 约束条件:")
            for c in task.constraints:
                lines.append(f"  - {c}")

        if task.success_criteria:
            lines.append("\n✅ 成功标准:")
            for s in task.success_criteria:
                lines.append(f"  - {s}")

        # 置信度
        confidence_labels = {
            (0.8, 1.0): "高",
            (0.5, 0.8): "中",
            (0.0, 0.5): "低",
        }
        confidence_text = "未知"
        for (lo, hi), label in confidence_labels.items():
            if lo <= task.confidence < hi:
                confidence_text = label
                break
        lines.append(f"\n📊 置信度: {confidence_text} ({task.confidence:.2f})")

        # 步骤列表
        lines.append(f"\n📝 执行步骤 (共 {len(steps)} 步):")
        lines.append("-" * 30)
        for i, step in enumerate(steps, 1):
            lines.append(self.render_step_line(i, step))

        # 危险警告
        warning = self.render_warning(danger_level, steps)
        if warning:
            lines.append("")
            lines.append(warning)

        # 确认提示
        lines.append("")
        lines.append("请输入 'y' 确认执行，或 'n' 取消。")
        lines.append("=" * 50)

        return "\n".join(lines)

    def render_step_line(self, index: int, step: Step) -> str:
        """渲染单行步骤: "[工具] 描述"。"""
        label = _TOOL_LABELS.get(step.tool_hint, f"[{step.tool_hint}]")
        critical_mark = " ★" if step.is_critical else ""
        deps = ""
        if step.depends_on:
            deps = f" (依赖: {', '.join(step.depends_on)})"

        return f"  {index}. {label} {step.description}{critical_mark}{deps}"

    def render_warning(
        self,
        danger_level: DangerLevel,
        steps: list[Step],
    ) -> str | None:
        """渲染危险操作警告。"""
        if danger_level == DangerLevel.GREEN:
            return None

        label = _DANGER_LABELS.get(danger_level, "")
        if not label:
            return None

        # 找出危险步骤
        danger_steps = []
        for step in steps:
            desc_lower = step.description.lower()
            if danger_level == DangerLevel.RED:
                if any(kw in desc_lower for kw in ["删除", "format", "drop", "truncate", "rm "]):
                    danger_steps.append(step.step_id)
            elif danger_level == DangerLevel.YELLOW:
                if any(kw in desc_lower for kw in ["安装", "install", "post", "网络"]):
                    danger_steps.append(step.step_id)

        lines = [f"\n{label}"]
        if danger_steps:
            lines.append(f"  涉及步骤: {', '.join(danger_steps)}")
            lines.append("  请仔细确认后再执行！")

        return "\n".join(lines)
