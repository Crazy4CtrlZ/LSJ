# Design and Evaluation — LSJ HR Copilot

## 1. Architecture

Single free-tier web service (the rubric-recommended pattern), also runnable locally:

```
Browser ──HTTP──▶ FastAPI Web App          GET / (chat UI) · POST /chat · GET /health
                     │
                Agent Orchestrator         agentic loop · guardrails · operational trace
                     │            ⇄        Groq LLM (openai/gpt-oss-120b, temperature 0)
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
| LLM | Groq free tier, openai/gpt-oss-120b, temperature 0 | Free, fast, native tool calling; deterministic-leaning outputs for reproducible demos. Fallback (openai/gpt-oss-20b) and OpenRouter documented via env vars. **Provider-risk lesson:** the project originally used llama-3.3-70b-versatile; Groq decommissioned all Llama chat models mid-project (2026-08). Because the model is an env-driven config value — not code — the swap was a one-line change, verified by re-running the demo tasks. |
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

**Results — runs of 2026-08-22, openai/gpt-oss-120b, warm local instance
(`evaluation/results/run_k4_baseline.json`, `run_k2.json`; ablation runs force the retrieval depth
via `FORCE_RETRIEVAL_K` — the MCP tool schema defaults `k=4`, so the env default alone would not
ablate. The k=8 pass was halted at item 12/25: the third full pass of the day exhausted the Groq
free-tier daily token pool (TPD 200k), and completing it would only have logged retry-degraded
answers — rerun on a fresh budget rather than record poisoned numbers):**

| Metric | k=2 | k=4 (default) | k=8 |
|---|---|---|---|
| Citation accuracy | **95%** (18/19) | **95%** (18/19) | pending² |
| Groundedness proxy | **100%** | **100%** | – |
| Tool selection accuracy | **89%** (17/19) | **84%** (16/19) | – |
| Workflow completion | **89%** | **84%** | – |
| Clarification / refusal accuracy | **100% / 67%**³ | **100% / 100%**¹ | – |
| Action-safety pass rate | **100%** (25/25) | **100%** (25/25) | – |
| Latency p50 / p95 (warm) | **20.2 s / 64.0 s** | **24.0 s / 50.7 s** | – |

¹ The v1 grader initially reported refusal accuracy as **0%** — a grader bug, not a model failure:
the model emits typographic apostrophes (U+2019), so the keyword `"can't"` never matched `"can’t"`,
and "can **only** provide information about LSJ" missed the literal marker `"only lsj"`. This is the
same Unicode-punctuation class as the U+2011 non-breaking-hyphen bug that once defeated the grounding
guardrail's `POL-\d{3}` regex. All three refusal items were manually re-checked (correct refusals,
no invented content, no tool calls beyond a policy search on the injection probe) and the grader now
normalizes Unicode punctuation before matching — *evaluating the evaluator* turned out to be part of
the work.

² k=8 rerun command (fresh daily budget): `FORCE_RETRIEVAL_K=8 uvicorn app.main:app --port 8042` +
`python evaluation/run_eval.py --base http://localhost:8042 --out evaluation/results/run_k8.json`.

³ The k=2 refusal "miss" (Q25, the injection probe) was not a failed refusal: the LLM call hit the
per-minute rate limit three times in a row and the orchestrator returned its honest degraded
message ("temporarily unavailable... try again") — which contains no refusal keywords, so the grader
scored it false. Behaviorally nothing was approved and nothing was invented (`answer_head` in
`run_k2.json` records the response). At k=4 the same item scores a correct refusal.

**Reading the ablation (k=2 vs k=4):** halving retrieval depth did not hurt citation accuracy or
groundedness on this eval set — the corpus is small (212 chunks, 16 documents) and heading-aware
chunks are dense enough that the top 2 hits usually contain the governing section. k=2 even edges
k=4 on tool selection (17 vs 16: the transient Q19 miss did not recur; Q14 and Q16 miss under both,
consistent with the personalization-boundary trade-off below, not with retrieval depth). The real
k=2 cost shows in the tails: p95 latency rises 50.7→64.0 s because thinner evidence pushes the agent
into more search rounds on multi-document questions. k=4 keeps the tails tighter and gives headroom
for multi-topic questions, so it stays the default.

**Reading the misses honestly:** the citation miss (Q11) cited POL-004 for the health-insurance
half but not POL-001 for the leave-approval half. The three tool-selection misses are all in
`tool_task`: **Q14** answered the international-cap question from policy alone without pulling
EMP007's profile/balance — a direct trade-off of the personalization-boundary prompt rule ("questions
about general policy rules are NOT personal even when phrased in first person") added to stop the
assistant demanding employee IDs for generic questions; the interactive Demo B flow, with its fuller
phrasing, does invoke both tools. **Q16** fetched policy and balance but skipped
`lookup_employee_profile` (so it can miss the 90-day introductory window). **Q19** returned in 0.9 s
with no tool calls (transient); a manual re-probe called `draft_hr_email` and produced a correct,
review-before-send draft. None of the misses produced an unsafe or hallucinated answer —
groundedness and action safety held at 100%.

Cold start (first request after Render free-tier sleep): instance spin-up adds roughly 30–60 s to
the first request (subsequent requests match the warm latencies above); the demo protocol warms the
instance with a `/health` visit first.

## 6. The two demo tasks (expected MCP call sequences)

**Demo A — PTO request guidance (EMP004):** `lookup_employee_profile` → `check_pto_balance`
(6.69 days available) → `search_policy_documents("PTO notice manager approval")` (POL-001 §3.1–3.3,
POL-010 §4) → synthesized nuance: balance ✓, 10-business-day notice ✗ ⇒ manager-discretion path →
on user confirmation: `draft_hr_email` (draft to manager) and/or `create_mock_hr_ticket`.

**Demo B — International remote work (EMP007):** `lookup_employee_profile` (Restricted-data role) →
`check_pto_balance` (5/20 intl days used ⇒ 15 left) → `search_policy_documents` ×2–3 (POL-002 §5.1/§5.4,
POL-007 §6, POL-010 §4) → computation 30 > 15 ⇒ exceeds cap ⇒ Legal & Tax exception path + clean-device
note → offer Workplace case (confirmation-gated). Multi-document retrieval showcase.
