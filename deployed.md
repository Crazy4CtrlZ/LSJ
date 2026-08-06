# Deployed Application

| Item | Value |
|---|---|
| Deployed URL | https://lsj-ej43.onrender.com |
| Health endpoint | https://lsj-ej43.onrender.com/health |
| Host | Render free tier (single web service) |

Verified 2026-08-06: `/health` → `{"status":"ok","mcp_connected":true,"tools_count":7,"index_size":212,`
`"model":"llama-3.3-70b-versatile","llm_configured":true}`; Demo A (`/chat`, EMP004) returns a grounded
answer with full tool trace.

## Free-tier cold-start notes
- The instance sleeps after ~15 minutes of inactivity; the next request takes ~30–60 s while it wakes.
- The policy index is built during the **build phase** (`buildCommand` runs `python -m rag.ingest`;
  `BUILD_INDEX_ON_START=0`), so the 512 MB runtime instance only reads the index — building it at
  runtime exceeded the memory limit. Note: the service was created via the dashboard, so Build Command
  and env vars are maintained in the dashboard (render.yaml is kept in sync for documentation/Blueprint use).
- For the demo video we warm the service beforehand; evaluation reports cold and warm latency separately.
