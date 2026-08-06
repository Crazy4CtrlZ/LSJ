"""CI-required test #2: MCP tool discovery + real tool calls through the MCP layer (rubric §8).

Spawns the actual server subprocess over stdio — the same path the deployed agent uses.
"""
import pytest

from app.mcp_client import MCPClient

EXPECTED_TOOLS = {
    "search_policy_documents", "get_policy_section", "lookup_employee_profile",
    "check_pto_balance", "lookup_benefits_status", "create_mock_hr_ticket", "draft_hr_email",
}


@pytest.mark.asyncio
async def test_discovery_and_calls():
    mcp = MCPClient()
    await mcp.connect()
    try:
        names = {t["function"]["name"] for t in mcp.tools}
        assert EXPECTED_TOOLS <= names, f"missing tools: {EXPECTED_TOOLS - names}"

        # data tool happy path (contract envelope + known mock value)
        r = await mcp.call("check_pto_balance", {"employee_id": "EMP004"})
        assert r["ok"] is True
        assert r["data"]["available_days"] == 6.69

        # graceful failure: unknown employee
        r = await mcp.call("lookup_employee_profile", {"employee_id": "EMP999"})
        assert r["ok"] is False and r["error"]["code"] == "NOT_FOUND"

        # ineligibility is data, not an error (contractor)
        r = await mcp.call("check_pto_balance", {"employee_id": "EMP003"})
        assert r["ok"] is True and r["data"]["pto_eligible"] is False

        # action safety: unconfirmed ticket must be refused
        r = await mcp.call("create_mock_hr_ticket", {
            "employee_id": "EMP004", "category": "Time Off", "summary": "test", "confirmed": False})
        assert r["ok"] is False and r["error"]["code"] == "CONFIRMATION_REQUIRED"

        # confirmed mock ticket succeeds, in memory only
        r = await mcp.call("create_mock_hr_ticket", {
            "employee_id": "EMP004", "category": "Time Off", "summary": "test ticket", "confirmed": True})
        assert r["ok"] is True and r["data"]["mock"] is True and r["data"]["ticket_id"].startswith("TCK-")

        # draft tool never sends
        r = await mcp.call("draft_hr_email", {
            "employee_id": "EMP004", "to_role": "manager", "subject": "PTO request", "context": "3 days next week"})
        assert r["ok"] is True and "DRAFT" in r["data"]["disclaimer"]
    finally:
        await mcp.close()
