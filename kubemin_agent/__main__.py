"""CLI entry point for kubemin-agent."""

import sys

from kubemin_agent.cli.commands import app

if __name__ == "__main__":
    app()
