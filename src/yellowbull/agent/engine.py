"""TaskEngine 主循环

执行引擎主入口：初始化 → 校验 → 主循环 → 完成/失败。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from yellowbull.agent.completion_evaluator import CompletionEvaluator, CompletionResult
from yellowbull.agent.execution_stack import ExecutionStack, TaskContext
from yellowbull.agent.failure_handler import FailureHandler
from yellowbull.agent.guard import BudgetGuard, GuardResult
from yellowbull.agent.executor import StepExecutor, StepResultData
from yellowbull.agent.obstacle_resolver import ObstacleResolver
from yellowbull.agent.step_selector import StepSelector
from yellowbull.agent.step_state import ContextStore, StepState, TaskState
from yellowbull.agent.validator import StepValidator, ValidationResult
from yellowbull.llm.client import LLMClient
from yellowbull.models.step import Step, StepStatus
from yellowbull.models.subtask import SubTask
from yellowbull.models.task import Task

logger = logging.getLogger(__name__)


class TaskRunResult(BaseModel):
    """任务执行结果"""

    task_id: str = Field(description="任务ID")
    success: bool = Field(description="是否成功")
    message: str = Field(default="", description="结果消息")
    steps_executed: int = Field(default=0, description="执行步骤数")
    steps_failed: int = Field(default=0, description="失败步骤数")
    steps_skipped: int = Field(default=0, description="跳过步骤数")
    context: dict = Field(default_factory=dict, description="执行上下文")


class TaskEngine:
    """执行引擎

    主循环:
    1. 初始化: 创建 step_states / context_store / guard
    2. 预校验: 校验步骤合法性
    3. 主循环:
       - 全局保护检查
       - 选择下一步
       - 执行步骤 (普通/分支/循环/子任务)
       - 失败处理
       - 完成评估
    4. 完成: 汇总结果
    """

    def __init__(
        self,
        llm_client: LLMClient,
        max_total_steps: int = 100,
        total_timeout: int = 1800,
        step_timeout: int = 120,
        max_retries: int = 3,
    ):
        self.llm_client = llm_client
        self.max_total_steps = max_total_steps
        self.total_timeout = total_timeout
        self.step_timeout = step_timeout
        self.max_retries = max_retries

    async def run(self, task: Task) -> TaskRunResult:
        """执行任务

        Args:
            task: 任务

        Returns:
            TaskRunResult
        """
        logger.info("开始执行任务: %s", task.id)

        # 1. 初始化
        step_states = self._init_step_states(task.steps)
        context_store = ContextStore(task_id=task.id)
        guard = BudgetGuard(
            max_total_steps=self.max_total_steps,
            total_timeout=self.total_timeout,
            step_timeout=self.step_timeout,
        )
        guard.start()

        # 2. 预校验
        validation = StepValidator.validate_steps(task.steps)
        if not validation.valid:
            logger.error("步骤校验失败: %s", validation.errors)
            return TaskRunResult(
                task_id=task.id,
                success=False,
                message=f"步骤校验失败: {'; '.join(validation.errors)}",
            )

        # 使用校验后的排序
        steps = validation.sorted_steps

        # 3. 初始化组件
        executor = StepExecutor(
            context_store=context_store,
            llm_client=self.llm_client,
            step_timeout=self.step_timeout,
        )
        selector = StepSelector(step_states=step_states)
        evaluator = CompletionEvaluator()
        obstacle_resolver = ObstacleResolver(llm_client=self.llm_client)
        failure_handler = FailureHandler(
            step_selector=selector,
            obstacle_resolver=obstacle_resolver,
            max_retries=self.max_retries,
        )

        # 4. 主循环
        try:
            result = await self._main_loop(
                task=task,
                steps=steps,
                step_states=step_states,
                context_store=context_store,
                guard=guard,
                executor=executor,
                selector=selector,
                evaluator=evaluator,
                failure_handler=failure_handler,
            )
            return result
        except Exception as e:
            logger.error("任务 %s 执行异常: %s", task.id, e)
            return TaskRunResult(
                task_id=task.id,
                success=False,
                message=f"执行异常: {e}",
            )

    def _init_step_states(self, steps: list[Step]) -> dict[str, StepState]:
        """初始化步骤状态"""
        return {step.step_id: StepState(step.step_id) for step in steps}

    async def _main_loop(
        self,
        task: Task,
        steps: list[Step],
        step_states: dict[str, StepState],
        context_store: ContextStore,
        guard: BudgetGuard,
        executor: StepExecutor,
        selector: StepSelector,
        evaluator: CompletionEvaluator,
        failure_handler: FailureHandler,
    ) -> TaskRunResult:
        """主循环"""
        while True:
            # 1. 全局保护检查
            guard_result = guard.check()
            if not guard_result.ok:
                logger.warning("全局保护触发: %s", guard_result.reason)
                return self._build_failure_result(
                    task, steps, step_states, context_store, guard_result.reason
                )

            # 2. 完成评估
            completion = evaluator.evaluate(steps, step_states)
            if completion.is_complete:
                logger.info("任务 %s 完成: %s", task.id, completion.reason)
                return TaskRunResult(
                    task_id=task.id,
                    success=completion.is_success,
                    message=completion.reason,
                    steps_executed=completion.done_steps,
                    steps_failed=completion.failed_steps,
                    steps_skipped=completion.skipped_steps,
                    context=context_store.to_dict(),
                )

            # 3. 选择下一步
            next_step = selector.get_next(steps)
            if next_step is None:
                logger.warning("无可执行步骤，任务可能已阻塞")
                return TaskRunResult(
                    task_id=task.id,
                    success=False,
                    message="无可执行步骤，任务阻塞",
                    steps_executed=completion.done_steps,
                    steps_failed=completion.failed_steps,
                    steps_skipped=completion.skipped_steps,
                )

            # 4. 执行步骤
            state = step_states[next_step.step_id]
            state.mark_running()

            try:
                if next_step.is_branch_point:
                    # 条件分支
                    branch_result = await executor.execute_branch(next_step)
                    if branch_result.condition_met:
                        state.mark_done(branch_result.activated_steps)
                    else:
                        state.mark_done(branch_result.skipped_steps)

                    # 标记跳过的步骤
                    for skip_id in branch_result.skipped_steps:
                        skip_state = step_states.get(skip_id)
                        if skip_state and skip_state.status == StepStatus.PENDING:
                            skip_state.mark_skipped(by_branch=True)

                elif next_step.is_loop:
                    # 循环迭代
                    loop_result = await executor.execute_loop(
                        next_step, step_states, guard
                    )
                    if loop_result.failed_count == 0:
                        state.mark_done(loop_result.results)
                    else:
                        state.mark_failed(
                            f"循环执行 {loop_result.failed_count} 次失败"
                        )

                else:
                    # 普通步骤
                    result = await executor.execute(next_step)
                    if result.success:
                        state.mark_done(result.result)
                    else:
                        state.mark_failed(result.error or "执行失败")

            except Exception as e:
                logger.error("步骤 %s 执行异常: %s", next_step.step_id, e)
                state.mark_failed(str(e))

            # 5. 失败处理
            if state.status == StepStatus.FAILED:
                action = await failure_handler.handle_failure(
                    next_step, state, state.error or "未知错误", steps
                )

                if action == "abort":
                    logger.error("关键步骤失败，终止任务")
                    return self._build_failure_result(
                        task,
                        steps,
                        step_states,
                        context_store,
                        f"关键步骤 {next_step.step_id} 失败",
                    )

                elif action == "retry":
                    # 重置为 pending 以便重试
                    state.status = StepStatus.PENDING
                    state.error = None

                elif action == "skip":
                    # 已由 failure_handler 处理级联跳过
                    pass

            # 6. 消耗预算
            guard.consume_step()

    def _build_failure_result(
        self,
        task: Task,
        steps: list[Step],
        step_states: dict[str, StepState],
        context_store: ContextStore,
        reason: str,
    ) -> TaskRunResult:
        """构建失败结果"""
        done = sum(
            1 for s in step_states.values() if s.status == StepStatus.DONE
        )
        failed = sum(
            1 for s in step_states.values() if s.status == StepStatus.FAILED
        )
        skipped = sum(
            1 for s in step_states.values() if s.status == StepStatus.SKIPPED
        )

        return TaskRunResult(
            task_id=task.id,
            success=False,
            message=reason,
            steps_executed=done,
            steps_failed=failed,
            steps_skipped=skipped,
            context=context_store.to_dict(),
        )
