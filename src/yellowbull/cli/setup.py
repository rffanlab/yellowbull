"""Setup 命令 — 交互式初始化向导

提供 `yellowbull setup` 命令，支持交互和非交互两种模式。
负责 .env 生成、数据目录/数据库初始化、.gitignore 更新。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from yellowbull.config.settings import (
    DatabaseSettings,
    ExecutionSettings,
    LLMSettings,
    Settings,
)
from yellowbull.storage.db import DatabaseManager

console = Console()

# ── 常量 ───────────────────────────────────────────────────────

_PROVIDER_OPTIONS = {
    "1": {"name": "OpenAI", "default_model": "gpt-4o"},
    "2": {"name": "Anthropic", "default_model": "claude-sonnet-4-20250514"},
    "3": {"name": "Ollama", "default_model": "", "base_url": "http://localhost:11434"},
}

_TOOL_OPTIONS = {
    "file": "文件读写",
    "shell": "Shell 命令执行",
    "code": "代码生成与审查",
    "search": "网络搜索",
}


# ── 辅助函数 ───────────────────────────────────────────────────


def _check_environment() -> bool:
    """用途: 检测 Python 版本和基础依赖

    入参: 无
    返回:
        bool: True=环境满足要求, False=不满足
    """
    required_version = (3, 10)
    actual = sys.version_info[:2]
    if actual < required_version:
        console.print(
            f"[red]✗ Python {'.'.join(map(str, required_version))}+  Required, "
            f"found {'.'.join(map(str, actual))}[/red]"
        )
        return False

    # 依赖检测
    packages = ["click", "rich", "pydantic", "pydantic_settings", "aiosqlite"]
    for pkg in packages:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            console.print(f"[red]✗ 缺少依赖包: {pkg}[/red]")
            return False

    return True


def _generate_env(config: dict, path: Path) -> None:
    """用途: 将配置 dict 写入 .env 文件

    入参:
        config (dict): 扁平化配置字典
        path (Path): .env 文件路径

    返回: 无
    """
    settings = Settings.from_dict(config)
    settings.export_env(path)


def _init_data_dirs(db_path_str: str) -> Path:
    """用途: 创建数据库所在目录

    入参:
        db_path_str (str): 数据库文件路径

    返回:
        Path: 数据库文件的 Path 对象
    """
    db_path = Path(db_path_str)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


async def _init_database(db_path: Path) -> None:
    """用途: 异步初始化 SQLite 数据库（WAL + 建表）

    入参:
        db_path (Path): 数据库文件路径

    返回: 无
    """
    # 重置单例，确保使用正确的 path
    DatabaseManager._instance = None
    settings = DatabaseSettings(path=str(db_path))
    manager = DatabaseManager(settings=settings)
    await manager.initialize()
    await manager.close()


def _gitignore_add_env(gitignore_path: Path | None = None) -> None:
    """用途: 将 .env 追加到 .gitignore（幂等）

    入参:
        gitignore_path (Path | None): .gitignore 路径，默认当前目录

    返回: 无
    """
    if gitignore_path is None:
        gitignore_path = Path(".gitignore")

    pattern = ".env"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if pattern in content:
            return  # 已存在，幂等跳过
        gitignore_path.write_text(
            content.rstrip() + f"\n{pattern}\n", encoding="utf-8"
        )
    else:
        gitignore_path.write_text(f"{pattern}\n", encoding="utf-8")


def _print_summary(settings: Settings) -> None:
    """用途: 打印配置摘要表格

    入参:
        settings (Settings): 全局配置

    返回: 无
    """
    table = Table(title="[bold green]✓ 初始化完成！[/bold green]", show_header=False)
    table.add_column("项", style="cyan")
    table.add_column("值")

    table.add_row("Provider", settings.llm.provider)
    table.add_row("Model", settings.llm.model)
    table.add_row("Tools", settings.tools_allowed)
    table.add_row("Database", f"{settings.database.path} (WAL)")
    table.add_row("Config", ".env")

    console.print()
    console.print(table)
    console.print('\n[dim]开始使用: yellowbull "你的第一个任务"[/dim]')


# ── 交互式引导函数 ─────────────────────────────────────────────


def _interactive_llm_setup() -> dict:
    """用途: 交互引导 LLM 配置

    入参: 无
    返回:
        dict: llm_provider, llm_model, llm_api_key, llm_base_url
    """
    console.print("\n[bold cyan][2/6] LLM 配置[/bold cyan]")

    # 提供商选择
    click.echo("  选择提供商:")
    for key, val in _PROVIDER_OPTIONS.items():
        default = f" (默认)" if key == "1" else ""
        click.echo(f"    {key}) {val['name']}{default}")

    choice = click.prompt("  请选择", type=str, default="1")
    provider_info = _PROVIDER_OPTIONS.get(choice, _PROVIDER_OPTIONS["1"])

    # 映射到 provider 名称
    provider_map = {"1": "openai", "2": "anthropic", "3": "ollama"}
    provider = provider_map.get(choice, "openai")

    model = click.prompt(
        "  Model 名称",
        type=str,
        default=provider_info["default_model"],
    )

    api_key = click.prompt(
        "  API Key (留空=使用环境变量)",
        type=str,
        default="",
        show_default=False,
    )

    base_url = None
    if provider == "ollama":
        base_url = click.prompt(
            "  Base URL",
            type=str,
            default="http://localhost:11434",
        )
    else:
        base_url_input = click.prompt(
            "  Base URL (代理地址，可选)",
            type=str,
            default="",
            show_default=False,
        )
        if base_url_input.strip():
            base_url = base_url_input.strip()

    return {
        "llm_provider": provider,
        "llm_model": model,
        "llm_api_key": api_key,
        "llm_base_url": base_url,
    }


def _interactive_exec_setup() -> dict:
    """用途: 交互引导执行参数配置

    入参: 无
    返回:
        dict: step_timeout, task_timeout, max_steps, retry_limit
    """
    console.print("\n[bold cyan][3/6] 执行配置 (按 Enter 使用默认值)[/bold cyan]")

    return {
        "step_timeout": click.prompt("  单步超时 [120s]", type=int, default=120),
        "task_timeout": click.prompt("  任务总超时 [1800s]", type=int, default=1800),
        "max_steps": click.prompt("  最大步骤数 [100]", type=int, default=100),
        "retry_limit": click.prompt("  单步最大重试 [2]", type=int, default=2),
    }


def _interactive_tool_setup() -> dict:
    """用途: 交互引导工具选择

    入参: 无
    返回:
        dict: tools_allowed, shell_safe_mode
    """
    console.print("\n[bold cyan][4/6] 工具配置[/bold cyan]")

    click.echo("  启用工具 (空格选择, * = 已选):")
    for name, desc in _TOOL_OPTIONS.items():
        click.echo(f"    [*] {name:8s} - {desc}")

    # 简化：直接输入逗号分隔的工具名，默认全选
    tools_input = click.prompt(
        "  启用的工具 (逗号分隔)",
        type=str,
        default="file,shell,code",
    )

    safe_mode = click.confirm("  Shell 安全模式", default=True)

    return {
        "tools_allowed": tools_input.strip(),
        "shell_safe_mode": safe_mode,
    }


# ── LLM 连接测试 ───────────────────────────────────────────────


async def _test_llm_connection(settings: Settings) -> bool:
    """用途: 发送简短 chat 请求验证 API Key + Model

    入参:
        settings (Settings): 全局配置

    返回:
        bool: True=连接成功, False=失败
    """
    from yellowbull.llm.client import LLMClient

    try:
        client = LLMClient(settings=settings.llm)
        result = await client.chat(
            messages=[{"role": "user", "content": "Say 'ok'"}],
            max_tokens=10,
        )
        if result:
            summary = str(result)[:80]
            console.print(f"[green]✓ 连接成功 ({settings.llm.model}, response: {summary})[/green]")
            return True
    except Exception as e:
        console.print(f"[red]✗ 连接失败: {e}[/red]")
        console.print("[dim]排查建议:[/dim]")
        console.print("  - 检查 API Key 是否有效")
        console.print("  - 确认 Model 名称存在")
        console.print("  - 检查网络连接 / Base URL")

    return False


# ── CLI Command ────────────────────────────────────────────────


@click.command()
@click.option("--non-interactive", is_flag=True, help="非交互模式，必须提供所有参数")
@click.option("--provider", type=str, default=None, help="LLM 提供商 (openai/anthropic/ollama)")
@click.option("--model", type=str, default=None, help="Model 名称")
@click.option("--api-key", type=str, default=None, help="API Key")
@click.option("--base-url", type=str, default=None, help="Base URL（代理地址）")
@click.option("--db-path", type=str, default="./data/yellowbull.db", help="数据库路径")
@click.option("--tools-allowed", type=str, default="file,shell,code", help="允许的工具列表")
@click.option("--init-data-only", is_flag=True, help="仅初始化数据目录和数据库")
@click.option("--show-config", is_flag=True, help="显示当前配置后退出")
@click.option("--force", is_flag=True, help="强制覆盖已有 .env 文件")
def setup(
    non_interactive: bool,
    provider: str | None,
    model: str | None,
    api_key: str | None,
    base_url: str | None,
    db_path: str,
    tools_allowed: str,
    init_data_only: bool,
    show_config: bool,
    force: bool,
) -> None:
    """初始化 YellowBull 配置、数据目录和数据库。"""

    # ── --show-config：打印当前配置后退出 ────────────────────────
    if show_config:
        settings = Settings()
        _print_summary(settings)
        return

    # ── --init-data-only：仅初始化数据 ──────────────────────────
    if init_data_only:
        console.print("[bold]数据初始化模式[/bold]")
        data_path = _init_data_dirs(db_path)
        db_file = data_path / Path(db_path).name
        asyncio.run(_init_database(db_file))
        console.print("[green]✓ 数据初始化完成[/green]")
        return

    # ── --non-interactive：参数校验 → .env → 数据初始化 ─────────
    if non_interactive:
        if not all([provider, model, api_key]):
            raise click.ClickException(
                "--non-interactive 需要 --provider, --model, --api-key"
            )

        config = {
            "llm_provider": provider,
            "llm_model": model,
            "llm_api_key": api_key,
            "llm_base_url": base_url or ("http://localhost:11434" if provider == "ollama" else None),
            "db_path": db_path,
            "tools_allowed": tools_allowed,
        }

        env_path = Path(".env")
        if env_path.exists() and not force:
            raise click.ClickException(f"{env_path} 已存在，使用 --force 覆盖")

        _generate_env(config, env_path)
        _gitignore_add_env(Path(".gitignore"))

        data_dir = _init_data_dirs(db_path)
        db_file = Path(db_path)
        if not db_file.is_absolute():
            db_file = data_dir / db_file
        asyncio.run(_init_database(db_file))

        console.print("[green]✓ 初始化完成！配置已写入 .env[/green]")
        return

    # ── 交互模式：6步引导 ───────────────────────────────────────
    console.print(
        Panel(
            "[bold yellow]YellowBull[/bold yellow] — 初始化向导\n"
            "[dim]逐步完成配置，所有选项支持 Enter 使用默认值[/dim]",
            title="[bold]v0.1.0[/bold]",
            border_style="blue",
        )
    )

    # Step 1: 环境检测
    console.print("\n[bold cyan][1/6] 环境检测[/bold cyan]")
    if not _check_environment():
        console.print("[red]环境不满足要求，请修复后重试。[/red]")
        sys.exit(1)

    console.print(f"[green]✓ Python {'.'.join(map(str(sys.version_info[:3])))} (>= 3.10)[/green]")
    console.print("[green]✓ 依赖包完整[/green]")

    # Step 2~4: 交互引导
    llm_config = _interactive_llm_setup()
    exec_config = _interactive_exec_setup()
    tool_config = _interactive_tool_setup()

    # Step 5: 数据初始化
    console.print("\n[bold cyan][5/6] 数据初始化[/bold cyan]")
    db_path_input = click.prompt(
        "  数据库路径",
        type=str,
        default="./data/yellowbull.db",
    )

    data_dir = _init_data_dirs(db_path_input)
    console.print("[green]✓[/green] 数据目录已就绪")

    db_file = Path(db_path_input)
    if not db_file.is_absolute():
        db_file = data_dir / db_file
    asyncio.run(_init_database(db_file))
    console.print("[green]✓[/green] 数据库初始化完成 (WAL 模式)")
    console.print("[green]✓[/green] 经验表 / 关键词表 / 标签表 已就绪")

    # Step 6: 生成配置
    console.print("\n[bold cyan][6/6] 生成配置[/bold cyan]")

    config = {**llm_config, **exec_config, **tool_config, "db_path": db_path_input}

    env_path = Path(".env")
    if env_path.exists():
        if not click.confirm("  .env 已存在，是否覆盖？", default=False):
            console.print("[yellow]跳过配置写入[/yellow]")
            return

    _generate_env(config, env_path)
    _gitignore_add_env(Path(".gitignore"))
    console.print("[green]✓[/green] .env 文件已写入")
    console.print("[green]✓[/green] .gitignore 已追加 .env")

    # 打印摘要
    settings = Settings.from_dict(config)
    _print_summary(settings)

    # LLM 连接测试（可选）
    if click.confirm("测试 LLM 连接？", default=True):
        asyncio.run(_test_llm_connection(settings))
