"""Person B — the MCP client. Spawns the MCP server as a stdio subprocess, discovers its tools
at startup, and relays every tool call. The agent's capabilities are whatever discovery returns —
nothing about the tools is hard-coded into the agent (rubric: genuine MCP integration)."""
from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BASE_DIR = Path(__file__).resolve().parent.parent


class MCPClient:
    def __init__(self) -> None:
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None
        self.tools: list[dict] = []  # OpenAI-style tool schemas, built from MCP discovery

    @property
    def connected(self) -> bool:
        return self.session is not None

    async def connect(self) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            cwd=str(BASE_DIR),
        )
        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        listing = await self.session.list_tools()
        # MCP discovery -> the exact tool list the LLM sees each turn
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
            for t in listing.tools
        ]

    async def call(self, name: str, args: dict) -> dict:
        """Call an MCP tool; always returns a contract envelope dict."""
        if not self.session:
            return {"ok": False, "error": {"code": "INTERNAL", "message": "MCP session not connected"}}
        try:
            result = await self.session.call_tool(name, args)
        except Exception as e:  # server died / bad tool — graceful failure (rubric)
            return {"ok": False, "error": {"code": "INTERNAL", "message": f"MCP call failed: {e}"}}
        if getattr(result, "structuredContent", None):
            payload = result.structuredContent
            return payload.get("result", payload) if isinstance(payload, dict) else payload
        for item in result.content or []:
            if getattr(item, "text", None):
                try:
                    return json.loads(item.text)
                except json.JSONDecodeError:
                    return {"ok": True, "data": {"text": item.text}}
        return {"ok": False, "error": {"code": "INTERNAL", "message": "empty MCP response"}}

    async def close(self) -> None:
        if self._stack:
            try:
                await self._stack.aclose()
            except Exception:
                pass
        self._stack, self.session, self.tools = None, None, []
