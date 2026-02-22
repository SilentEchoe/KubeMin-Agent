import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

try:
    from .agent_core.loop import ChatAgent, build_default_tools
    from .agent_core.provider import OpenAICompatibleProvider
    from .agent_core.session import SessionManager
    from .config import settings
except ImportError:  # Support `python cli.py` execution
    from agent_core.loop import ChatAgent, build_default_tools
    from agent_core.provider import OpenAICompatibleProvider
    from agent_core.session import SessionManager
    from config import settings

app = typer.Typer(help="KubeMin-Agent: Enterprise Production Grade Diagnostic CLI")
console = Console()

@app.callback()
def main(
    ctx: typer.Context,
    json: bool = typer.Option(False, help="Output strictly in JSON format"),
):
    """
    KubeMin-Agent CLI Entrypoint.
    """
    # Initialize Context for global flags
    ctx.obj = {"json": json}

@app.command()
def info():
    """
    Display current configuration and environment info.
    """
    if settings.api_token:
        token_status = "[green]Set[/green]"
    else:
        token_status = "[yellow]Not Set (Anonymous/Env)[/yellow]"

    info_panel = Panel(
        f"""
        [bold]KubeMin API URL:[/bold] {settings.api_url}
        [bold]Token Status:[/bold] {token_status}
        [bold]Run Store:[/bold] {settings.run_store_dir}
        [bold]Budget:[/bold] {settings.budget_max_tool_calls} calls / run
        [bold]Agent Workspace:[/bold] {settings.agent_workspace}
        [bold]Agent Model:[/bold] {settings.agent_model}
        """,
        title="KubeMin Agent Configuration",
        expand=False
    )
    console.print(info_panel)


def _create_chat_agent() -> ChatAgent:
    provider = OpenAICompatibleProvider(
        api_base=settings.agent_api_base,
        api_key=settings.resolved_agent_api_key,
        model=settings.agent_model,
    )
    tools = build_default_tools(
        workspace=settings.agent_workspace,
        exec_timeout_s=settings.agent_exec_timeout_s,
        restrict_to_workspace=settings.agent_restrict_workspace,
    )
    sessions = SessionManager(settings.agent_sessions_dir)
    return ChatAgent(
        provider=provider,
        tools=tools,
        sessions=sessions,
        workspace=settings.agent_workspace,
        max_iterations=settings.agent_max_iterations,
        history_limit=settings.agent_history_limit,
    )


def _is_local_api_base(url: str) -> bool:
    lowered = url.lower()
    return "localhost" in lowered or "127.0.0.1" in lowered


@app.command()
def agent(
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Single-turn message"),
    session: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
):
    """
    Chat with a nanobot-style general-purpose agent.
    """
    if not settings.resolved_agent_api_key and not _is_local_api_base(settings.agent_api_base):
        console.print("[red]Missing API key.[/red]")
        console.print("Set KUBEMIN_AGENT_API_KEY or OPENAI_API_KEY (or use a local endpoint).")
        raise typer.Exit(code=1)

    chat_agent = _create_chat_agent()

    if message:
        response = asyncio.run(chat_agent.process(message, session_key=session))
        console.print(f"\n[bold green]Agent:[/bold green] {response}")
        return

    console.print("[bold green]Interactive agent mode[/bold green] (Ctrl+C to exit)")
    while True:
        try:
            user_input = console.input("[bold blue]You:[/bold blue] ")
            if not user_input.strip():
                continue
            response = asyncio.run(chat_agent.process(user_input, session_key=session))
            console.print(f"[bold green]Agent:[/bold green] {response}\n")
        except KeyboardInterrupt:
            console.print("\nExiting.")
            break

@app.command()
def inspect(
    app_id: str = typer.Option(..., "--app", "-a", help="Application ID to diagnose"),
    namespace: str = typer.Option("default", "--namespace", "-n", help="Namespace of the application"),
    query: str = typer.Argument(..., help="Natural language query for diagnosis")
):
    """
    Start a diagnostic run for a specific application.
    """
    console.print(f"[bold blue]Starting diagnosis for app:[/bold blue] {app_id} (ns: {namespace})")
    console.print(f"[dim]Query: {query}[/dim]")
    
    # Placeholder for Phase 1 Orchestration
    console.print("[yellow]Orchestrator not yet implemented (Phase 1)[/yellow]")

@app.command()
def replay(
    run_id: str = typer.Option(..., "--run", "-r", help="UUID of the run to replay")
):
    """
    Replay a past diagnostic run from artifacts.
    """
    console.print(f"Replaying run: {run_id}")
    # Placeholder for Phase 1 Replay logic

if __name__ == "__main__":
    app()
