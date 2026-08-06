# Design and Evaluation — LSJ HR Copilot

## 1. Architecture

Single free-tier web service (the rubric-recommended pattern), also runnable locally:

```
Browser ──HTTP──▶ FastAPI Web App          GET / (chat UI) · POST /chat · GET /health
                     │
                Agent Orchestrator         agentic loop · guardrails · operational trace
                     │            ⇄        Groq LLM (llama-3.3-70b-versatile, temperature 0)
                MCP Client                 official Python SDK · stdio · tool discovery at startup
                     │  JSON-RPC/stdio
                MCP Server (FastMCP)       7 tools (contract v1.0 below)
                 ├── RAG tools ──▶ ChromaDB persistent index  ◀── ingestion of corpus/ (MD·HTML·PDF·TXT)
                 └── data tools ─▶ mock_data/*.json           (runtime writes: in-memory only)
```

Separation of concerns maps to the AI Agents course's single-agent model: **reasoning layer** = the
LLM; **orchestration layer** = `app/orchestrator.py` (the LLM never calls tools directly); **tool
layer** = the MCP server. CI/CD (GitHub Actions) gates a Render deploy hook on green tests.

## 2. Design choices and justifications

| Choice | Decision | Why |
|---|---|---|
| Orchestration | Manual tool-use loop (no LangChain) | Full control of the rubric-required trace format; fewer dependencies on a 512 MB instance; easier to explain in the demo. Deliberate deviation from the course's LangChain examples. |
| MCP transport | stdio subprocess | Rubric-sanctioned; a genuine MCP session with discovery; HTTP is a one-line change (`mcp.run(transport="streamable-http")`), documented not deployed. |
| Server package name | `mcp_server/` (the rubric's "mcp/ or equivalent") | A top-level `mcp/` would shadow the installed MCP SDK package in Python's import system. |
| Embedding model | all-MiniLM-L6-v2 (ONNX build bundled by ChromaDB) | Free, local, no API/network at query time, small enough for Render's 512 MB; same model family taught in the course. |
| Vector store | ChromaDB, persistent, embedded | Zero cost, no external service, deterministic rebuild at deploy; rubric explicitly allows a local store built during deployment. |
| Chunking | Heading-aware (content-aware) per numbered section; token-window (350 words, 60 overlap) fallback | Corpus documents all carry numbered sections → chunks align to citable units (doc_id + §section); overlap prevents boundary loss. Stable chunk ids make ingestion deterministic (fixed-seed requirement). |
| Retrieval | top-k (default k=4, env-tunable) + optional doc/category filters; agent performs query rewriting naturally in the loop | k chosen by ablation (§5); filters exposed as tool parameters so the agent can narrow scope. |
| LLM | Groq free tier, llama-3.3-70b-versatile, temperature 0 | Free, fast, native tool calling; deterministic-leaning outputs for reproducible demos. Fallback model (llama-3.1-8b-instant) and OpenRouter documented via env vars. |
| Safety guardrails | See §4 | Rubric §3/§4 requirements mapped one-to-one. |

## 3. MCP server design and tool schemas (contract v1.0)

Envelopes: success `{"ok": true, "data": {...}}`; failure `{"ok": false, "error": {"code", "message"}}`
with codes `NOT_FOUND · INVALID_ARGUMENT · NOT_ELIGIBLE · CONFIRMATION_REQUIRED · INTERNAL`.
Ineligibility (contractor/intern) is **data** (`eligible: false` + policy-cited `reason`), not an error.

| # | Tool | Backing | Key params |
|---|---|---|---|
| 1 | `search_policy_documents` | RAG index | query, k (1–10), doc_filter?, category_filter? |
| 2 | `get_policy_section` | sections store | doc_id, section ("3" ⇒ all 3.x) |
| 3 | `lookup_employee_profile` | mock JSON | employee_id (^EMP\d{3}$) |
| 4 | `check_pto_balance` | mock JSON | employee_id |
| 5 | `lookup_benefits_status` | mock JSON | employee_id |
| 6 | `create_mock_hr_ticket` | in-memory store | employee_id, category (POL-015 §3 list), summary ≤300, priority, **confirmed** |
| 7 | `draft_hr_email` | template + profile | employee_id, to_role, subject ≤120, context |

Discovery: at app startup the MCP client opens a stdio session, calls `list_tools`, and converts the
returned schemas to the LLM's tool format — the agent's capabilities are exactly what the server
advertises; nothing is hard-coded (tested in `tests/test_mcp_discovery.py`).

## 4. Agent orchestration and safety

Loop (max 6 rounds): LLM sees system prompt + history + discovered tools → returns either a final
answer or tool calls → orchestrator executes each via MCP, appends results, repeats. Every round
appends to the **operational trace**: tool, arguments, ok/error code, result summary — surfaced in
the UI ("What the AI did") and returned by `/chat` (never hidden chain-of-thought).

Guardrails: (1) answer policy questions only from retrieved evidence, cite `[POL-xxx §y.z]` per claim;
(2) empty retrieval ⇒ say so + route to an HR case (no unsupported claims); (3) out-of-corpus topics ⇒
refuse and redirect; (4) facts vs recommendations kept distinct; (5) prompt-injection resistance
(instructions to bypass rules are ignored — eval item Q25); (6) **action safety**: `confirmed=true` on
ticket creation is set from the user's explicit UI confirmation only — the orchestrator overwrites
whatever the model supplies; drafts never send; Conduct—Sensitive cases route to humans (POL-015 §5).
Failure handling: unknown employee ⇒ NOT_FOUND ⇒ clarifying question; MCP down ⇒ honest degraded
answer; ambiguous requests ⇒ clarification (eval Q20–Q22).

## 5. Evaluation

Set: `evaluation/eval_set.jsonl` — 25 items with gold answers and expected tools/citations across
five categories (7 simple · 5 multi-document · 7 tool-requiring · 3 ambiguous · 3 out-of-scope/safety).
Harness: `evaluation/run_eval.py` reports citation accuracy, groundedness proxy, tool-selection
accuracy, workflow completion, clarification accuracy, refusal accuracy, action-safety pass rate,
and latency p50/p95 (cold vs warm run separately). Citation-quality framing follows ALCE
(Gao et al., 2023: citation recall/precision).

**Results (fill in after deployment):**

| Metric | k=2 | k=4 (default) | k=8 |
|---|---|---|---|
| Citation accuracy | – | – | – |
| Groundedness proxy | – | – | – |
| Tool selection accuracy | – | – | – |
| Workflow completion | – | – | – |
| Clarification / refusal accuracy | – | – | – |
| Action-safety pass rate | – | – | – |
| Latency p50 / p95 (warm) | – | – | – |

Cold start (first request after sleep): _measure and record_.

## 6. The two demo tasks (expected MCP call sequences)

**Demo A — PTO request guidance (EMP004):** `lookup_employee_profile` → `check_pto_balance`
(6.69 days available) → `search_policy_documents("PTO notice manager approval")` (POL-001 §3.1–3.3,
POL-010 §4) → synthesized nuance: balance ✓, 10-business-day notice ✗ ⇒ manager-discretion path →
on user confirmation: `draft_hr_email` (draft to manager) and/or `create_mock_hr_ticket`.

**Demo B — International remote work (EMP007):** `lookup_employee_profile` (Restricted-data role) →
`check_pto_balance` (5/20 intl days used ⇒ 15 left) → `search_policy_documents` ×2–3 (POL-002 §5.1/§5.4,
POL-007 §6, POL-010 §4) → computation 30 > 15 ⇒ exceeds cap ⇒ Legal & Tax exception path + clean-device
note → offer Workplace case (confirmation-gated). Multi-document retrieval showcase.
