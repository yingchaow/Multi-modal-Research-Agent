# Multi-modal Research Agent

A LangGraph-based multi-agent research assistant for discovering papers, analyzing multi-modal paper content, and generating structured academic research reports with human-in-the-loop control.

The system combines paper retrieval, LLM-based paper screening, PDF/image analysis, report planning, review, and knowledge-base retrieval into a single workflow exposed through a FastAPI + SSE web interface.

## Features

- **Multi-agent workflow**: coordinates specialized agents for topic refinement, arXiv retrieval, multi-modal paper analysis, report writing, review, and supervision.
- **Skill-based agent modules**: core capabilities such as architect writing, human interaction, multi-modal analysis, and arXiv paper screening are packaged as reusable skills.
- **Human-in-the-loop decisions**: lets the user approve, reject, revise, or restart parts of the workflow from the web UI.
- **Paper screening**: uses an LLM with few-shot criteria to decide whether each crawled arXiv paper is worth downstream reading.
- **Multi-modal paper analysis**: downloads papers and extracts useful technical signals from figures, diagrams, and experimental results.
- **Knowledge-base retrieval**: stores core knowledge from selected papers and lets future reports reuse related research insights.
- **Streaming web experience**: FastAPI + Server-Sent Events provide real-time progress updates and streamed report generation.
- **Persistent workflow state**: Redis-backed checkpointing supports session recovery by thread ID.

## Project Structure

```text
.
├── agent_nodes/          # Thin LangGraph node wrappers
├── core/                 # Session and runtime utilities
├── integrations/         # External service integrations
├── memory/               # Local memory, paper history, and knowledge storage
├── scripts/              # Utility and debugging scripts
├── skills/               # Reusable skill modules used by agents
├── workflow/             # LangGraph workflow definition
├── server.py             # FastAPI web server
├── index.html            # Frontend console
├── config.py             # Model and service configuration
└── docker-compose.yml    # Local service orchestration
```

## Workflow

1. The user enters a research topic in the web interface.
2. The human-interaction skill converts the topic into arXiv-friendly English keywords.
3. The arXiv agent retrieves candidate papers and calls the paper-screening skill.
4. The multi-modal skill analyzes the selected paper and its figures.
5. The architect skill drafts a structured report using paper content and relevant knowledge-base entries.
6. The user reviews the outline/report and can approve, reject, revise, or request a new paper.
7. The system produces the final Markdown-style research report.

## Quick Start

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example environment file and fill in your own keys:

```bash
cp .env.example .env
```

Required or commonly used variables:

```env
ChatTongyi_API_KEY=
S2_API_KEY=
QDRANT_API_KEY=
QDRANT_URL=http://qdrant:6333
QDRANT_CLOUDE_URL=
vision_model_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
REDIS_HOST=redis
REDIS_PORT=6379
```

### 4. Run with Docker Compose

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8000
```

### 5. Run locally without Docker

Start Redis separately, then run:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

## Runtime Data

The following files and directories are generated locally and intentionally ignored by Git:

- `.env`
- `.venv/`
- `__pycache__/`
- `papers/`
- `feedback_memory_db/`
- `qdrant_storage/`
- `*.sqlite`, `*.sqlite-shm`, `*.sqlite-wal`

Use `.env.example` as the public template for required configuration.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
