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
    headless: bool = True,
    step_delay: float = 0.0,
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
        provider=provider,
        sessions=sessions,
        workspace=workspace,
        game_url=game_url,
        headless=headless,
        step_delay=step_delay,
    )


def _save_report(report, workspace: Path) -> Path:
    """
    Save AuditReportV1 as a local Markdown report file and return its path.

    The file contains:
    - PASS / FAIL / CONDITIONAL verdict banner
    - Issue summary metrics
    - Failure reasons (from all FAILED test cases)
    - Full markdown body from the agent
    - Raw JSON for machine consumption
    """
    import datetime
    import json

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = workspace / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    status = report.status  # PASS / FAIL / CONDITIONAL
    verdict_emoji = {"PASS": "PASS", "FAIL": "FAIL", "CONDITIONAL": "CONDITIONAL"}.get(status, status)

    # Collect failure reasons from test cases
    failed_cases = [
        tc for tc in report.plan.test_cases
        if tc.status.value in ("FAILED",)
    ]

    lines: list[str] = [
        f"# GameAuditAgent Report",
        f"",
        f"| Item | Value |",
        f"|---------|-------|",
        f"| Game URL | {report.game_url} |",
        f"| Verdict | **{verdict_emoji}** |",
        f"| Total Issues | {report.total_vulnerabilities} |",
        f"| Critical | {report.critical_issues} |",
        f"| High | {report.high_issues} |",
        f"| Report Time | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |",
        f"",
    ]

    if status != "PASS" and failed_cases:
        lines += [
            "## Failure Reasons",
            "",
        ]
        for tc in failed_cases:
            lines.append(f"### [{tc.id}] {tc.description}")
            lines.append(f"")
            lines.append(f"- **Expected:** {tc.expected_result}")
            if tc.actual_result:
                lines.append(f"- **Actual:** {tc.actual_result}")
            if tc.error_message:
                lines.append(f"- **Error:** {tc.error_message}")
            if tc.evidence_links:
                lines.append(f"- **Evidence:** {', '.join(tc.evidence_links)}")
            lines.append("")

    elif status == "PASS":
        lines += [
            "## Result",
            "",
            "All test cases passed. No blocking issues found.",
            "",
        ]

    # Append the agent's full markdown report
    lines += [
        "## Detailed Report",
        "",
        report.markdown_report,
        "",
        "---",
        "",
        "## Raw JSON",
        "",
        "```json",
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False),
        "```",
    ]

    report_path = report_dir / f"audit_{timestamp}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


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
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless mode (default). Use --no-headless to watch the agent operate the browser in real time.",
    ),
    step_delay: float = typer.Option(
        0.0,
        "--step-delay",
        help="Seconds to pause before each browser action when running in observable mode (--no-headless). Recommended: 1.0-2.0.",
        min=0.0,
        max=10.0,
    ),
) -> None:
    """Run a one-shot game test: read PDF guide, test the game, output report."""
    if not url:
        console.print("[red]Error:[/red] Game URL is required. Use --url or set GAME_TEST_URL env var.")
        raise typer.Exit(1)

    if not pdf.exists():
        console.print(f"[red]Error:[/red] PDF not found: {pdf}")
        raise typer.Exit(1)

    agent = _create_agent(api_key, api_base, model, workspace, game_url=url, headless=headless, step_delay=step_delay)

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

    if not headless:
        console.print()
        console.print("[bold yellow]Observable Mode Enabled[/bold yellow]")
        console.print("  The browser window will be visible so you can watch the agent operate.")
        if step_delay > 0:
            console.print(f"  Each browser action will pause for [bold]{step_delay}s[/bold] to let you follow along.")
        else:
            console.print("  Tip: use [bold]--step-delay 1.5[/bold] to slow down browser actions for easier observation.")

    console.print("---\n")

    async def _run():
        try:
            result = await agent.run(task_message, session_key="standalone:game_audit")
            final_report = getattr(agent, "_final_report", None)

            if final_report:
                # Save the full report to a local Markdown file (next to where the command was run)
                report_path = _save_report(final_report, Path.cwd())

                # Print the verdict banner
                status = final_report.status
                color = {"PASS": "green", "FAIL": "red", "CONDITIONAL": "yellow"}.get(status, "white")
                console.print()
                console.rule(f"[bold {color}]Audit Verdict: {status}[/bold {color}]")
                console.print(f"  Game URL  : {final_report.game_url}")
                console.print(f"  Issues    : {final_report.total_vulnerabilities} total  "
                               f"({final_report.critical_issues} critical, "
                               f"{final_report.high_issues} high)")

                # Print failure reasons directly in terminal
                failed_cases = [
                    tc for tc in final_report.plan.test_cases
                    if tc.status.value == "FAILED"
                ]
                if failed_cases:
                    console.print()
                    console.print("[bold red]Failure Reasons:[/bold red]")
                    for tc in failed_cases:
                        console.print(f"  [{tc.id}] {tc.description}")
                        if tc.actual_result:
                            console.print(f"    Actual  : {tc.actual_result}")
                        if tc.error_message:
                            console.print(f"    Error   : {tc.error_message}")

                console.print()
                console.print(f"[bold]Report saved:[/bold] {report_path}")
                console.rule()
            else:
                # Agent did not call submit_report -- print raw response
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
    headless: bool = typer.Option(
        True,
        "--headless/--no-headless",
        help="Run browser in headless mode (default). Use --no-headless to keep browser windows visible on the server.",
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

        agent = _create_agent(api_key, api_base, model, workspace, game_url=game_url, headless=headless)

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
            if result.startswith("[SUSPENDED]"):
                return JSONResponse({"status": "suspended", "message": result}, status_code=202)
                
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
    console.print(f"Browser mode: {'headless' if headless else 'visible (--no-headless)'}")
    uvicorn.run(api, host=host, port=port)


def main():
    app()


if __name__ == "__main__":
    main()
