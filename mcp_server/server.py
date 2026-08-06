"""Person B — the MCP server (FastMCP over stdio). Implements MCP-TOOL-SCHEMAS.md v1.0 exactly.

Seven tools; every one returns the contract envelope:
  success → {"ok": true,  "data": {...}}
  failure → {"ok": false, "error": {"code": CODE, "message": "..."}}
Codes: NOT_FOUND · INVALID_ARGUMENT · NOT_ELIGIBLE (unused: ineligibility is data, not error)
       · CONFIRMATION_REQUIRED · INTERNAL

Action safety (rubric): create_mock_hr_ticket writes to an IN-MEMORY store only and requires
confirmed=true; draft_hr_email produces text and sends nothing.

Run standalone:  python -m mcp_server.server   (the app's MCP client spawns this as a subprocess)
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app import config  # noqa: E402

mcp = FastMCP("lsj-hr-tools")

EMP_RE = re.compile(r"^EMP\d{3}$")
DOC_RE = re.compile(r"^POL-\d{3}$")
CATEGORIES = ["Time Off", "Leave — Extended", "Benefits", "Payroll", "Workplace", "Conduct — Sensitive", "Other"]


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data}


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------- mock data (read once; writes stay in memory)
def _load(name: str) -> dict:
    return json.loads((config.DATA_DIR / name).read_text(encoding="utf-8"))


_employees = {e["employee_id"]: e for e in _load("employees.json")["employees"]}
_balances = {b["employee_id"]: b for b in _load("pto_balances.json")["balances"]}
_benefits = {r["employee_id"]: r for r in _load("benefits.json")["records"]}
_tickets_file = _load("tickets.json")
_tickets: list[dict] = list(_tickets_file["tickets"])          # in-memory copy — disk file is never mutated
_next_ticket = int(_tickets_file["_meta"]["next_ticket_id"].split("-")[1])


# ---------------------------------------------------------------- RAG-backed tools (contract #1, #2)
@mcp.tool()
def search_policy_documents(query: str, k: int = 4, doc_filter: str = "", category_filter: str = "") -> dict:
    """Semantic search over LSJ's policy library. Returns the k most relevant policy excerpts with
    citation metadata (doc_id, section, snippet, similarity score). Use this to find policy evidence
    before answering any policy question. Empty results mean the corpus does not cover the topic."""
    if not query.strip():
        return _err("INVALID_ARGUMENT", "query must be a non-empty string")
    try:
        from rag import retrieve

        if not retrieve.index_ready():
            return _err("INTERNAL", "policy index not built — run `python -m rag.ingest` first")
        results = retrieve.search(query, k=k, doc_filter=doc_filter or None,
                                  category_filter=category_filter or None)
        return _ok({"results": results})
    except Exception as e:  # graceful failure (rubric)
        return _err("INTERNAL", f"search failed: {e}")


@mcp.tool()
def get_policy_section(doc_id: str, section: str) -> dict:
    """Fetch the exact text of one policy section (e.g. doc_id='POL-001', section='3.1') for precise
    citation or quoting. section='3' returns all 3.x subsections of that document."""
    if not DOC_RE.match(doc_id):
        return _err("INVALID_ARGUMENT", "doc_id must look like POL-001")
    try:
        from rag import retrieve

        if not retrieve.index_ready():
            return _err("INTERNAL", "policy index not built — run `python -m rag.ingest` first")
        sec = retrieve.get_section(doc_id, section)
        if sec is None:
            return _err("NOT_FOUND", f"{doc_id} §{section} does not exist")
        return _ok(sec)
    except Exception as e:
        return _err("INTERNAL", f"lookup failed: {e}")


# ---------------------------------------------------------------- mock-data tools (contract #3, #4, #5)
@mcp.tool()
def lookup_employee_profile(employee_id: str) -> dict:
    """Look up an employee's profile: name, role, department, manager, office, employment type,
    tenure, work arrangement. Requires employee_id like EMP004."""
    if not EMP_RE.match(employee_id):
        return _err("INVALID_ARGUMENT", "employee_id must look like EMP004")
    emp = _employees.get(employee_id)
    if not emp:
        return _err("NOT_FOUND", f"no employee {employee_id} — ask the user to check their ID")
    data = dict(emp)
    mgr = _employees.get(emp.get("manager_id") or "")
    data["manager_name"] = mgr["name"] if mgr else None
    return _ok(data)


@mcp.tool()
def check_pto_balance(employee_id: str) -> dict:
    """Check an employee's current PTO balance: accrued, used, pending, available days, sick days,
    floating holidays, and international remote-work days used in the rolling 12 months."""
    if not EMP_RE.match(employee_id):
        return _err("INVALID_ARGUMENT", "employee_id must look like EMP004")
    bal = _balances.get(employee_id)
    if not bal:
        return _err("NOT_FOUND", f"no PTO record for {employee_id}")
    data = dict(bal)
    data.setdefault("as_of", "2026-08-04")
    return _ok(data)  # ineligible employees carry pto_eligible=false + reason — data, not an error


@mcp.tool()
def lookup_benefits_status(employee_id: str) -> dict:
    """Check an employee's benefits: eligibility tier, medical plan, dental/vision, 401(k) enrollment
    and employer-match status, covered dependents."""
    if not EMP_RE.match(employee_id):
        return _err("INVALID_ARGUMENT", "employee_id must look like EMP004")
    rec = _benefits.get(employee_id)
    if not rec:
        return _err("NOT_FOUND", f"no benefits record for {employee_id}")
    return _ok(dict(rec))


# ---------------------------------------------------------------- action tools (contract #6, #7)
@mcp.tool()
def create_mock_hr_ticket(employee_id: str, category: str, summary: str,
                          priority: str = "P3", confirmed: bool = False) -> dict:
    """Create a MOCK HR ticket (in-memory only; nothing real happens). REQUIRES confirmed=true,
    which the system sets only after the user explicitly approves — never set it yourself unless
    the user has clearly said yes to creating this ticket."""
    global _next_ticket
    if not confirmed:
        return _err("CONFIRMATION_REQUIRED",
                    "user has not confirmed this action — ask the user for explicit approval first")
    if not EMP_RE.match(employee_id):
        return _err("INVALID_ARGUMENT", "employee_id must look like EMP004")
    if category not in CATEGORIES:
        return _err("INVALID_ARGUMENT", f"category must be one of: {', '.join(CATEGORIES)}")
    if not summary.strip() or len(summary) > 300:
        return _err("INVALID_ARGUMENT", "summary must be 1–300 characters")
    if priority not in ("P1", "P2", "P3"):
        return _err("INVALID_ARGUMENT", "priority must be P1, P2 or P3")
    ticket = {
        "ticket_id": f"TCK-{_next_ticket}",
        "employee_id": employee_id,
        "category": category,
        "priority": priority,
        "status": "open",
        "summary": summary.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mock": True,
    }
    if category == "Conduct — Sensitive":
        ticket["routed_to_human"] = True  # POL-015 §5: humans only — automation just routes
    _next_ticket += 1
    _tickets.append(ticket)
    return _ok(ticket)


@mcp.tool()
def draft_hr_email(employee_id: str, to_role: str, subject: str, context: str) -> dict:
    """Draft (never send) a professional message on the employee's behalf — e.g. a PTO request to
    their manager. Returns draft text for the user to review and send themselves."""
    if not EMP_RE.match(employee_id):
        return _err("INVALID_ARGUMENT", "employee_id must look like EMP004")
    roles = {"manager", "people_operations", "it", "workplace_ops"}
    if to_role not in roles:
        return _err("INVALID_ARGUMENT", f"to_role must be one of: {', '.join(sorted(roles))}")
    if not subject.strip() or len(subject) > 120:
        return _err("INVALID_ARGUMENT", "subject must be 1–120 characters")
    emp = _employees.get(employee_id)
    if not emp:
        return _err("NOT_FOUND", f"no employee {employee_id}")
    if to_role == "manager":
        mgr = _employees.get(emp.get("manager_id") or "")
        to_name = mgr["name"] if mgr else "your manager"
    else:
        to_name = {"people_operations": "People Operations", "it": "IT Support",
                   "workplace_ops": "Workplace Operations"}[to_role]
    body = (
        f"Hi {to_name},\n\n{context.strip()}\n\n"
        f"Please let me know if you need any further details.\n\nBest regards,\n{emp['name']}"
    )
    return _ok({"to_name": to_name, "to_role": to_role, "subject": subject.strip(), "body": body,
                "disclaimer": "DRAFT — review and send yourself; nothing has been sent."})


if __name__ == "__main__":
    mcp.run()  # stdio transport — HTTP is a one-line change: mcp.run(transport="streamable-http")
