"""CLI commands for kubemin-agent."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from kubemin_agent.config import load_config, save_default_config, ensure_workspace

app = typer.Typer(
    name="kubemin-agent",
    help="KubeMin-Agent: Intelligent assistant for cloud-native application management",
)
console = Console()


@app.command()
def onboard(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Initialize configuration and workspace."""
    path = save_default_config(config_path)
    config = load_config(config_path)
    workspace = ensure_workspace(config)

    console.print(f"[green]Config created at:[/green] {path}")
    console.print(f"[green]Workspace initialized at:[/green] {workspace}")
    console.print("\n[yellow]Next steps:[/yellow]")
    console.print("1. Edit config to add your API key")
    console.print("2. Run: kubemin-agent agent -m \"Hello!\"")


@app.command()
def agent(
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Message to send"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Chat with the agent."""
    config = load_config(config_path)
    workspace = ensure_workspace(config)

    api_key = config.get_api_key()
    if not api_key:
        console.print("[red]Error:[/red] No API key configured. Run 'kubemin-agent onboard' first.")
        raise typer.Exit(1)

    from kubemin_agent.providers.litellm_provider import LiteLLMProvider
    from kubemin_agent.bus.queue import MessageBus
    from kubemin_agent.agent.loop import AgentLoop

    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=config.get_api_base(),
        default_model=config.agents.defaults.model,
    )
    bus = MessageBus()
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
    )

    if message:
        # Single message mode
        response = asyncio.run(loop.process_direct(message))
        console.print(response)
    else:
        # Interactive mode
        console.print("[bold]KubeMin-Agent[/bold] interactive mode. Type 'exit' to quit.\n")
        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
                if user_input.strip().lower() in ("exit", "quit"):
                    break
                if not user_input.strip():
                    continue
                response = asyncio.run(loop.process_direct(user_input))
                console.print(f"\n{response}\n")
            except (KeyboardInterrupt, EOFError):
                break
        console.print("\n[dim]Goodbye![/dim]")


@app.command()
def status(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Show current status and configuration."""
    config = load_config(config_path)

    table = Table(title="KubeMin-Agent Status")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Workspace", str(config.workspace_path))
    table.add_row("Model", config.agents.defaults.model)
    table.add_row("Max Tokens", str(config.agents.defaults.max_tokens))
    table.add_row("Temperature", str(config.agents.defaults.temperature))
    table.add_row("Max Tool Iterations", str(config.agents.defaults.max_tool_iterations))

    api_key = config.get_api_key()
    table.add_row("API Key", f"...{api_key[-8:]}" if api_key else "[red]Not configured[/red]")
    table.add_row("API Base", config.get_api_base() or "Default")

    table.add_row("Telegram", "Enabled" if config.channels.telegram.enabled else "Disabled")
    table.add_row("KubeMin API", config.kubemin.api_base or "[dim]Not configured[/dim]")

    console.print(table)


@app.command()
def gateway(
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """Start the gateway (agent + channels + cron + heartbeat)."""
    config = load_config(config_path)
    workspace = ensure_workspace(config)

    api_key = config.get_api_key()
    if not api_key:
        console.print("[red]Error:[/red] No API key configured.")
        raise typer.Exit(1)

    from kubemin_agent.providers.litellm_provider import LiteLLMProvider
    from kubemin_agent.bus.queue import MessageBus
    from kubemin_agent.agent.loop import AgentLoop
    from kubemin_agent.channels.manager import ChannelManager

    async def _run_gateway():
        provider = LiteLLMProvider(
            api_key=api_key,
            api_base=config.get_api_base(),
            default_model=config.agents.defaults.model,
        )
        bus = MessageBus()
        agent_loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            model=config.agents.defaults.model,
        )
        channel_manager = ChannelManager(bus)

        console.print("[bold green]Gateway starting...[/bold green]")

        tasks = [
            asyncio.create_task(agent_loop.run()),
            asyncio.create_task(bus.dispatch_outbound()),
            asyncio.create_task(channel_manager.start_all()),
        ]

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            agent_loop.stop()
            bus.stop()
            await channel_manager.stop_all()

    asyncio.run(_run_gateway())


if __name__ == "__main__":
    app()
