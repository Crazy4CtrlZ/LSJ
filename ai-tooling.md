# AI Tooling Usage (rubric-required disclosure)

We used **Claude (Anthropic)** as the primary AI engineering assistant throughout, alongside our own
review and testing. In broad terms:

- **Preparation:** Claude drafted the synthetic 16-document policy corpus (4 formats) and the mock
  datasets from our specifications, cross-checked internal consistency (accrual math, cross-references),
  and generated the project plan, tool-schema contract, dashboard, and White Paper documentation.
- **Code:** Claude generated the initial implementation of all three workstreams (RAG pipeline, MCP
  server + agent orchestrator, FastAPI app + tests + CI) against our frozen MCP tool contract v1.0.
  The team reviewed per-lane, ran the test suite, and iterated.
- **What worked well:** contract-first prompting (freezing tool schemas before code) kept generated
  modules compatible; asking for tests alongside code caught envelope mismatches early; using Claude
  to enforce the rubric as a checklist prevented scope gaps.
- **What worked less well:** LLM-dependent behavior (tool-call phrasing, refusals) still needed human
  prompt tuning against the live model; generated parsing code needed adjustments for real PDF text
  extraction quirks; we had to watch for Python package shadowing (renamed `mcp/` → `mcp_server/`).

We remain responsible for correctness, security, and academic integrity of the submitted work.
