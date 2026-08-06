# LSJ HR Copilot

An agentic AI system that helps employees of **LSJ, Inc.** (a fictional company — all data synthetic)
complete HR policy and operations tasks. It combines **RAG** over a 16-document policy corpus with an
**agent orchestrator** that calls tools exposed by an **MCP server**, producing grounded, **cited**
answers with a visible tool-call trace.

> Quantic MSAIE · AI Engineering Techniques and Architectures · Group project

**Deployed URL:** _add after first Render deploy — see `deployed.md`_

## Architecture (one free-tier service)

```
Browser ── FastAPI (/ · /chat · /health)
              │
        Agent Orchestrator  ←→  Groq LLM (llama-3.3-70b-versatile)
              │  agentic loop · guardrails · trace
        MCP Client (official SDK, stdio)
              │  tool discovery + calls (JSON-RPC)
        MCP Server (FastMCP, 7 tools)          ← mcp_server/
         ├── RAG tools → ChromaDB index        ← rag/ + corpus/ (16 docs: MD, HTML, PDF, TXT)
         └── data tools → mock JSON            ← mock_data/ (writes are in-memory only)
```

Full design rationale: `design-and-evaluation.md`. Tool contract: `MCP-TOOL-SCHEMAS` section there.

## Setup (local)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then put your Groq API key in .env (never commit .env)
python -m rag.ingest            # build the policy index (~1 min first run: embeds 16 docs)
uvicorn app.main:app --reload   # → http://localhost:8000
```

The chat UI has **Demo A / Demo B buttons** that reproduce the two graded agentic tasks in one click.
API alternative:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/chat -H 'content-type: application/json' \
  -d '{"message":"Can I take 3 days of PTO next week?","employee_id":"EMP004"}'
```

## Tests

```bash
pytest -q       # app start · MCP tool discovery + real tool calls · 4-format ingestion · safety gating
```

## Deployment (Render free tier)

1. Push to GitHub — CI runs on every push/PR; **deploy only triggers when tests pass**.
2. Render → New → Blueprint → select this repo (`render.yaml` configures everything).
3. In Render dashboard set env var `GROQ_API_KEY`.
4. Add repo secret `RENDER_DEPLOY_HOOK` (Render → Settings → Deploy Hook) to enable CI-gated deploys.

**Cold starts:** the free instance sleeps after ~15 idle minutes; the next request waits ~30–60 s
(plus index build on the very first boot). This is expected free-tier behavior — see `deployed.md`.

## Evaluation

```bash
uvicorn app.main:app --port 8000        # terminal 1
python evaluation/run_eval.py           # terminal 2 → metrics + evaluation/results/run.json
```

25 scored items across five categories; reports citation accuracy, groundedness proxy, tool-selection
accuracy, workflow completion, clarification/refusal accuracy, action-safety pass rate, latency p50/p95.
Ablation: rerun the server with `RETRIEVAL_K=2|4|8` and compare reports.

## Repository map

`app/` FastAPI + orchestrator + MCP client · `mcp_server/` MCP server (7 tools) · `rag/` ingestion +
retrieval · `corpus/` policy documents · `mock_data/` synthetic datasets · `evaluation/` eval set +
harness · `tests/` CI suite · required docs: `design-and-evaluation.md`, `ai-tooling.md`, `deployed.md`.
