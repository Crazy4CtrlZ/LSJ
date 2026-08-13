"""Person C — the FastAPI web application: chat UI, /chat, /health (rubric §6).

Startup (lifespan): optionally build the RAG index if missing, then connect the MCP client
(spawning the tool server as a stdio subprocess) and create the orchestrator.
Run locally:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from app import config  # noqa: E402
from app.mcp_client import MCPClient  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    from rag import ingest, retrieve

    if config.BUILD_INDEX_ON_START and not retrieve.index_ready():
        try:
            n = ingest.build_index()
            print(f"[startup] built policy index: {n} chunks")
        except Exception as e:  # keep serving; /health will show the gap
            print(f"[startup] index build failed: {e}")

    app.state.mcp = MCPClient()
    try:
        await app.state.mcp.connect()
        print(f"[startup] MCP connected — {len(app.state.mcp.tools)} tools discovered")
    except Exception as e:
        print(f"[startup] MCP connect failed: {e}")
    app.state.orchestrator = Orchestrator(app.state.mcp)
    yield
    await app.state.mcp.close()


app = FastAPI(title="LSJ HR Copilot", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    employee_id: str | None = None
    history: list[dict] = Field(default_factory=list)  # [{role, content}] prior turns
    confirm_action: bool = False  # user ticked "I confirm the proposed action"


@app.get("/")
async def home():
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


@app.get("/health")
async def health():
    from rag import retrieve

    mcp = app.state.mcp
    return JSONResponse({
        "status": "ok",
        "mcp_connected": mcp.connected,
        "tools_count": len(mcp.tools),
        "index_size": retrieve.index_size() if retrieve.index_ready() else 0,
        "model": config.MODEL,
        "llm_configured": bool(config.GROQ_API_KEY),
    })


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        result = await app.state.orchestrator.chat(
            message=req.message, employee_id=req.employee_id,
            history=req.history, confirm_action=req.confirm_action,
        )
    except Exception as e:  # never surface a bare 500 to the UI — degrade honestly (rubric: graceful failure)
        print(f"[chat] unhandled error: {type(e).__name__}: {e}")
        result = {"answer": "Something went wrong handling this request. Please try again — if it persists, "
                            "the service may be rate-limited or restarting.",
                  "citations": [], "snippets": [], "tool_trace": [], "degraded": True}
    return JSONResponse(result)
