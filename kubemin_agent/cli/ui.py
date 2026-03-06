import asyncio
import os
import sys
from pathlib import Path

from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import Style
from pygments.lexers.shell import BashLexer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from kubemin_agent.agent.skills import SkillsLoader


def get_prompt_style() -> Style:
    """Codex/Claude Code like theme."""
    return Style.from_dict({
        "prompt": "fg:ansidarkgray bold",
        "text": "fg:ansiwhite", 
        "completion-menu": "bg:default",
        "completion-menu.completion": "fg:ansiwhite bg:default",
        "completion-menu.meta.completion": "fg:ansigray bg:default",
        "completion-menu.completion.current": "fg:#66d9ef bg:default bold",
        "completion-menu.meta.completion.current": "fg:#66d9ef bg:default bold",
    })


def create_startup_panel(runtime: "ControlPlaneRuntime", workspace: Path) -> Panel:
    """Create the Codex-style startup panel."""
    # Assuming version is available via importlib or hardcoded for now
    version = "0.1.0"
    model_name = getattr(runtime, "model", "Unknown Model")
    cwd = str(workspace.resolve())

    # Replace home directory with ~ for cleaner display
    home = str(Path.home())
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]

    content = (
        f"model:     [bold]{model_name}[/bold]      [cyan]/model[/cyan] to change\n"
        f"directory: [bold]{cwd}[/bold]"
    )

    return Panel(
        content,
        title=f"[bold]>_ KubeMin-Agent[/bold] (v{version})",
        title_align="left",
        border_style="dim",
        padding=(1, 2),
        expand=False,
    )


async def run_interactive_ui(runtime: "ControlPlaneRuntime", workspace: Path, console: Console) -> None:
    """Run the interactive UI loop with prompt_toolkit."""
    history_file = workspace / ".kubemin_history"

    # Command completer
    command_completer = WordCompleter([
        "/help", "/clear", "/plan", "/execute", "/skills", "/exit", "/model"
    ], ignore_case=True, meta_dict={
        "/help": "显示可用命令帮助",
        "/clear": "清空终端屏幕",
        "/plan": "创建执行计划",
        "/execute": "执行生成的计划",
        "/skills": "列出可用的技能",
        "/exit": "退出代理",
        "/model": "切换模型",
    })

    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=command_completer,
        complete_while_typing=True,
        style=get_prompt_style(),
        lexer=PygmentsLexer(BashLexer),
    )

    # Display startup panel
    console.print()
    console.print(create_startup_panel(runtime, workspace))
    console.print("\n[bold]Tip:[/bold] 欢迎使用 KubeMin-Agent。输入 [bold cyan]/help[/bold cyan] 查看可用命令；按 [bold cyan]Enter[/bold cyan] 确认发送。\n")

    # Display initial skills explicitly as requested before
    skills_loader = SkillsLoader(workspace)
    skills = skills_loader.skill_names
    if skills:
         console.print(f"[dim]已加载技能 (Skills): {', '.join(skills)}[/dim]\n")

    while True:
        try:
            user_input = await session.prompt_async(
                HTML("<prompt>❯ </prompt>")
            )
            
            text = user_input.strip()
            if not text:
                continue

            lower_text = text.lower()
            if lower_text in ("/exit", "/quit", "exit", "quit"):
                break
            
            if lower_text == "/clear":
                # Clear terminal
                os.system('cls' if os.name == 'nt' else 'clear')
                continue
            
            if lower_text == "/help":
                console.print("\n[bold]可用命令:[/bold]")
                console.print("  [cyan]/help[/cyan]    显示本帮助信息")
                console.print("  [cyan]/clear[/cyan]   清空终端屏幕")
                console.print("  [cyan]/plan[/cyan]    创建执行计划 (例如: /plan 修复认证中的bug)")
                console.print("  [cyan]/execute[/cyan] 执行生成的计划")
                console.print("  [cyan]/skills[/cyan]  列出可用的技能")
                console.print("  [cyan]/model[/cyan]   切换模型")
                console.print("  [cyan]/exit[/cyan]    退出代理\n")
                continue
            
            if lower_text == "/skills":
                loader = SkillsLoader(workspace)
                summary = loader.build_skills_summary()
                always = [s.name for s in loader.get_always_skills()]
                if not summary and not always:
                    console.print("[yellow]当前未加载任何技能。[/yellow]\n")
                else:
                    console.print("\n[bold]已加载技能:[/bold]")
                    if always:
                         console.print(f"始终激活动: {', '.join(always)}")
                    if summary:
                         console.print(Markdown(summary))
                    console.print()
                continue
                
            if lower_text == "/model":
                console.print("[yellow]切换模型功能尚在开发中...[/yellow]\n")
                continue

            # Start the rich spinner while waiting for response
            response = ""
            with console.status("[bold cyan]Agent 正在思考...[/bold cyan]", spinner="dots"):
                 try:
                     response = await runtime.handle_message("cli", "interactive", text)
                 except Exception as e:
                     logger.exception("处理消息时出错")
                     console.print(f"[bold red]错误:[/bold red] {e}")
                     continue

            console.print("\n")
            # Properly render markdown
            console.print(Markdown(response))
            console.print("\n")

        except KeyboardInterrupt:
            # Allow clearing the line on ctrl-c
            continue
        except EOFError:
            # Ctrl-D
            break
        except Exception as e:
            console.print(f"[bold red]意外的界面错误:[/bold red] {e}")
    console.print("\n[dim]再见！[/dim]")
