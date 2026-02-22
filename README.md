# KubeMin-Agent (CLI) - Enterprise Production Grade

> **Production Grade Read-Only Diagnostic Agent**  
> Part of the KubeMin ecosystem. Designed for "Observability, Revivability, Evaluability, Governability, and Evolvability".

KubeMin-Agent is a CLI-first intelligent agent designed to diagnose Kubernetes applications within a strictly controlled information domain. It leverages the KubeMin-Cli API to safely retrieve pods, logs, and metrics, preventing direct uncontrolled access to the cluster.

---

## 0. Scope & Non-Goals

### Scope (Phase 1: Read-Only)
- **Form Factor**: CLI (`kubemin-agent`)
- **Data Source**: Strictly via **KubeMin-Cli / KubeMin API** (No direct K8s access).
- **Core Evidence**: Pod Summaries, Logs, Prometheus Metrics.
- **Output**: Structured JSON Reports + Human-friendly summaries.

### Non-Goals
- No write operations (scaling, restarting, patching).
- No multi-agent collaboration (v1).
- No interactive confirmation loops (autonomy within strict read-only bounds).

---

## 1. Top Use Cases

1. **App Instability**: Diagnosing CrashLoopBackOff, OOMKilled, Liveness probe failures.
2. **Performance Degradation**: CPU/Memory throttling, latency spikes.
3. **Post-Release Failure**: Correlating events, logs, and metrics to identify root causes.
4. **Audit & Replay**: every diagnosis has a `run_id` and full evidence chain.

---

## 2. Architecture

The agent follows a strict **Plan -> Execute -> Verify -> Report** state machine architecture.

```
┌─────────────────────────────┐
│ CLI (Typer/Rich)            │  Input/Output
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Orchestrator (State Machine) │  Core Logic
│ - budget / retry / timeout   │  Safety rails
│ - run_store / replay         │  Audit trail
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Tool Runtime (Allowlist)     │  Safe Execution
│ - kubemin: pods/logs/prom    │  API Proxy
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│ Model Gateway (LLM)          │  Intelligence
│ - schema-enforced outputs    │  Strict JSON
└──────────────┬──────────────┘
```

## 3. Getting Started

### Prerequisites
- Python 3.10+
- KubeMin-Cli configured and running.

### Installation

```bash
pip install -r requirements.txt
# or via pipx
# pipx install .
```

### Usage

**Diagnose an Application:**
```bash
python cli.py inspect --app my-app-id -n default "Why is it restarting?"
```

**Replay a Past Run:**
```bash
python cli.py replay --run <run_uuid>
```

---

## 4. Directory Structure

```
.
├── cli.py                  # Entrypoint
├── config.py               # Configuration & Env Vars
├── runtime/                # Core Logic
│   ├── orchestrator.py
│   ├── run_store.py
│   └── budget.py
├── tools/                  # Safe Tool Definitions
│   ├── base.py
│   └── kubemin_api.py
├── model/                  # LLM Integration
│   ├── gateway.py
│   └── schemas.py
└── eval/                   # QA & Testing
    └── runner.py
```

## 5. Nanobot-style General Agent (New)

This repository now includes a general-purpose chat agent inspired by nanobot:

- Tool-calling loop (LLM -> tools -> LLM)
- Built-in tools: `read_file`, `write_file`, `list_dir`, `exec`
- Session persistence: `~/.kubemin-agent/sessions`
- Workspace safety guard for file and shell operations

### Quick start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure API key (either one):

```bash
export KUBEMIN_AGENT_API_KEY="your_api_key"
# or
export OPENAI_API_KEY="your_api_key"
```

3. Run one-shot message:

```bash
python cli.py agent -m "List files in my workspace"
```

4. Run interactive mode:

```bash
python cli.py agent
```

### Config notes

- Workspace path: `KUBEMIN_AGENT_WORKSPACE` (default `~/.kubemin-agent/workspace`)
- Model: `KUBEMIN_AGENT_MODEL` (default `gpt-4o-mini`)
- API base: `KUBEMIN_AGENT_API_BASE` (default `https://api.openai.com/v1`)
- Safety: `KUBEMIN_AGENT_RESTRICT_WORKSPACE=true` keeps tools in workspace only
