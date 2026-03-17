# PRD: FQHC Copilot Phase 0 — Monolith (Current State)

**Version:** 1.0
**Author:** Anand Vallamsetla
**Date:** 2026-03-17
**Status:** Shipped (PoC deployed on Render)
**GitHub:** github.com/thewhyman/medicaid-fqhc-copilot
**Commits:** 29 | **Deployments:** 31

---

## Problem Statement

Federally Qualified Health Centers (FQHCs) serve underinsured and uninsured patients. Caseworkers at these centers determine Medicaid eligibility manually — cross-referencing a patient's income, household size, age, citizenship status, pregnancy status, and state of residence against Federal Poverty Level (FPL) tables and 50-state Medicaid expansion rules. This process is slow, error-prone, and high-stakes: an incorrect determination can mean a patient is wrongfully denied benefits or a center absorbs unreimbursed care costs.

No affordable, reliable AI tool exists for FQHC caseworkers to assist with Medicaid eligibility determinations. Existing LLM-based systems (ChatGPT, Copilot) fail silently on boundary cases — particularly arithmetic involving income thresholds — without any mechanism to detect or correct errors.

---

## Goals

1. **Build a PoC Medicaid eligibility agent** that assists FQHC caseworkers with real-time determinations for all 50 states + DC + territories
2. **Achieve 100% correctness on deterministic edge cases** — boundary income, age transitions, non-expansion states, Alaska/Hawaii FPL tables
3. **Demonstrate that LLMs require defense in depth** — prove through architecture that a single LLM call is insufficient for high-stakes determinations
4. **Treat evaluation as infrastructure, not afterthought** — evals gate deployment; if correctness fails, the code doesn't ship
5. **Ship a deployed, publicly accessible PoC** with real PostgreSQL, real MCP tool integration, and real eval pipeline

---

## Non-Goals

1. **Production deployment to real FQHCs** — this is a PoC demonstrating architectural patterns, not a certified medical tool. No real patient data.
2. **HIPAA certification** — we design for HIPAA awareness (per-patient memory scoping, no cross-patient leakage) but do not pursue formal certification.
3. **Multi-agent architecture** — Phase 0 is deliberately a monolith. All logic lives in a single ReAct loop. Decomposition is Phase 1.
4. **Voice interface** — text-only. Voice is Phase 2.
5. **Dynamic policy updates** — FPL tables and Medicaid rules are embedded statically. Real-time policy retrieval (RAG) is a future consideration.
6. **Multi-model support** — OpenAI only (gpt-4o-mini pinned). No Claude, Gemini, or open-source model support.

---

## User Stories

### Caseworker

- As a caseworker, I want to type a patient's details (name, age, income, household size, state, citizenship, pregnancy status) and receive an eligibility determination so that I can quickly advise the patient.
- As a caseworker, I want the determination to include the reasoning (which FPL threshold, which category, expansion state or not) so that I can explain the decision to the patient.
- As a caseworker, I want the system to remember a patient from a previous session so that I don't have to re-enter their details if I come back later.
- As a caseworker, I want the system to stream its response in real-time so that I can start reading the determination before the full response is generated.

### Developer / Portfolio Reviewer

- As a developer reviewing this repo, I want to understand the architectural decisions and why they were made so that I can learn from the patterns.
- As an interviewer at Anthropic or Scale AI, I want to see eval-gated deployment, defense in depth, and edge case design so that I can assess the candidate's engineering judgment.
- As an open-source contributor, I want to run the eval suite locally so that I can verify changes don't introduce regressions.

---

## Requirements

### Must-Have (P0)

**R1: ReAct Agent Loop**
An autonomous agent that uses the ReAct pattern (Reason → Act → Observe → Repeat) to determine Medicaid eligibility.

Acceptance criteria:
- [ ] Agent receives a natural language query about a patient
- [ ] Agent reasons about the patient's eligibility factors step by step
- [ ] Agent calls MCP tools as needed (database queries, file reads)
- [ ] Agent produces a final determination: ELIGIBLE or NOT ELIGIBLE
- [ ] Agent provides natural language explanation with the determination
- [ ] Agent completes in ≤10 iterations (MAX_AGENT_ITERATIONS guardrail)
- [ ] Agent works in both streaming and non-streaming modes with full feature parity

**R2: Deterministic Eligibility Engine**
A pure Python function that computes the correct eligibility determination independently of the LLM.

Acceptance criteria:
- [ ] Takes patient record as input: income, household_size, age, state, citizenship, pregnancy_status
- [ ] Looks up correct FPL threshold for household size (standard table + Alaska + Hawaii)
- [ ] Determines Medicaid expansion status for the patient's state
- [ ] Applies correct threshold percentage (138% expansion, 100% non-expansion, higher for pregnant/children)
- [ ] Returns: eligible (bool), category, threshold_used, fpl_amount, reasoning
- [ ] Zero LLM involvement — pure arithmetic and lookup tables
- [ ] Handles all 16 seed patient edge cases correctly

**R3: Five-Layer Defense Architecture**

| Layer | What | Catches |
|---|---|---|
| 1. System prompt | FPL tables + rules embedded in context | Basic reasoning errors |
| 2. Deterministic engine | Python function as internal verification | All math errors |
| 3. Structured output | JSON schema for tool calls | Format/parsing errors |
| 4. Post-hoc guardrail | Compare LLM output vs engine in real-time | Hallucinated determinations |
| 5. QA agent | Second LLM reviewing first with ground truth | Reasoning errors engine can't catch |

Acceptance criteria:
- [ ] Each layer operates independently — removing one layer doesn't break others
- [ ] Post-hoc guardrail (Layer 4) catches the $1 boundary case: Patient #10, Kevin Park ($21,598 income, $21,597 threshold)
- [ ] QA agent (Layer 5) receives ground truth from deterministic engine — it's a reasoning auditor, not a coin flip
- [ ] QA agent checks 5 things: category, FPL table, math, citizenship, expansion status
- [ ] All 5 layers apply to both streaming and non-streaming paths (streaming parity)

**R4: MCP Tool Integration**
Three MCP servers connected through a manager with automatic reconnection:

| MCP Server | Purpose |
|---|---|
| PostgreSQL MCP | Read/write patient records |
| Filesystem MCP | Read configuration and reference files |
| Fetch MCP | Available in config but BANNED by evals — embedded data preferred |

Acceptance criteria:
- [ ] Agent calls `read_query` without knowing it's talking to Postgres (tool isolation)
- [ ] MCP manager handles reconnection if a server drops
- [ ] Tool results truncated at 10,000 characters and stripped of control characters
- [ ] Fetch MCP present in configuration but eval suite fails if agent calls it (enforced static data)

**R5: Per-Patient Memory (Mem0 SDK)**
Persistent memory scoped per patient using Mem0 SDK (not MCP):

Acceptance criteria:
- [ ] Memory keyed by `patient-{id}` — no cross-patient leakage
- [ ] Memory search injected into system prompt BEFORE LLM call (not as a tool)
- [ ] Memory save happens AFTER final response (not during agent loop)
- [ ] Reduces API calls from 5-6 (MCP approach) to 3 (SDK approach)
- [ ] HIPAA-aware design: Patient 1's determination cannot appear in Patient 5's context

**R6: Model Version Pinning**
Pin to `gpt-4o-mini-2024-07-18`, not the `gpt-4o-mini` alias.

Acceptance criteria:
- [ ] Model string hardcoded in config.py as a constant
- [ ] No use of model aliases anywhere in the codebase
- [ ] Changing the model version requires a deliberate code change + regression eval run

**R7: Three-Dimensional Eval Suite**
Every determination evaluated on three independent dimensions:

| Dimension | Method | Threshold |
|---|---|---|
| Correctness | Deterministic engine comparison | Must match exactly |
| Efficiency | API call count + banned tool check | ≤4 API calls, no Fetch |
| Quality | Keyword matching with alternatives | Must mention category, state, threshold |

Acceptance criteria:
- [ ] Correctness eval runs without any API calls (pure Python)
- [ ] Efficiency eval counts actual API calls during determination
- [ ] Quality eval checks for keywords with alternatives (e.g., "pregnant" OR "pregnancy")
- [ ] All three dimensions reported independently in eval results
- [ ] A determination can pass correctness but fail quality (or vice versa)

**R8: Eval-Gated Deployment**
Deterministic evals run in the Render build pipeline. Deployment is blocked if correctness tests fail.

Acceptance criteria:
- [ ] render.yaml includes eval step before deployment
- [ ] Correctness failure = deployment blocked (hard gate)
- [ ] Single combined GitHub Actions workflow (`regression-evals.yml`) runs deterministic evals on every push/PR and full agent evals on a daily schedule
- [ ] Agent eval failures auto-create GitHub issues with `eval-regression` label
- [ ] Workflow supports manual trigger via `workflow_dispatch`

**R9: 16 Seed Patients (8 Standard + 8 Edge Cases)**
Pre-loaded patient records covering the full eligibility decision space:

Standard patients (1-8): Clear eligible/not eligible cases across different states, household sizes, ages.

Edge case patients (9-16):
- [ ] Income exactly at 138% FPL threshold (boundary)
- [ ] Income $1 over threshold (just above cutoff)
- [ ] Non-US citizen (citizenship disqualification)
- [ ] Age 18 (child→adult category boundary)
- [ ] Age 65 in non-expansion state (adult→elderly boundary)
- [ ] Pregnant in non-expansion state (higher threshold applies)
- [ ] Alaska (separate FPL table)
- [ ] Hawaii, household size 8 (FPL table maximum boundary)

Acceptance criteria:
- [ ] All 16 patients seeded in PostgreSQL
- [ ] Deterministic engine returns correct result for all 16
- [ ] Full agent eval passes for all 16
- [ ] Edge cases specifically target known LLM failure modes

**R10: Streaming Parity**
Full feature parity between streaming and non-streaming paths.

Acceptance criteria:
- [ ] Same guardrails on both paths
- [ ] Same memory injection on both paths
- [ ] Same tool result sanitization on both paths
- [ ] Same metrics collection on both paths
- [ ] Same MAX_AGENT_ITERATIONS on both paths

### Nice-to-Have (P1)

**R11: Code Modularity**
Strict separation of concerns across files:

| File | Responsibility |
|---|---|
| `eligibility.py` | Single source of truth for eligibility math |
| `prompts.py` | All prompts (system + QA) |
| `config.py` | All constants and configuration |
| `mcp_manager.py` | Multi-server MCP connection, tool routing, auto-reconnection |
| `agent.py` | Agent logic, Mem0, guardrails, metrics |
| `server.py` | FastAPI endpoints |

Acceptance criteria:
- [ ] No constants defined in multiple files
- [ ] No copy-pasted logic between streaming and non-streaming methods
- [ ] Function-level imports eliminated — all imports at top of file

**R12: Web Frontend**
Vanilla HTML/CSS/JS frontend for caseworker interaction:

Acceptance criteria:
- [ ] Text input for patient queries
- [ ] Streaming response display
- [ ] Patient selection dropdown
- [ ] Mobile-responsive (caseworkers may use tablets)

### Future Considerations (P2)

**R13: Multi-agent architecture** — decompose monolith into independent agents (Phase 1)
**R14: LangGraph migration** — replace hand-written orchestration with framework (Phase 2)
**R15: Voice interface** — STT + TTS for hands-free caseworker interaction (Phase 2)
**R16: HITL override dashboard** — caseworker correction and audit trail (Phase 2)

---

## Success Metrics

### Leading Indicators (at time of initial deployment)

| Metric | Target | Result |
|---|---|---|
| Correctness on all 16 seed patients | 100% | ✅ Achieved |
| Eval-gated deployment blocks on failure | Working | ✅ Achieved |
| Post-hoc guardrail catches $1 boundary case | Catches Patient #10 | ✅ Achieved (Kevin Park) |
| API calls per determination | ≤4 | ✅ Achieved (3 avg) |
| Deployment count | Continuous | ✅ 31 deployments |

### Lagging Indicators (1 month post-deployment)

| Metric | Target | Result |
|---|---|---|
| LinkedIn article published | Yes | ✅ Published 2026-03-17 |
| Article impressions | >100 | ✅ 277 in first hour |
| Conference talk referencing this work | Yes | ✅ HealthTech Summit 2026 (HITL philosophy) |
| Interview readiness | Can explain all 10 decisions | ✅ Documented in Career OS |

---

## Technical Architecture

### System Diagram

```
┌──────────────┐     HTTP      ┌──────────────┐
│  Caseworker   │ ◄──────────► │  FastAPI      │
│  (Browser)    │   (SSE for   │  server.py    │
│  HTML/CSS/JS  │   streaming) │              │
└──────────────┘              └──────┬───────┘
                                      │
                               ┌──────▼───────┐
                               │   agent.py    │
                               │   ReAct Loop  │
                               │   (monolith)  │
                               │               │
                               │ ┌───────────┐ │
                               │ │ Mem0 SDK   │ │
                               │ │ (pre/post) │ │
                               │ └───────────┘ │
                               │               │
                               │ ┌───────────┐ │
                               │ │ Guardrail  │ │
                               │ │ (Layer 4)  │ │
                               │ └───────────┘ │
                               │               │
                               │ ┌───────────┐ │
                               │ │ QA Agent   │ │
                               │ │ (Layer 5)  │ │
                               │ └───────────┘ │
                               └──────┬───────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
             ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
             │ PostgreSQL   │  │ Filesystem   │  │ Fetch MCP   │
             │ MCP Server   │  │ MCP Server   │  │ (BANNED)    │
             └─────────────┘  └─────────────┘  └─────────────┘
                    │
             ┌──────▼──────┐
             │ PostgreSQL   │
             │ (Render      │
             │  managed)    │
             └─────────────┘
```

### Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.13+ |
| LLM | OpenAI gpt-4o-mini-2024-07-18 (pinned) |
| Framework | FastAPI |
| Database | PostgreSQL (Render managed) |
| Memory | Mem0 SDK (not MCP) |
| Tool Protocol | MCP (stdio transport) |
| Deployment | Render (render.yaml) |
| CI/CD | GitHub Actions |
| Frontend | Vanilla HTML/CSS/JS |
| Eval runner | npm scripts + Python |

### File Structure

```
medicaid-fqhc-copilot/
├── agent.py              # ReAct loop, Mem0, guardrails, QA agent (monolith)
├── eligibility.py        # Deterministic engine (ground truth)
├── prompts.py            # System prompt + QA prompt
├── config.py             # Constants and configuration
├── mcp_manager.py        # Multi-server MCP connection & tool routing
├── server.py             # FastAPI endpoints
├── static/               # Frontend (HTML/CSS/JS)
├── evals/                # Eval scripts
├── reports/              # Saved eligibility determination reports (markdown)
├── seed_db.py            # Database schema + 16 seed patients (Python)
├── render.yaml           # Deployment + eval gate
├── package.json          # npm scripts (eval, start, build) + MCP server dependencies
├── .github/
│   └── workflows/
│       └── regression-evals.yml  # Combined: deterministic on push + agent evals on schedule
├── requirements.txt
└── README.md
```

---

## Open Questions (Resolved)

| Question | Resolution |
|---|---|
| Mem0 as MCP tool or SDK? | SDK — reduced API calls from 5-6 to 3. Don't expose to model what doesn't need model reasoning. |
| Fetch FPL data live or embed? | Embed — data is static. Fetch banned by evals. |
| Single eval dimension or multiple? | Three dimensions (correctness, efficiency, quality). Correctness-only is insufficient. |
| Model alias or pinned version? | Pinned. Aliases silently resolve to new snapshots. |
| Streaming: separate implementation or shared? | Shared methods — streaming parity enforced as design constraint. |
| Evals in CI or deployment pipeline? | Both. Deterministic evals on every push (CI). Full agent evals weekly. Deployment gated on correctness. |

---

## Key Architectural Decisions (10 Total)

Documented in detail in the LinkedIn article "Building a Reliable AI Agent: 10 Architectural Decisions and What I Learned" (published 2026-03-17):

1. Deterministic engine over LLM math
2. Model version pinning
3. Five-layer defense architecture
4. Guardrail caught a real bug (Patient #10)
5. QA agent with ground truth advantage
6. Three-dimensional eval design
7. Tiered eval strategy (push vs. weekly)
8. Edge case test design (16 patients)
9. Tool isolation through MCP
10. Modularity from day one

---

## Design Principles

1. **LLMs are unreliable calculators.** Use code for what code does better. Use the LLM for what it's genuinely good at — natural language reasoning.
2. **Defense in depth is an AI architecture principle.** No single layer is sufficient. Each layer has a different failure mode.
3. **Evaluation is infrastructure.** Evals gate deployment. If correctness fails, the code doesn't ship. Evals are not a test suite — they are a deployment pipeline.
4. **Build guardrails before you need them.** The $1 boundary case validated the entire guardrail architecture.
5. **Human oversight isn't optional — it's architected into every decision point.** (HealthTech Summit 2026 thesis, expressed in code through the guardrail and QA agent layers.)
6. **The hard part of AI engineering isn't the model — it's everything around it.** The OpenAI API call is 10 lines of code. The other 95% is where the engineering judgment lives.
