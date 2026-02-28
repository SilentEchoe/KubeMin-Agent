"""CLI commands for kubemin-agent."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from kubemin_agent.config import ensure_workspace, load_config, save_default_config

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

    from kubemin_agent.agent.loop import AgentLoop
    from kubemin_agent.bus.queue import MessageBus
    from kubemin_agent.control.runtime import ControlPlaneRuntime
    from kubemin_agent.providers.litellm_provider import LiteLLMProvider

    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=config.get_api_base(),
        default_model=config.agents.defaults.model,
    )

    if config.control.enabled:
        runtime = ControlPlaneRuntime.from_config(config, provider, workspace)

        if message:
            response = asyncio.run(runtime.handle_message("cli", "direct", message))
            console.print(response)
            return

        console.print("[bold]KubeMin-Agent[/bold] control-plane interactive mode.")
        console.print("Type 'exit' to quit. Use '/plan <task>' to create a plan, and '/execute' to run it.\n")
        while True:
            try:
                user_input = console.input("[bold blue]> [/bold blue]")
                if user_input.strip().lower() in ("exit", "quit"):
                    break
                if not user_input.strip():
                    continue
                response = asyncio.run(runtime.handle_message("cli", "interactive", user_input))
                console.print(f"\n{response}\n")
            except (KeyboardInterrupt, EOFError):
                break
        console.print("\n[dim]Goodbye![/dim]")
        return

    # Backward-compatibility path: legacy AgentLoop mode.
    bus = MessageBus()
    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        max_context_tokens=config.agents.defaults.max_context_tokens,
        min_recent_history_messages=config.agents.defaults.min_recent_history_messages,
        task_anchor_max_chars=config.agents.defaults.task_anchor_max_chars,
        history_message_max_chars=config.agents.defaults.history_message_max_chars,
    )

    if message:
        response = asyncio.run(loop.process_direct(message))
        console.print(response)
    else:
        console.print("[bold]KubeMin-Agent[/bold] legacy interactive mode. Type 'exit' to quit.\n")
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
    table.add_row("Max Context Tokens", str(config.agents.defaults.max_context_tokens))
    table.add_row("Min Recent History", str(config.agents.defaults.min_recent_history_messages))
    table.add_row("Task Anchor Max Chars", str(config.agents.defaults.task_anchor_max_chars))
    table.add_row("History Msg Max Chars", str(config.agents.defaults.history_message_max_chars))
    table.add_row("Memory Backend", config.agents.defaults.memory_backend)
    table.add_row("Memory Top K", str(config.agents.defaults.memory_top_k))
    table.add_row("Memory Context Max Chars", str(config.agents.defaults.memory_context_max_chars))
    table.add_row("Temperature", str(config.agents.defaults.temperature))
    table.add_row("Max Tool Iterations", str(config.agents.defaults.max_tool_iterations))

    api_key = config.get_api_key()
    table.add_row("API Key", f"...{api_key[-8:]}" if api_key else "[red]Not configured[/red]")
    table.add_row("API Base", config.get_api_base() or "Default")

    table.add_row("Control Plane", "Enabled" if config.control.enabled else "Disabled")
    table.add_row("Control Max Parallel", str(config.control.max_parallelism))
    table.add_row("Control Fail Fast", str(config.control.fail_fast))
    table.add_row("Evaluation", "Enabled" if config.evaluation.enabled else "Disabled")
    table.add_row("Evaluation Mode", config.evaluation.mode)
    table.add_row("Evaluation Warn Threshold", str(config.evaluation.warn_threshold))
    table.add_row("Evaluation LLM Judge", "Enabled" if config.evaluation.llm_judge_enabled else "Disabled")
    table.add_row("Evaluation Trace Capture", "Enabled" if config.evaluation.trace_capture else "Disabled")
    table.add_row("Evaluation Max Trace Steps", str(config.evaluation.max_trace_steps))
    table.add_row("Validator Policy", config.validator.policy_level)

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

    from kubemin_agent.agent.loop import AgentLoop
    from kubemin_agent.bus.events import InboundMessage
    from kubemin_agent.bus.queue import MessageBus
    from kubemin_agent.channels.manager import ChannelManager
    from kubemin_agent.control.runtime import ControlPlaneRuntime
    from kubemin_agent.cron.service import CronService
    from kubemin_agent.cron.types import CronJob
    from kubemin_agent.heartbeat.service import HeartbeatService
    from kubemin_agent.providers.litellm_provider import LiteLLMProvider

    async def _run_gateway() -> None:
        provider = LiteLLMProvider(
            api_key=api_key,
            api_base=config.get_api_base(),
            default_model=config.agents.defaults.model,
        )
        bus = MessageBus()
        channel_manager = ChannelManager(bus)
        cron_service = CronService(workspace)
        heartbeat_service = HeartbeatService(workspace)

        console.print("[bold green]Gateway starting...[/bold green]")

        async def execute_cron_job(job: CronJob) -> None:
            """Callback for CronService to execute a job via MessageBus."""
            msg = InboundMessage(
                channel="cron",
                chat_id=job.chat_id or "system",
                content=job.message,
                sender="system",
                metadata={"job_id": job.id, "job_name": job.name},
            )
            await bus.inbound.put(msg)

        async def execute_heartbeat(content: str) -> None:
            """Callback for HeartbeatService to execute tasks via MessageBus."""
            msg = InboundMessage(
                channel="heartbeat",
                chat_id="system",
                content=content,
                sender="system",
            )
            await bus.inbound.put(msg)

        if config.control.enabled:
            runtime = ControlPlaneRuntime.from_config(config, provider, workspace)
            tasks = [
                asyncio.create_task(runtime.run_bus_loop(bus)),
                asyncio.create_task(bus.dispatch_outbound()),
                asyncio.create_task(channel_manager.start_all()),
                asyncio.create_task(cron_service.run(execute_cron_job)),
                asyncio.create_task(heartbeat_service.run(execute_heartbeat)),
            ]
            try:
                await asyncio.gather(*tasks)
            except KeyboardInterrupt:
                runtime.stop()
                bus.stop()
                cron_service.stop()
                heartbeat_service.stop()
                await channel_manager.stop_all()
            return

        # Backward-compatibility path: legacy AgentLoop gateway.
        agent_loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=workspace,
            model=config.agents.defaults.model,
            max_context_tokens=config.agents.defaults.max_context_tokens,
            min_recent_history_messages=config.agents.defaults.min_recent_history_messages,
            task_anchor_max_chars=config.agents.defaults.task_anchor_max_chars,
            history_message_max_chars=config.agents.defaults.history_message_max_chars,
        )
        tasks = [
            asyncio.create_task(agent_loop.run()),
            asyncio.create_task(bus.dispatch_outbound()),
            asyncio.create_task(channel_manager.start_all()),
            asyncio.create_task(cron_service.run(execute_cron_job)),
            asyncio.create_task(heartbeat_service.run(execute_heartbeat)),
        ]

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            agent_loop.stop()
            bus.stop()
            cron_service.stop()
            heartbeat_service.stop()
            await channel_manager.stop_all()

    asyncio.run(_run_gateway())


@app.command()
def logs(
    session: str = typer.Option("", "--session", "-s", help="Filter by session key"),
    request_id: str = typer.Option("", "--request-id", "-r", help="Filter by request ID"),
    eval_only: bool = typer.Option(False, "--eval-only", "-e", help="Show only evaluation logs"),
    limit: int = typer.Option(50, "--limit", "-l", help="Number of latest entries to show"),
    config_path: Optional[Path] = typer.Option(None, "--config", "-c", help="Config file path"),
) -> None:
    """View execution trajectories and evaluation results."""
    import json
    from datetime import datetime
    
    from rich.panel import Panel
    from rich.text import Text
    from rich.tree import Tree

    config = load_config(config_path)
    workspace = ensure_workspace(config)
    audit_dir = workspace.parent / "audit"
    
    if not audit_dir.exists():
        console.print("[yellow]No audit logs found.[/yellow]")
        return
        
    log_files = sorted(audit_dir.glob("*.jsonl"), reverse=True)
    if not log_files:
        console.print("[yellow]No audit logs found.[/yellow]")
        return
        
    entries = []
    
    # Read files from newest to oldest until we hit the limit
    for log_file in log_files:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                # Reverse to process newest first
                for line in reversed(lines):
                    try:
                        entry = json.loads(line)
                        if session and entry.get("session_key") != session:
                            continue
                        if request_id and entry.get("request_id") != request_id:
                            continue
                        if eval_only and entry.get("type") != "evaluation":
                            continue
                        
                        target_types = {"reasoning_step", "evaluation"}
                        if not eval_only:
                            target_types.update(["dispatch", "execution", "validation"])
                            
                        if entry.get("type") in target_types:
                            entries.append(entry)
                            if len(entries) >= limit:
                                break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            console.print(f"[red]Error reading {log_file}: {e}[/red]")
            
        if len(entries) >= limit:
            break
            
    if not entries:
        console.print("[yellow]No matching logs found.[/yellow]")
        return
        
    # Reverse back to chronological order (oldest -> newest) for display
    entries.reverse()
    
    console.print(f"[bold green]Found {len(entries)} matching log entries[/bold green]\n")
    
    for entry in entries:
        etype = entry.get("type")
        timestamp = entry.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp)
                ts_str = dt.strftime("%H:%M:%S")
            except ValueError:
                ts_str = timestamp
        else:
            ts_str = "Unknown"
            
        req_id = entry.get("request_id", "-")[:8]
        sess_key = entry.get("session_key", "-")
        header = f"[dim]{ts_str}[/dim] [cyan]{sess_key}[/cyan] [blue]req:{req_id}[/blue]"
        
        if etype == "dispatch":
            agent = entry.get("target_agent", "unknown")
            task = entry.get("task_description", "")
            console.print(f"{header} [bold magenta]DISPATCH[/bold magenta] ➔ [bold]{agent}[/bold]")
            console.print(f"  [dim]Task:[/dim] {task}\n")
            
        elif etype == "reasoning_step":
            agent = entry.get("agent_name", "unknown")
            phase = entry.get("phase", "unknown")
            step = entry.get("step_index", 0)
            
            tree = Tree(f"{header} [bold yellow]STEP {step}[/bold yellow] ({agent} - {phase})")
            
            intent = entry.get("intent_summary")
            action = entry.get("action")
            obs = entry.get("observation_summary")
            err = entry.get("error")
            
            if intent:
                tree.add(Text("Intent: ", style="italic dim").append(intent, style="green"))
            if action:
                tree.add(Text("Action: ", style="italic dim").append(action, style="cyan"))
            if obs:
                tree.add(Text("Observ: ", style="italic dim").append(obs, style="white"))
            if err:
                tree.add(Text("Error:  ", style="italic dim").append(err, style="red bold"))
                
            console.print(tree)
            console.print()
            
        elif etype == "evaluation":
            agent = entry.get("agent_name", "unknown")
            score = entry.get("overall_score", 0)
            passed = entry.get("passed", False)
            warn_threshold = entry.get("warn_threshold", 60)
            
            color = "green" if passed else "red"
            status = "PASSED" if passed else "WARNING"
            
            table = Table(title=f"Evaluation: {agent}", show_header=False, box=None)
            table.add_column("Key", style="dim", justify="right")
            table.add_column("Value")
            
            table.add_row("Status", f"[{color} bold]{status}[/{color} bold] (Score: {score}/{warn_threshold})")
            
            dims = entry.get("dimension_scores", {})
            if dims:
                dim_str = ", ".join(f"{k}: {v}" for k, v in dims.items())
                table.add_row("Dimensions", dim_str)
                
            if not passed:
                reasons = entry.get("reasons", [])
                if reasons:
                    table.add_row("Reasons", "\n".join(f"• {r}" for r in reasons))
                    
                suggestions = entry.get("suggestions", [])
                if suggestions:
                    table.add_row("Suggestions", "\n".join(f"• {s}" for s in suggestions))
            
            panel = Panel(table, border_style=color, expand=False)
            console.print(f"{header} [bold]EVALUATION[/bold]")
            console.print(panel)
            console.print()
            
        elif etype == "validation":
            agent = entry.get("agent_name", "unknown")
            passed = entry.get("passed", False)
            if not passed:
                reason = entry.get("reason", "unknown error")
                severity = entry.get("severity", "info")
                color = "red" if severity == "block" else "yellow"
                console.print(f"{header} [bold {color}]VALIDATION {severity.upper()}[/bold {color}] ({agent})")
                console.print(f"  [dim]Reason:[/dim] {reason}\n")


if __name__ == "__main__":
    app()
