"""CLI 主入口

提供命令行参数解析、基础设施初始化和交互式 REPL / 单次任务执行。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel

from yellowbull.config.settings import Settings
from yellowbull.llm.client import LLMClient
from yellowbull.storage.db import DatabaseManager
from yellowbull.tools import CodeTool, FileTool, ShellTool, ToolRegistry

console = Console()
logger = logging.getLogger("yellowbull")


def _setup_logging(verbose: bool) -> None:
    """用途: 配置全局日志级别和格式

    入参:
        verbose (bool): 是否启用详细日志

    返回: 无
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _init_settings(
    model: str | None,
    project_root: str | None,
    config_path: str | None,
) -> Settings:
    """用途: 根据命令行参数初始化全局配置

    入参:
        model (str | None): LLM 模型名称
        project_root (str | None): 项目根目录
        config_path (str | None): 配置文件路径

    返回:
        Settings: 初始化后的配置对象
    """
    settings = Settings()
    if model:
        settings.llm.model = model
    if project_root:
        settings.project_root = project_root
    return settings


def _init_tools(settings: Settings) -> None:
    """用途: 注册所有启用的工具到全局注册表

    入参:
        settings (Settings): 全局配置

    返回: 无
    """
    enabled = settings.enabled_tools

    if "file" in enabled:
        ToolRegistry.register(FileTool())
        logger.debug("已注册工具: file")

    if "shell" in enabled:
        ToolRegistry.register(ShellTool(safe_mode=settings.shell_safe_mode))
        logger.debug("已注册工具: shell")

    if "code" in enabled:
        # CodeTool 暂不传入 llm_client，在 main 流程中再绑定
        ToolRegistry.register(CodeTool())
        logger.debug("已注册工具: code")


async def _init_infrastructure(settings: Settings) -> tuple[LLMClient, DatabaseManager]:
    """用途: 异步初始化 LLM 客户端和数据库

    入参:
        settings (Settings): 全局配置

    返回:
        tuple[LLMClient, DatabaseManager]: (LLM客户端, 数据库管理器)
    """
    llm_client = LLMClient(settings=settings.llm)
    db_manager = await DatabaseManager.get(settings=settings.database)
    return llm_client, db_manager


@click.command()
@click.argument("task", required=False)
@click.option("--model", "model", default=None, help="LLM 模型名称")
@click.option("--project-root", "project_root", default=None, help="项目根目录")
@click.option("--config", "config_path", default=None, help="配置文件路径")
@click.option("--verbose", "-v", is_flag=True, default=False, help="详细输出")
def cli(
    task: str | None,
    model: str | None,
    project_root: str | None,
    config_path: str | None,
    verbose: bool,
) -> None:
    """YellowBull — 本地开发 Agent

    TASK: 可选的任务描述，提供则执行单次任务后退出；不提供则进入交互模式。
    """
    _setup_logging(verbose)

    console.print(
        Panel(
            "[bold yellow]YellowBull[/bold yellow] — 本地开发 Agent\n"
            "[dim]接任务 → 拆步骤 → 调工具 → 看结果 → 修正 → 记录经验[/dim]",
            title="[bold]v0.1.0[/bold]",
            border_style="blue",
        )
    )

    # 1. 初始化配置
    settings = _init_settings(model, project_root, config_path)
    logger.info("配置加载完成 | model=%s | project_root=%s", settings.llm.model, settings.project_root)

    # 2. 注册工具
    _init_tools(settings)
    logger.info("已注册工具数: %d", len(ToolRegistry.list_all()))

    # 3. 异步初始化基础设施
    async def _run() -> None:
        """用途: 主异步入口，初始化基础设施并启动 Agent 循环

        入参: 无
        返回: 无
        """
        llm_client, db_manager = await _init_infrastructure(settings)

        # 绑定 LLM 到 CodeTool
        code_tool = ToolRegistry.get("code")
        if code_tool and isinstance(code_tool, CodeTool):
            code_tool._llm = llm_client

        try:
            if task:
                # 单次任务模式
                await _run_single_task(task, settings, llm_client)
            else:
                # 交互模式
                await _run_repl(settings, llm_client)
        finally:
            await db_manager.close()

    asyncio.run(_run())


async def _run_single_task(
    task: str,
    settings: Settings,
    llm_client: LLMClient,
) -> None:
    """用途: 执行单次任务模式

    入参:
        task (str): 任务描述
        settings (Settings): 全局配置
        llm_client (LLMClient): LLM 客户端

    返回: 无
    """
    console.print(f"\n[bold cyan]任务:[/bold cyan] {task}")
    console.print("[dim]任务执行引擎尚未实现，此处为占位符。[/dim]")


async def _run_repl(
    settings: Settings,
    llm_client: LLMClient,
) -> None:
    """用途: 启动交互式 REPL 循环

    入参:
        settings (Settings): 全局配置
        llm_client (LLMClient): LLM 客户端

    返回: 无
    """
    console.print("\n[dim]进入交互模式。输入任务描述开始，输入 'quit' 或 'exit' 退出。[/dim]")

    while True:
        try:
            user_input = click.prompt("\n[yellow]>>>[/yellow]", default="")
        except (KeyboardInterrupt, EOFError):
            console.print("\n再见！")
            break

        if not user_input.strip():
            continue

        cmd = user_input.strip().lower()
        if cmd in ("quit", "exit", "q"):
            console.print("再见！")
            break

        # 任务执行入口
        console.print(f"[bold cyan]任务:[/bold cyan] {user_input}")
        console.print("[dim]任务执行引擎尚未实现，此处为占位符。[/dim]")


if __name__ == "__main__":
    cli()
