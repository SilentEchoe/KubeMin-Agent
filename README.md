# KubeMin-Agent

KubeMin-Agent 是一个基于 LangChain 框架所编写的一系列 Agent 服务，主要分为三个服务模块：

1. 自动化测试：通过控制浏览器控制页面，以自动化完成一系列点击事件，达成黑盒测试的目的
2. 构建安全沙箱：构建一个安全的沙箱环境，进行自动化测试
3. API 工具调用：通过调用 API 工具（调用 KubeMin-Cli）服务来构建生产级别的工作流

## 项目结构

```
app/
  api/            # FastAPI 路由与版本管理
  agents/         # LangChain Agent 抽象与实现
  chains/         # LangChain Chain 构建
  core/           # 配置、日志等核心模块
  middlewares/    # 中间件（请求追踪等）
  schemas/        # 请求/响应数据模型
  services/       # 业务服务层
```

## Miniconda 环境配置

使用 Miniconda 创建并激活本项目的开发环境：

```bash
conda env create -f environment.yml
conda activate kubemin-agent
```

可选：创建本地环境变量文件

```bash
cp .env.example .env
```

启动服务：

```bash
uvicorn app.main:app --reload
```

示例请求：

```bash
curl http://127.0.0.1:8000/api/v1/healthz
curl -X POST http://127.0.0.1:8000/api/v1/agents/run \\
  -H 'Content-Type: application/json' \\
  -d '{\"query\":\"hello\"}'
```
