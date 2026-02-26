#!/usr/bin/env python3
"""
最小可启动的 GameAuditAgent 示例

运行步骤:
  1. 设置环境变量:
     export LLM_API_KEY="your-api-key"
     export LLM_API_BASE="https://your-api-base"   # 可选

  2. 启动 demo 游戏 (另一个终端):
     cd examples/demo-game && python3 -m http.server 8888

  3. 运行此脚本:
     python3 examples/run_game_audit.py

  也可以用 CLI 方式运行:
     game-audit-agent test --pdf examples/demo-game/guide.md --url http://localhost:8888
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure the project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


async def main():
    """Run a minimal GameAuditAgent against the demo game."""
    from kubemin_agent.agents.game_audit_agent import GameAuditAgent
    from kubemin_agent.providers.litellm_provider import LiteLLMProvider
    from kubemin_agent.session.manager import SessionManager

    # --- Configuration ---
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        print("Error: LLM_API_KEY environment variable is required.")
        print("  export LLM_API_KEY='your-api-key'")
        sys.exit(1)

    api_base = os.environ.get("LLM_API_BASE")
    model = os.environ.get("LLM_MODEL", "openrouter/google/gemini-2.0-flash-001")
    game_url = os.environ.get("GAME_TEST_URL", "http://localhost:8888")
    guide_path = Path(__file__).parent / "demo-game" / "guide.md"

    workspace = Path.home() / ".kubemin-agent" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # --- Create components ---
    print("=" * 60)
    print("  GameAuditAgent - Minimum Viable Example")
    print("=" * 60)
    print(f"  Model:     {model}")
    print(f"  Game URL:  {game_url}")
    print(f"  Guide:     {guide_path}")
    print(f"  Workspace: {workspace}")
    print("=" * 60)
    print()

    provider = LiteLLMProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=model,
    )
    sessions = SessionManager(workspace)

    agent = GameAuditAgent(
        provider=provider,
        sessions=sessions,
        workspace=workspace,
        game_url=game_url,
    )

    # --- Build the task message ---
    task_message = (
        f"Please audit the web game at {game_url}.\n\n"
        f"First, read the gameplay guide at: {guide_path.absolute()}\n"
        f"Then navigate to the game and systematically audit:\n"
        f"1. Game logic correctness (coin flip mechanics, balance changes)\n"
        f"2. Content compliance (text and images)\n"
        f"3. UI/UX quality (interactive elements, layout, feedback)\n\n"
        f"Generate a comprehensive audit report with your findings."
    )

    # --- Run the agent ---
    print("[Starting audit...]\n")
    try:
        result = await agent.run(task_message, session_key="example:game_audit")
        print("\n" + "=" * 60)
        print("  AUDIT REPORT")
        print("=" * 60)
        print(result)
    except KeyboardInterrupt:
        print("\n[Interrupted by user]")
    except Exception as e:
        print(f"\n[Error] {e}")
        raise
    finally:
        await agent.cleanup()
        print("\n[Agent cleanup complete]")


if __name__ == "__main__":
    asyncio.run(main())
