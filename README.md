# KubeMin-Agent

KubeMin-Agent 是一个基于 LangChain 框架所编写的一系列 Agent 服务，主要分为三个服务模块：

1. 自动化测试：通过控制浏览器控制页面，以自动化完成一系列点击事件，达成黑盒测试的目的
2. 构建安全沙箱：构建一个安全的沙箱环境，进行自动化测试
3. API 工具调用：通过调用 API 工具（调用 KubeMin-Cli）服务来构建生产级别的工作流

## Miniconda 环境配置

使用 Miniconda 创建并激活本项目的开发环境：

```bash
conda env create -f environment.yml
conda activate kubemin-agent
```

启动服务：

```bash
uvicorn app.main:app --reload
```
