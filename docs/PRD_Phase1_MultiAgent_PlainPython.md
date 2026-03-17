# PRD: FQHC Copilot Phase 1 — Multi-Agent Architecture (Plain Python)

**Version:** 1.0
**Author:** Anand Vallamsetla
**Date:** 2026-03-17
**Status:** Draft
**GitHub:** github.com/thewhyman/medicaid-fqhc-copilot

---

## Problem Statement

The current FQHC Copilot is a monolithic single-agent system where eligibility determination, memory management, guardrails, and evaluation all live in one ReAct loop inside `agent.py`. This makes it difficult to test eval dimensions independently, debug multi-step failures, or extend the system with new capabilities (voice, RAG, additional agents). Caseworkers need a more reliable, auditable system where each responsibility is isolated and independently testable.

The monolith also limits the project's value as a portfolio piece — multi-agent architecture is the industry direction (LangGraph, CrewAI, AutoGen all exist because of this need), and demonstrating the ability to build one from scratch before adopting a framework shows engineering judgment.

---

## Goals

1. **Decompose the monolith into 6 independent agents** with clear single responsibilities, without breaking any existing eval tests
2. **Make each eval dimension independently runnable** — correctness, efficiency, and quality eval agents can be triggered separately
3. **Reduce debugging time** by isolating failures to specific agents rather than tracing through a single ReAct loop
4. **Maintain 100% backward compatibility** — existing API endpoints, eval suite, and deployment pipeline work unchanged
5. **Create a reusable multi-agent orchestration pattern** in plain Python that others can learn from (no framework dependency)

---

## Non-Goals

1. **Voice interface** — deferred to Phase 2. We need the multi-agent foundation stable before adding a new interface layer.
2. **LangGraph or any framework adoption** — Phase 1 is deliberately plain Python. We build the orchestration ourselves to understand what frameworks abstract away.
3. **RAG for dynamic policy updates** — FPL data remains embedded. RAG adds retrieval noise and complexity we don't need for static data.
4. **Horizontal scaling or microservice architecture** — all agents run in-process. Premature distribution adds network overhead with no benefit for a PoC.
5. **HITL override dashboard** — deferred to Phase 2. Phase 1 establishes the agent boundaries; Phase 2 adds the UI.

---

## User Stories

### Caseworker

- As a caseworker, I want eligibility determinations to be at least as accurate as the current system so that the multi-agent refactor doesn't introduce regressions.
- As a caseworker, I want determinations corrected in real-time when the system detects an error so that I never relay incorrect eligibility information to a patient.
- As a caseworker, I want patient context from previous sessions automatically included so that I don't have to repeat information.

### Developer (Self / Open Source Contributors)

- As a developer, I want each agent to be a self-contained Python module so that I can understand, test, and modify one agent without reading the entire codebase.
- As a developer, I want to run correctness evals without triggering efficiency or quality evals so that I can iterate faster on math-related changes.
- As a developer, I want a clear orchestration layer (router) that shows the full agent flow in one file so that I can understand the system architecture in under 5 minutes.
- As a developer learning multi-agent patterns, I want this PRD and the code to serve as a reference implementation so that I can apply the same pattern to my own projects.

### Evaluator (CI/CD Pipeline)

- As the CI pipeline, I want deterministic evals to run on every push and complete in under 30 seconds so that code regressions are caught immediately.
- As the weekly eval scheduler, I want full agent evals to run end-to-end and auto-create GitHub issues on failure so that model drift is detected without manual monitoring.

---

## Requirements

### Must-Have (P0)

**R1: Agent Decomposition**
Extract the monolith into 6 agents, each in its own Python module:

| Agent | Module | Responsibility |
|---|---|---|
| Eligibility Agent | `agents/eligibility.py` | ReAct loop, LLM calls, determination |
| Memory Agent | `agents/memory.py` | Mem0 SDK search/save, patient-{id} scoping |
| Knowledge Agent | `agents/knowledge.py` | FPL tables, state rules, expansion status |
| Correctness Eval | `agents/eval_correctness.py` | Deterministic engine comparison |
| Efficiency Eval | `agents/eval_efficiency.py` | API call counting, banned tool detection |
| Quality Eval | `agents/eval_quality.py` | Keyword matching, reasoning verification |

Acceptance criteria:
- [ ] Each agent is importable and testable independently
- [ ] No agent imports from another agent's internals (communicate through the router)
- [ ] All existing eval tests pass without modification
- [ ] `eligibility.py` (deterministic engine) remains unchanged — it is NOT an agent, it is ground truth

**R2: Router / Orchestrator**
Create `router.py` that orchestrates the full determination flow:

```
1. Receive request (patient_id, query, stream flag)
2. Call Memory Agent (search patient-{id})
3. Call Knowledge Agent (get FPL + state rules)
4. Inject memory + knowledge into Eligibility Agent system prompt
5. Run Eligibility Agent (ReAct loop, ≤10 iterations)
6. Run Deterministic Engine (parallel ground truth)
7. Run 3 Eval Agents (parallel):
   - Correctness: compare determination vs engine
   - Efficiency: count API calls, check banned tools
   - Quality: verify keywords, reasoning, citations
8. Aggregate verdict:
   - Correctness fail → override response with engine answer
   - Quality fail → append correction
   - Efficiency fail → log warning (don't block response)
9. Call Memory Agent (save determination)
10. Return response
```

Acceptance criteria:
- [ ] Router handles both streaming and non-streaming paths
- [ ] Router enforces streaming parity (same guardrails on both paths)
- [ ] Full flow completes in ≤3 seconds for text requests
- [ ] Router is the ONLY file that knows about all agents — agents don't know about each other

**R3: Shared Configuration**
Consolidate all agent configuration into `config.py`:

- Model version (gpt-4o-mini-2024-07-18)
- MAX_AGENT_ITERATIONS (10)
- Tool result truncation limit (10,000 chars)
- Mem0 configuration
- MCP server configurations
- Eval thresholds (max API calls: 4, banned tools list)

Acceptance criteria:
- [ ] No hardcoded constants in any agent module
- [ ] Changing a config value in one place propagates to all agents
- [ ] Config values are testable (eval tests can override thresholds)

**R4: Eval Independence**
Each eval agent can be run independently via CLI:

```bash
python -m agents.eval_correctness --patient-id patient-10
python -m agents.eval_efficiency --patient-id patient-10
python -m agents.eval_quality --patient-id patient-10
python -m agents.eval_all  # runs all three
```

Acceptance criteria:
- [ ] Each eval agent produces a structured JSON result: `{passed: bool, details: str, dimension: str}`
- [ ] Eval agents can run without the Eligibility Agent (accept a pre-computed determination as input)
- [ ] GitHub Actions workflow updated to run evals independently
- [ ] Weekly schedule runs all three and aggregates results into a single GitHub issue on failure

**R5: Backward Compatibility**
Existing API endpoints remain unchanged:

- `POST /determine` — text determination (same request/response format)
- `POST /determine/stream` — streaming determination (same SSE format)
- All 16 seed patients produce identical results before and after refactor

Acceptance criteria:
- [ ] A/B comparison script that runs all 16 patients on old and new code, diffs results
- [ ] Zero regressions on correctness, efficiency, and quality evals
- [ ] Render deployment pipeline unchanged (render.yaml still gates on evals)

### Nice-to-Have (P1)

**R6: Agent Metrics**
Each agent emits timing and usage metrics:

- Eligibility Agent: LLM call count, total tokens, iteration count
- Memory Agent: search latency, save latency, memories found
- Eval Agents: pass/fail, dimension, execution time

Acceptance criteria:
- [ ] Metrics logged as structured JSON to stdout
- [ ] Metrics visible in Render logs
- [ ] Total determination latency broken down by agent

**R7: Agent-Level Error Handling**
Each agent handles its own errors gracefully:

- Memory Agent failure → proceed without memory (degrade, don't crash)
- Knowledge Agent failure → use embedded FPL data (fallback)
- Eval Agent failure → log error, don't block response
- Eligibility Agent failure → return error to user with patient-friendly message

Acceptance criteria:
- [ ] No single agent failure crashes the entire system
- [ ] Degradation is logged with agent name and error details
- [ ] Caseworker sees a helpful message, not a stack trace

### Future Considerations (P2)

**R8: Voice Interface Agent** — WebSocket endpoint with STT/TTS (Phase 2)
**R9: LangGraph Migration** — Refactor router.py to LangGraph state graph (Phase 2)
**R10: HITL Override Dashboard** — Web UI for caseworker corrections (Phase 2)
**R11: OpenTelemetry Tracing** — Distributed tracing across agents (Phase 2)
**R12: RAG Knowledge Agent** — Dynamic policy retrieval for 50-state updates (future)

---

## Success Metrics

### Leading Indicators (within 1 week of completing refactor)

| Metric | Target | Measurement |
|---|---|---|
| All 16 seed patients produce identical results | 100% | A/B comparison script |
| Deterministic evals pass on every push | 100% | GitHub Actions |
| Individual eval agent CLI works independently | All 3 runnable | Manual test |
| Full determination latency | ≤3s (no regression) | Render logs |
| Code modularity: no cross-agent imports | 0 violations | grep check in CI |

### Lagging Indicators (within 1 month)

| Metric | Target | Measurement |
|---|---|---|
| Weekly full agent evals pass rate | ≥95% | GitHub Actions weekly schedule |
| Time to diagnose a failure | <5 min (down from ~20 min in monolith) | Developer experience |
| Open source engagement (stars, forks, issues) | Any increase | GitHub metrics |

---

## Technical Architecture

### Directory Structure (after refactor)

```
medicaid-fqhc-copilot/
├── agents/
│   ├── __init__.py
│   ├── eligibility.py       # Primary ReAct agent (LLM calls)
│   ├── memory.py             # Mem0 SDK search/save
│   ├── knowledge.py          # FPL tables, state rules
│   ├── eval_correctness.py   # Deterministic comparison
│   ├── eval_efficiency.py    # API call counting
│   └── eval_quality.py       # Keyword/reasoning check
├── router.py                 # Orchestrator (the only file that imports all agents)
├── eligibility.py            # Deterministic engine (UNCHANGED — ground truth)
├── prompts.py                # All prompts (system + QA)
├── config.py                 # All configuration
├── server.py                 # FastAPI endpoints (thin — delegates to router)
├── evals/
│   ├── run_correctness.py
│   ├── run_efficiency.py
│   ├── run_quality.py
│   └── run_all.py
├── tests/
│   ├── test_eligibility_agent.py
│   ├── test_memory_agent.py
│   ├── test_knowledge_agent.py
│   ├── test_eval_agents.py
│   └── test_router.py
├── render.yaml
├── .github/
│   └── workflows/
│       ├── deterministic_evals.yml  # Every push
│       └── full_agent_evals.yml     # Weekly
└── PRD_Phase1.md                     # This document
```

### Agent Communication Pattern

All agents communicate through the router via **function calls** (not HTTP, not message queues). The router is a plain Python function:

```python
async def determine(patient_id: str, query: str, stream: bool) -> DeterminationResult:
    # 1. Gather context
    memory_context = await memory_agent.search(patient_id)
    knowledge_context = knowledge_agent.get_rules(patient_id)

    # 2. Run primary agent
    determination = await eligibility_agent.determine(
        query=query,
        memory=memory_context,
        knowledge=knowledge_context,
        stream=stream
    )

    # 3. Ground truth
    engine_result = eligibility_engine.compute(patient_id)

    # 4. Evaluate (parallel)
    correctness = eval_correctness.check(determination, engine_result)
    efficiency = eval_efficiency.check(determination.metrics)
    quality = eval_quality.check(determination, engine_result)

    # 5. Override if needed
    if not correctness.passed:
        determination = override_with_engine(determination, engine_result)
    if not quality.passed:
        determination = append_correction(determination, quality.details)

    # 6. Save memory
    await memory_agent.save(patient_id, determination)

    return determination
```

---

## Open Questions

| Question | Owner | Blocking? |
|---|---|---|
| Should eval agents run sequentially or in parallel (asyncio.gather)? | Engineering | No — start sequential, optimize later |
| Should Memory Agent failure block the determination or degrade gracefully? | Engineering | Yes — recommend degrade |
| Should we add a `--dry-run` flag to router for testing without LLM calls? | Engineering | No — nice to have |
| How to handle patient records that span multiple sessions (memory pagination)? | Engineering | No — defer to Phase 2 |

---

## Implementation Plan

| Week | Deliverable | Validation |
|---|---|---|
| Day 1-2 | Create `agents/` directory, extract Memory Agent and Knowledge Agent from agent.py | Existing evals pass |
| Day 3-4 | Extract Eligibility Agent, create router.py | Full flow works via router |
| Day 5-6 | Extract 3 Eval Agents, add CLI runners | Each eval runs independently |
| Day 7 | Update GitHub Actions, A/B comparison, update render.yaml | CI passes, deploy succeeds |
| Day 8 | Metrics logging, error handling, documentation | P1 requirements met |

---

## Design Principles

1. **The router is the brain.** It is the ONLY module that knows about all agents. Agents are unaware of each other.
2. **The deterministic engine is sacred.** It is not an agent. It is ground truth. It never changes in this refactor.
3. **Eval agents are first-class citizens.** They are not afterthoughts bolted onto the system — they are peers of the Eligibility Agent.
4. **No framework.** This phase deliberately avoids LangGraph, CrewAI, or any orchestration framework. The goal is to understand what a framework abstracts before adopting one.
5. **Backward compatibility is non-negotiable.** If a single seed patient produces a different result, the refactor is not done.
