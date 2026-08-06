# Mock Structured Data — LSJ, Inc. (Synthetic)

Small JSON datasets backing the MCP tools (`lookup_employee_profile`, `check_pto_balance`, `lookup_benefits_status`, `create_mock_hr_ticket`). All records are clearly synthetic — fictional company, fictional people, no real personal information (rubric requirement). All balances are stated as of **2026-08-04** and are arithmetically consistent with the policy corpus (accrual tiers from POL-001 §2.1, 7 completed accrual months in 2026).

| File | Contents |
|---|---|
| employees.json | 12 profiles EMP001–EMP012: role, department, manager_id chain, office, employment type, exempt status, work arrangement, hire date |
| pto_balances.json | Accrual rate, accrued/used/pending/available days, sick days, floating holidays, international remote-work days used (rolling 12 mo) |
| benefits.json | Eligibility tier, medical plan, dental/vision, HSA seed, 401(k) enrollment and match status, dependents |
| tickets.json | HR case store with 3 closed historical tickets + schema; runtime writes are in-memory only (action safety, POL-015 §6) |
| offices.json | 4 offices with timezone, compensation tier, holiday calendar variant |

## Org chart

```
EMP001 Sarah Chen (VP People Ops, dept head) ── EMP008 Nina Rossi (part-time)
EMP006 Rachel Kim (Dir. Engineering, dept head) ── EMP002 Marcus Webb (Eng Manager) ── EMP004, EMP009, EMP012, EMP003
                                                └─ EMP007 Tom Okafor
EMP010 David Osei (CFO, dept head) ── EMP005 Alicia Gomez (Controller) ── EMP011 Emma Fischer
```

## Edge cases wired in (and the policy each exercises)

- **EMP003 Priya Nair — contractor.** No PTO (POL-001 §8), no benefits (POL-004 §2.2). Tools return explicit ineligibility reasons, not errors.
- **EMP009 Jae-won Lee — probationary new hire** (hired 2026-06-15). PTO accrued but `pto_usable: false` until 2026-09-14 (POL-001 §2.3); 401(k) match starts 2026-09-13 (POL-004 §5).
- **EMP011 Emma Fischer — low balance** (2.0 days available). A 3-day request fails POL-001 §3.3 → agent should offer alternatives (shorter request / unpaid leave §7). Also non-exempt (POL-011 §5 overtime).
- **EMP008 Nina Rossi — part-time.** Prorated accrual (POL-001 §2.1), medical-only benefits (POL-004 §2.1).
- **EMP012 Leo Tanaka — intern.** Ineligible for PTO/benefits; internship ends 2026-08-21.
- **EMP002 Marcus Webb — pending PTO request** (PTO-2026-0187), so "pending" state is queryable.
- **EMP004/EMP007/EMP009 — non-U.S. employees** with local benefits supplements (POL-004 §1) — benefits-triage answers must not assume U.S. plans.

## Demo task hooks

- **Demo A — PTO request guidance (EMP004 Daniel Park):** "Can I take 3 days of PTO next week?" Balance 6.69 days → sufficient (POL-001 §3.3 passes). But a 3-day request requires 10 business days' notice (POL-001 §3.1) — "next week" is short notice → manager-discretion path + manager approval (POL-001 §3.2, manager EMP002). Agent may draft the manager message / mock ticket on confirmation.
- **Demo B — International remote work (EMP007 Tom Okafor):** "Can I work from Portugal for six weeks?" Six weeks ≈ 30 business days; only 15 of 20 rolling-12-month days remain (5 already used — see TCK-1003) → exceeds POL-002 §5.1 → §5.4 Legal & Tax exception review; security conditions POL-007 §6 apply (`handles_restricted_data: true` → clean-device program §6.3).
- **Failure demos:** unknown ID (e.g. EMP999) → graceful "not found" + clarification; EMP003 benefits question → grounded ineligibility answer with POL-004 §2.2 citation.

## Integrity rules the MCP layer should preserve

1. `available_days = accrued_ytd − used_ytd − pending_days` (POL-001 §3.3: never negative).
2. Every `manager_id` refers to an existing employee; department heads have `manager_id: null`.
3. `create_mock_hr_ticket` increments `next_ticket_id` in memory only — the JSON file on disk is never mutated at runtime.
4. Sensitive ("Conduct — Sensitive") tickets must be routed per POL-015 §5 — automation acknowledges and escalates only.
