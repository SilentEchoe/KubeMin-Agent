"""GameTestAgent - Web game testing and auditing specialist."""

from pathlib import Path

from kubemin_agent.agents.base import BaseAgent
from kubemin_agent.agent.tools.mcp_client import MCPClient
from kubemin_agent.agent.tools.pdf_reader import PDFReaderTool
from kubemin_agent.agent.tools.browser import BrowserTool
from kubemin_agent.agent.tools.screenshot import ScreenshotTool
from kubemin_agent.agent.tools.content_audit import ContentAuditTool
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


class GameTestAgent(BaseAgent):
    """
    Web game testing and auditing sub-agent.

    Reads PDF gameplay guides, then uses Chrome DevTools MCP to
    automate browser interactions and verify game logic correctness,
    content compliance, and UI/UX quality.

    Can run as a sub-agent within the control plane or as a standalone service.
    """

    def __init__(
        self,
        provider: LLMProvider,
        sessions: SessionManager,
        workspace: Path | None = None,
        headless: bool = True,
    ) -> None:
        self._workspace = workspace or Path.home() / ".kubemin-agent" / "workspace"
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._mcp = MCPClient(headless=headless)
        super().__init__(provider, sessions)

    @property
    def name(self) -> str:
        return "game_test"

    @property
    def description(self) -> str:
        return (
            "Tests and audits web games by reading PDF gameplay guides "
            "and automating browser interactions via Chrome DevTools MCP "
            "to verify game logic correctness, content compliance, and UI/UX quality."
        )

    @property
    def system_prompt(self) -> str:
        return (
            "You are GameTestAgent, a web game testing and auditing specialist.\n\n"
            "Your workflow:\n"
            "1. First, read the PDF gameplay guide using 'read_pdf' to understand the expected game behavior\n"
            "2. Navigate to the game URL using 'browser_action' with action='navigate'\n"
            "3. Use 'browser_action' with action='snapshot' to get the page structure with element uids\n"
            "4. Systematically test the game by clicking/filling elements using their uids\n"
            "5. Take screenshots at key moments to document findings\n"
            "6. Audit game content for compliance using 'audit_content'\n"
            "7. Generate a detailed test report\n\n"
            "IMPORTANT: Element interaction uses uid-based targeting.\n"
            "- Always call 'snapshot' first to see available elements and their uids\n"
            "- Use the uid from the snapshot when calling click, fill, hover, etc.\n"
            "- After each interaction, the response may include an updated snapshot\n\n"
            "Your testing scope:\n"
            "- **Logic Verification**: Test if game rules execute correctly as described in the guide\n"
            "- **Content Audit**: Check text and images for policy violations\n"
            "- **UI/UX Testing**: Verify interactive elements work, layout is correct, feedback is clear\n"
            "- **Console Errors**: Check for JavaScript errors via 'browser_action' with action='console_logs'\n"
            "- **Network**: Check for failed API calls via 'browser_action' with action='network'\n\n"
            "Test report format:\n"
            "## Test Report\n"
            "### 1. Game Overview\n"
            "### 2. Logic Test Results\n"
            "### 3. Content Audit Results\n"
            "### 4. UI/UX Findings\n"
            "### 5. Console/Network Issues\n"
            "### 6. Issues Found\n"
            "### 7. Overall Assessment (PASS/FAIL/CONDITIONAL)\n\n"
            "Be thorough, systematic, and document every finding with evidence (screenshots, element states)."
        )

    def _register_tools(self) -> None:
        """Register game testing specific tools."""
        self.tools.register(PDFReaderTool())
        self.tools.register(BrowserTool(self._mcp))
        self.tools.register(ScreenshotTool(self._mcp, self._workspace))
        self.tools.register(ContentAuditTool(self._mcp))

    async def cleanup(self) -> None:
        """Clean up resources (stop MCP server)."""
        await self._mcp.stop()
