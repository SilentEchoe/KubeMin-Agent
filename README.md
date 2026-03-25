# KubeMin-Agent

> Intelligent AI assistant for cloud-native application management on the KubeMin platform.

KubeMin-Agent 是一个基于 LLM 的智能代理，支持 Kubernetes 集群运维、应用巡检、游戏审计等场景。底层通过 [LiteLLM](https://github.com/BerriAI/litellm) 统一路由，兼容主流 LLM 供应商。

---

## 📋 环境要求

- **Python** ≥ 3.11
- **pip** (推荐使用 `venv` 虚拟环境)

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/SilentEchoe/KubeMin-Agent.git
cd KubeMin-Agent

# 创建并激活虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # macOS / Linux
# .venv\Scripts\activate   # Windows

# 安装项目（可编辑模式）
pip install -e .

# 如需开发/测试工具
pip install -e ".[dev]"
```

### 2. 初始化配置

```bash
kubemin-agent onboard
```

该命令会在 `~/.kubemin-agent/` 下生成默认配置文件和工作目录。

### 3. 配置 LLM Provider

编辑 `~/.kubemin-agent/config.json`，在 `providers` 下填写你的 API Key。

#### 使用 Anthropic Claude（默认）

```yaml
providers:
  anthropic:
    api_key: "sk-ant-xxxxx"

agents:
  defaults:
    model: "anthropic/claude-sonnet-4-20250514"
```

#### 使用 OpenAI / GPT

```yaml
providers:
  openai:
    api_key: "sk-xxxxx"

agents:
  defaults:
    model: "openai/gpt-4o"
```

#### 使用 OpenAI 兼容 API（Kimi / DeepSeek / 通义千问等）

国产大模型大多提供 OpenAI 兼容接口，只需设置 `api_base` 指向对应地址：

```yaml
providers:
  openai:
    api_key: "你的 API Key"
    api_base: "https://api.moonshot.cn/v1"      # Kimi
    # api_base: "https://api.deepseek.com"       # DeepSeek
    # api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 通义千问

agents:
  defaults:
    model: "openai/moonshot-v1-8k"              # 按实际模型名填写
```

#### 使用 OpenRouter（多模型聚合）

```yaml
providers:
  openrouter:
    api_key: "sk-or-xxxxx"

agents:
  defaults:
    model: "anthropic/claude-sonnet-4-20250514"  # OpenRouter 支持的任意模型
```

> [!TIP]
> model 格式为 `<provider>/<model-name>`，LiteLLM 通过前缀自动路由到对应供应商。

### 4. 启动 Agent

#### 交互式对话

```bash
kubemin-agent agent
```

#### 单次提问

```bash
kubemin-agent agent -m "检查集群中所有 Pod 的状态"
```

#### 启动 Gateway（Agent + 频道 + 定时任务）

```bash
kubemin-agent gateway
```

Gateway 模式会同时启动 Agent 服务、Telegram/飞书频道监听和定时巡检任务。

> [!IMPORTANT]
> 全局沙箱默认 `strict`。`agent/gateway/patrol` 启动时会先做沙箱预检：
> - 本地优先使用容器后端（docker/podman）重启到沙箱内
> - 若 strict 且无可用后端，会直接失败（fail closed）
> - 若启用默认拒绝网络策略，必须配置 `sandbox.network.proxy_url`

推荐配置示例：

```yaml
sandbox:
  mode: strict
  backends: [container, bwrap]
  container:
    runtime: docker
    image: kubemin-agent:latest
  network:
    default_deny: true
    enforce_proxy: true
    proxy_url: "http://egress-proxy.default.svc.cluster.local:3128"
    allowlist:
      - api.openai.com
      - openrouter.ai
      - api.telegram.org
```

---

## 📖 CLI 命令一览

| 命令 | 说明 |
|------|------|
| `kubemin-agent onboard` | 初始化配置和工作目录 |
| `kubemin-agent agent` | 启动交互式 Agent 对话 |
| `kubemin-agent gateway` | 启动完整 Gateway 服务 |
| `kubemin-agent patrol` | 执行一次性平台巡检 |
| `kubemin-agent status` | 查看当前配置和状态 |
| `kubemin-agent logs` | 查看执行轨迹和评估结果 |

使用 `--help` 查看各命令的详细参数：

```bash
kubemin-agent agent --help
```

---

## 🐳 Docker 部署

```bash
# 构建镜像
docker build -t kubemin-agent .

# 运行（以 GameAuditAgent 为例）
docker run -p 8080:8080 \
  -e LLM_API_KEY="你的 API Key" \
  -e LLM_API_BASE="https://api.moonshot.cn/v1" \
  -e GAME_TEST_URL="https://game.example.com" \
  kubemin-agent
```

---

## 🧪 开发与测试

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check .
```

---

## ⚠️ 注意事项

- **Tool Calling 支持**：KubeMin-Agent 重度依赖 Function Calling 能力。请确保所选模型支持 tool/function calling（如 Claude 3.5+、GPT-4o、Kimi moonshot-v1 等）。
- **Kimi 等国产模型**：对于复杂的多步推理任务，tool calling 质量可能不如 Claude / GPT-4o 稳定，建议先在简单场景下验证。
- **环境变量**：也可以通过环境变量配置，前缀为 `KUBEMIN_AGENT__`，嵌套用双下划线分隔，例如：
  ```bash
  export KUBEMIN_AGENT__PROVIDERS__OPENAI__API_KEY="你的 Key"
  ```

---

## 📄 License

[MIT](LICENSE)
