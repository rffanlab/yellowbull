"""步骤执行器

负责执行单步、条件分支、循环迭代。
所有执行操作通过 LLM 驱动 + 工具调用完成。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.agent.context_store import ContextStore as LegacyContextStore
from yellowbull.agent.step_state import ContextStore, StepState
from yellowbull.agent.guard import BudgetGuard
from yellowbull.llm.client import LLMClient
from yellowbull.models.result import StepResult
from yellowbull.models.step import Step, StepStatus
from yellowbull.tools.base import Tool, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


# tool_hint → 工具名称映射
_TOOL_HINT_MAP = {
    "file": "file_tool",
    "shell": "shell_tool",
    "code": "code_tool",
    "search": "search_tool",
}


class StepResultData(BaseModel):
    """单步执行结果"""

    step_id: str = Field(description="步骤 ID")
    success: bool = Field(description="是否成功")
    result: Any = Field(default=None, description="执行结果")
    error: str | None = Field(default=None, description="错误信息")
    tool_used: str = Field(default="", description="使用的工具")
    duration_ms: int = Field(default=0, description="耗时毫秒")


class BranchResult(BaseModel):
    """条件分支执行结果"""

    condition_met: bool = Field(description="条件是否满足")
    activated_steps: list[str] = Field(default_factory=list, description="激活的步骤 ID 列表")
    skipped_steps: list[str] = Field(default_factory=list, description="跳过的步骤 ID 列表")


class LoopResult(BaseModel):
    """循环执行结果"""

    iterations: int = Field(description="迭代次数")
    success_count: int = Field(default=0, description="成功次数")
    failed_count: int = Field(default=0, description="失败次数")
    results: list[Any] = Field(default_factory=list, description="迭代结果列表")


class StepExecutor:
    """单步执行器"""

    def __init__(
        self,
        context_store: ContextStore,
        llm_client: LLMClient,
        step_timeout: int = 120,
    ):
        self.context_store = context_store
        self.llm_client = llm_client
        self.step_timeout = step_timeout

    async def execute(self, step: Step) -> StepResultData:
        """执行单步

        1. 前置检查: depends_on 全部 done/skipped
        2. 收集输入数据: 从 context_store 按 input_from 取数据
        3. 格式校验: 按 input_format 校验
        4. 工具路由: tool_hint → 匹配工具
        5. 构建执行 Prompt
        6. 调用工具执行 (timeout=120s)
        7. 结果处理: 成功存入 context_store，失败返回错误
        """
        start_time = time.time()

        try:
            # 1. 收集输入
            inputs = self._collect_inputs(step)

            # 2. 格式校验
            ok, err = self._validate_input_format(inputs, step.input_format)
            if not ok:
                return StepResultData(
                    step_id=step.step_id,
                    success=False,
                    error=f"输入格式校验失败: {err}",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # 3. 工具路由
            tool = self._resolve_tool(step.tool_hint)
            if tool is None:
                return StepResultData(
                    step_id=step.step_id,
                    success=False,
                    error=f"无法解析工具: {step.tool_hint}",
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # 4. 构建执行 Prompt
            system_prompt, user_prompt = self._build_execution_prompt(
                step, inputs, tool
            )

            # 5. 调用 LLM 获取执行参数
            llm_response = await self.llm_client.chat(system_prompt, [user_prompt])

            # 6. 执行工具
            result = await self._invoke_tool(tool, llm_response, self.step_timeout)

            # 7. 存储结果
            if result.success:
                self.context_store.set(step.step_id, result.output)

            return StepResultData(
                step_id=step.step_id,
                success=result.success,
                result=result.output,
                error=result.error,
                tool_used=tool.name,
                duration_ms=int((time.time() - start_time) * 1000),
            )

        except asyncio.TimeoutError:
            return StepResultData(
                step_id=step.step_id,
                success=False,
                error=f"步骤执行超时 ({self.step_timeout}s)",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        except Exception as e:
            logger.error("步骤 %s 执行异常: %s", step.step_id, e)
            return StepResultData(
                step_id=step.step_id,
                success=False,
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

    def _collect_inputs(self, step: Step) -> dict:
        """从 context_store 收集输入数据"""
        inputs = {}
        for src_id in step.input_from:
            data = self.context_store.get(src_id)
            if data is not None:
                inputs[src_id] = data
        return inputs

    def _validate_input_format(
        self,
        inputs: dict,
        expected_format: str | None,
    ) -> tuple[bool, str | None]:
        """校验输入格式

        MVP 仅支持基础类型转换
        """
        if not expected_format:
            return True, None

        for key, value in inputs.items():
            if expected_format == "json" and not isinstance(value, (dict, list)):
                try:
                    import json
                    json.loads(str(value))
                except (json.JSONDecodeError, TypeError):
                    return False, f"输入 {key} 格式应为 JSON，实际为 {type(value).__name__}"

            elif expected_format == "code" and not isinstance(value, str):
                return False, f"输入 {key} 格式应为代码文本"

        return True, None

    def _resolve_tool(self, tool_hint: str) -> Tool | None:
        """根据 tool_hint 解析工具"""
        tool_name = _TOOL_HINT_MAP.get(tool_hint)
        if tool_name:
            return ToolRegistry.get(tool_name)
        # 直接尝试 tool_hint 作为工具名
        return ToolRegistry.get(tool_hint)

    def _build_execution_prompt(
        self,
        step: Step,
        inputs: dict,
        tool: Tool,
    ) -> tuple[str, str]:
        """构建执行 Prompt"""
        system_prompt = (
            f"你是一个任务执行助手。请使用工具 '{tool.name}' 执行以下操作。\n"
            f"工具说明: {tool.description}\n"
        )

        if step.expected_output:
            system_prompt += f"期望输出: {step.expected_output}\n"

        user_prompt = f"任务: {step.description}\n"

        if inputs:
            user_prompt += "输入数据:\n"
            for key, value in inputs.items():
                user_prompt += f"  - {key}: {value}\n"

        user_prompt += f"\n请返回执行参数（JSON 格式）。"

        return system_prompt, user_prompt

    async def _invoke_tool(
        self,
        tool: Tool,
        response: str,
        timeout: int,
    ) -> ToolResult:
        """调用工具执行"""
        try:
            import json
            params = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            params = {"command": response}

        try:
            result = await asyncio.wait_for(
                tool.execute(params),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                error=f"工具执行超时 ({timeout}s)",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"工具执行失败: {e}",
            )

    # ========== 条件分支执行 ==========

    async def execute_branch(self, step: Step) -> BranchResult:
        """执行条件分支步骤

        1. 正常执行该步骤（如"检查服务状态"）
        2. LLM 评估 branch_condition
        3. 根据结果标记 true_next/false_next 为 pending/skipped
        """
        # 1. 先执行步骤
        step_result = await self.execute(step)

        if not step_result.success:
            return BranchResult(
                condition_met=False,
                activated_steps=[],
                skipped_steps=step.true_next + step.false_next,
            )

        # 2. 评估分支条件
        condition_met = False
        if step.branch_condition:
            condition_met = await self._evaluate_branch_condition(
                step.branch_condition, step_result.result
            )

        # 3. 标记分支
        activated = []
        skipped = []

        if condition_met:
            activated = step.true_next or []
            skipped = step.false_next or []
        else:
            activated = step.false_next or []
            skipped = step.true_next or []

        return BranchResult(
            condition_met=condition_met,
            activated_steps=activated,
            skipped_steps=skipped,
        )

    async def _evaluate_branch_condition(
        self,
        condition: str,
        step_result: Any,
    ) -> bool:
        """使用 LLM 评估分支条件"""
        system_prompt = "你是一个条件评估助手。请根据提供的信息判断条件是否满足。只回答 true 或 false。"
        user_prompt = (
            f"以下条件是否满足？\n"
            f"条件: {condition}\n"
            f"依据: {step_result}\n"
            f"请回答 true 或 false。"
        )

        try:
            response = await self.llm_client.chat(system_prompt, [user_prompt])
            return "true" in response.lower().strip()
        except Exception as e:
            logger.warning("分支条件评估失败，默认 false: %s", e)
            return False

    # ========== 循环迭代执行 ==========

    async def execute_loop(
        self,
        loop_step: Step,
        step_states: dict[str, StepState],
        budget_guard: BudgetGuard | None = None,
        max_iterations: int = 50,
    ) -> LoopResult:
        """执行循环步骤

        1. 从 context_store 取 loop_input_step 的结果
        2. 校验结果是否为可迭代集合
        3. 遍历集合元素，逐个执行
        4. 检查全局保护（预算/超时）
        5. 累积结果存入 context_store
        """
        if not loop_step.loop_input_step:
            return LoopResult(
                iterations=0,
                success_count=0,
                failed_count=0,
                results=[],
            )

        # 1. 获取循环输入
        loop_data = self.context_store.get(loop_step.loop_input_step)
        if loop_data is None:
            logger.warning(
                "循环步骤 %s 的输入步骤 %s 无输出数据",
                loop_step.step_id,
                loop_step.loop_input_step,
            )
            return LoopResult(
                iterations=0,
                success_count=0,
                failed_count=0,
                results=[],
            )

        # 2. 展开集合
        try:
            items = self._expand_loop_collection(loop_data)
        except Exception as e:
            logger.error("循环数据展开失败: %s", e)
            return LoopResult(
                iterations=0,
                success_count=0,
                failed_count=1,
                results=[],
            )

        if not items:
            return LoopResult(
                iterations=0,
                success_count=0,
                failed_count=0,
                results=[],
            )

        # 3. 遍历执行
        results = []
        success_count = 0
        failed_count = 0

        for idx, item in enumerate(items):
            # 检查迭代限制
            if idx >= max_iterations:
                logger.warning(
                    "循环步骤 %s 达到最大迭代次数 %d",
                    loop_step.step_id,
                    max_iterations,
                )
                break

            # 检查全局保护
            if budget_guard and not budget_guard.check().ok:
                logger.warning(
                    "循环步骤 %s 因全局保护终止: %s",
                    loop_step.step_id,
                    budget_guard.check().reason,
                )
                break

            # 执行单次迭代
            item_result = await self._execute_loop_iteration(
                loop_step, item, idx
            )
            results.append(item_result.result)

            if item_result.success:
                success_count += 1
            else:
                failed_count += 1

            if budget_guard:
                budget_guard.consume_step()

        return LoopResult(
            iterations=len(results),
            success_count=success_count,
            failed_count=failed_count,
            results=results,
        )

    def _expand_loop_collection(self, data: Any) -> list[Any]:
        """将循环输入展开为集合"""
        if isinstance(data, list):
            return data
        if isinstance(data, (set, tuple)):
            return list(data)
        if isinstance(data, dict):
            return list(data.values())
        # 单个值包装为列表
        return [data]

    async def _execute_loop_iteration(
        self,
        step: Step,
        item: Any,
        iteration_index: int,
    ) -> StepResultData:
        """执行单次循环迭代"""
        # 替换描述中的变量
        description = step.description
        var_name = step.loop_item_variable or "item"
        description = description.replace(f"{{{var_name}}}", str(item))
        description = description.replace("{index}", str(iteration_index))

        # 创建临时步骤
        iteration_step = Step(
            step_id=f"{step.step_id}_iter_{iteration_index}",
            description=description,
            tool_hint=step.tool_hint,
            depends_on=[],
            is_critical=False,
            expected_output=step.expected_output,
            output_format=step.output_format,
        )

        return await self.execute(iteration_step)
