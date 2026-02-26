FROM python:3.12-slim AS base

# -- System dependencies --
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chrome dependencies
    chromium \
    fonts-liberation \
    fonts-noto-cjk \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libgtk-3-0 \
    # Node.js (for chrome-devtools-mcp via npx)
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# -- Python dependencies --
WORKDIR /app
COPY pyproject.toml .
COPY kubemin_agent/ kubemin_agent/

RUN pip install --no-cache-dir -e .

# -- Runtime configuration --
# Tell MCPClient we are in a container (enables --no-sandbox for Chrome)
ENV CONTAINER=true
# Chrome binary path for Debian/Ubuntu
ENV CHROME_PATH=/usr/bin/chromium

# Workspace for screenshots, reports, etc.
ENV KUBEMIN_AGENT_WORKSPACE=/data/workspace
RUN mkdir -p /data/workspace /data/guides

# Game URL is provided at runtime via environment variable
ENV GAME_TEST_URL=""
ENV LLM_API_KEY=""
ENV LLM_API_BASE=""

EXPOSE 8080

ENTRYPOINT ["game-audit-agent"]
CMD ["serve", "--port", "8080"]
