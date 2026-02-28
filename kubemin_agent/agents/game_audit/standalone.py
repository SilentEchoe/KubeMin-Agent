"""
Standalone entry point for GameAuditAgent.

Usage:
  # CLI mode: one-shot audit
  python -m kubemin_agent.agents.game_audit --pdf guide.pdf --url https://game.example.com

  # HTTP service mode
  python -m kubemin_agent.agents.game_audit --serve --port 8080
"""

import asyncio
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="game-audit-agent",
    help="GameAuditAgent - Web game auditing service",
)
console = Console()


def _create_agent(
    api_key: str,
    api_base: str | None,
    model: str,
    workspace: Path,
    game_url: str | None = None,
):
    """Create a GameAuditAgent instance."""
    from kubemin_agent.agents.game_audit_agent import GameAuditAgent
    from kubemin_agent.providers.litellm_provider import LiteLLMProvider
    from kubemin_agent.session.manager import SessionManager

    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=model,
    )
    sessions = SessionManager(workspace)
    return GameAuditAgent(
        provider=provider, sessions=sessions, workspace=workspace, game_url=game_url,
    )


@app.command()
def test(
    pdf: Path = typer.Option(..., "--pdf", "-p", help="Path to PDF gameplay guide"),
    url: str = typer.Option(None, "--url", "-u", envvar="GAME_TEST_URL", help="Game URL to test (also via GAME_TEST_URL env var)"),
    api_key: str = typer.Option(..., "--api-key", "-k", envvar="LLM_API_KEY", help="LLM API key"),
    api_base: str = typer.Option(None, "--api-base", envvar="LLM_API_BASE", help="LLM API base URL"),
    model: str = typer.Option("openrouter/google/gemini-2.0-flash-001", "--model", "-m", help="LLM model"),
    workspace: Path = typer.Option(
        Path.home() / ".kubemin-agent" / "workspace",
        "--workspace", "-w",
        help="Workspace directory",
    ),
) -> None:
    """Run a one-shot game test: read PDF guide, test the game, output report."""
    if not url:
        console.print("[red]Error:[/red] Game URL is required. Use --url or set GAME_TEST_URL env var.")
        raise typer.Exit(1)

    if not pdf.exists():
        console.print(f"[red]Error:[/red] PDF not found: {pdf}")
        raise typer.Exit(1)

    agent = _create_agent(api_key, api_base, model, workspace, game_url=url)

    task_message = (
        f"Please test the web game at {url}.\n\n"
        f"First, read the gameplay guide PDF at: {pdf.absolute()}\n"
        f"Then navigate to the game and systematically test:\n"
        f"1. Game logic correctness (does it match the guide?)\n"
        f"2. Content compliance (text and images)\n"
        f"3. UI/UX quality (interactive elements, layout, feedback)\n\n"
        f"Generate a comprehensive test report with your findings."
    )

    console.print("[bold]GameAuditAgent[/bold] starting audit...\n")
    console.print(f"PDF Guide: {pdf}")
    console.print(f"Game URL:  {url}")
    console.print(f"Model:     {model}")
    console.print("---\n")

    async def _run():
        try:
            result = await agent.run(task_message, session_key="standalone:game_audit")
            if getattr(agent, "_final_report", None):
                console.print(agent._final_report.model_dump_json(indent=2))
            else:
                console.print(result)
        finally:
            await agent.cleanup()

    asyncio.run(_run())


@app.command()
def serve(
    port: int = typer.Option(8080, "--port", help="HTTP service port"),
    host: str = typer.Option("0.0.0.0", "--host", help="HTTP service host"),
    api_key: str = typer.Option(..., "--api-key", "-k", envvar="LLM_API_KEY", help="LLM API key"),
    api_base: str = typer.Option(None, "--api-base", envvar="LLM_API_BASE", help="LLM API base URL"),
    model: str = typer.Option("openrouter/google/gemini-2.0-flash-001", "--model", "-m", help="LLM model"),
    workspace: Path = typer.Option(
        Path.home() / ".kubemin-agent" / "workspace",
        "--workspace", "-w",
        help="Workspace directory",
    ),
) -> None:
    """Start GameAuditAgent as an HTTP service."""
    try:
        import uvicorn
        from fastapi import FastAPI, File, Form, UploadFile
        from fastapi.responses import JSONResponse
    except ImportError:
        console.print("[red]Error:[/red] fastapi and uvicorn are required for serve mode.")
        console.print("Run: pip install fastapi uvicorn python-multipart")
        raise typer.Exit(1)

    api = FastAPI(title="GameAuditAgent Service", version="0.1.0")

    @api.post("/test")
    async def run_test(
        game_url: str = Form(...),
        pdf_file: UploadFile = File(...),
    ):
        """Run a game test with uploaded PDF and game URL."""
        # Save uploaded PDF
        pdf_path = workspace / "uploads" / pdf_file.filename
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        content = await pdf_file.read()
        pdf_path.write_bytes(content)

        agent = _create_agent(api_key, api_base, model, workspace, game_url=game_url)

        task_message = (
            f"Please test the web game at {game_url}.\n\n"
            f"First, read the gameplay guide PDF at: {pdf_path.absolute()}\n"
            f"Then navigate to the game and systematically test:\n"
            f"1. Game logic correctness\n"
            f"2. Content compliance\n"
            f"3. UI/UX quality\n\n"
            f"Generate a comprehensive test report."
        )

        try:
            result = await agent.run(task_message, session_key=f"service:game_audit:{game_url}")
            if getattr(agent, "_final_report", None):
                return JSONResponse(agent._final_report.model_dump(mode="json"))
            return JSONResponse({"status": "ok", "report": result})
        except Exception as e:
            return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
        finally:
            await agent.cleanup()

    @api.get("/health")
    async def health():
        return {"status": "ok", "agent": "game_audit"}

    console.print(f"[bold green]GameAuditAgent HTTP service starting on {host}:{port}[/bold green]")
    uvicorn.run(api, host=host, port=port)


def main():
    app()


if __name__ == "__main__":
    main()
