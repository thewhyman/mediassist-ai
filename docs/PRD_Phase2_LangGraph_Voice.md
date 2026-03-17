# PRD: FQHC Copilot Phase 2 — LangGraph Migration + Voice Interface

**Version:** 1.0
**Author:** Anand Vallamsetla
**Date:** 2026-03-17
**Status:** Draft
**Prerequisite:** Phase 1 complete (multi-agent plain Python)
**GitHub:** github.com/thewhyman/medicaid-fqhc-copilot

---

## Problem Statement

Phase 1 established a multi-agent architecture in plain Python with a hand-written router. While this demonstrates engineering fundamentals, it has limitations: the router lacks built-in state management for multi-turn conversations, checkpointing for long-running workflows, and native human-in-the-loop interruption. Additionally, caseworkers in FQHCs often have their hands full (literally — examining patients, filling out forms) and need a voice-first interface to query eligibility without typing.

Phase 2 solves both: migrate the orchestration to LangGraph for production-grade agent management, and add a voice interface (STT → Agent → TTS) so caseworkers can speak naturally and hear determinations read back.

The dual-phase approach is also the portfolio story: "I built it from scratch first to understand what frameworks abstract, then migrated to LangGraph to show I can evaluate and adopt the right tool."

---

## Goals

1. **Migrate router.py to a LangGraph StateGraph** with typed state, conditional edges, and built-in checkpointing — without changing any agent internals
2. **Add voice interface** (STT + TTS) as a new input/output channel that uses the same agent pipeline
3. **Enable human-in-the-loop override** where caseworkers can interrupt and correct a determination mid-flow
4. **Add observability** via LangSmith tracing so every agent call, tool use, and eval check is visible in a single trace
5. **Demonstrate framework evaluation judgment** by documenting what LangGraph gives you vs. what plain Python gave you — with concrete metrics

---

## Non-Goals

1. **Rewrite agent internals** — agents remain plain Python modules. Only the orchestration layer changes. If an agent worked in Phase 1, it works in Phase 2.
2. **Multi-user concurrent sessions** — voice is 1:1 caseworker-to-agent. No multi-party or conference calling.
3. **Real-time translation / multilingual** — English only for v1. Multilingual is a future consideration.
4. **Fine-tuning the LLM** — we use gpt-4o-mini-2024-07-18 (pinned). No custom model training.
5. **Production HIPAA certification** — this remains a PoC. We design for HIPAA awareness (per-patient scoping, audit trails) but do not pursue formal certification.

---

## User Stories

### Caseworker (Voice)

- As a caseworker examining a patient, I want to ask "Is Maria Gonzalez eligible for Medicaid?" out loud so that I don't have to stop what I'm doing and type.
- As a caseworker, I want to hear the determination spoken back to me with the key details (eligible/not eligible, reason, threshold) so that I can immediately relay it to the patient.
- As a caseworker, I want to interrupt the agent mid-response and say "Wait, she's actually pregnant" so that the determination updates in real-time with the corrected information.
- As a caseworker, I want voice conversations to remember previous patients I've asked about so that I can say "What about her husband?" and the system understands the family context.

### Caseworker (HITL Override)

- As a caseworker, I want to flag a determination as incorrect so that the system learns from my correction and the audit trail reflects the override.
- As a caseworker, I want to see when the system auto-corrected itself (guardrail triggered) so that I can trust but verify the system's reliability.

### Developer

- As a developer, I want to view a single trace in LangSmith showing the full agent flow (memory search → knowledge lookup → eligibility determination → eval checks → verdict) so that I can diagnose failures in under 2 minutes.
- As a developer, I want the LangGraph migration to be a drop-in replacement for router.py so that all existing evals and API endpoints work without modification.
- As a developer comparing LangGraph vs. plain Python, I want documented metrics (lines of code, latency, debugging time, feature velocity) so that I can make informed framework decisions for future projects.

### Evaluator (CI/CD)

- As the CI pipeline, I want voice integration tests to run weekly alongside agent evals so that STT/TTS regressions are caught automatically.
- As the eval system, I want LangGraph checkpoints to enable eval replay — re-run a specific patient determination from a saved state without re-executing the full flow.

---

## Requirements

### Must-Have (P0)

**R1: LangGraph StateGraph Migration**

Replace `router.py` with a LangGraph StateGraph that preserves the exact same agent flow:

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict

class CopilotState(TypedDict):
    patient_id: str
    query: str
    memory_context: list[dict]
    knowledge_context: dict
    determination: dict
    engine_result: dict
    eval_correctness: dict
    eval_efficiency: dict
    eval_quality: dict
    verdict: str
    response: str
    metrics: dict

graph = StateGraph(CopilotState)

# Nodes (each node calls one agent)
graph.add_node("search_memory", memory_agent.search)
graph.add_node("get_knowledge", knowledge_agent.get_rules)
graph.add_node("determine", eligibility_agent.determine)
graph.add_node("compute_ground_truth", eligibility_engine.compute)
graph.add_node("eval_correctness", eval_correctness.check)
graph.add_node("eval_efficiency", eval_efficiency.check)
graph.add_node("eval_quality", eval_quality.check)
graph.add_node("aggregate_verdict", verdict_aggregator.aggregate)
graph.add_node("save_memory", memory_agent.save)

# Edges
graph.add_edge("search_memory", "get_knowledge")
graph.add_edge("get_knowledge", "determine")
graph.add_edge("determine", "compute_ground_truth")
graph.add_edge("compute_ground_truth", "eval_correctness")
graph.add_edge("eval_correctness", "eval_efficiency")
graph.add_edge("eval_efficiency", "eval_quality")
graph.add_edge("eval_quality", "aggregate_verdict")

# Conditional edge: verdict determines next step
graph.add_conditional_edges(
    "aggregate_verdict",
    route_verdict,  # function that checks pass/fail
    {
        "pass": "save_memory",
        "correctness_fail": "override_with_engine",
        "quality_fail": "append_correction",
    }
)

graph.add_edge("save_memory", END)
graph.set_entry_point("search_memory")

copilot = graph.compile(checkpointer=MemorySaver())
```

Acceptance criteria:
- [ ] All 16 seed patients produce identical results to Phase 1
- [ ] Streaming and non-streaming paths both work through LangGraph
- [ ] Existing FastAPI endpoints (`/determine`, `/determine/stream`) unchanged
- [ ] render.yaml eval gates still block deployment on correctness failure
- [ ] State is fully typed (TypedDict) — no untyped dictionaries flowing between agents

**R2: LangGraph Checkpointing**

Enable per-patient checkpointing so conversations can be resumed:

Acceptance criteria:
- [ ] Checkpoint keyed by patient-{id}
- [ ] Caseworker can ask about a patient, leave, return, and continue with context
- [ ] Checkpoints stored in PostgreSQL (not in-memory)
- [ ] Checkpoint cleanup: auto-expire after 24 hours of inactivity

**R3: Human-in-the-Loop Interruption**

Add an interrupt point after the Eligibility Agent's determination, before eval:

Acceptance criteria:
- [ ] Caseworker can override the determination before evals run
- [ ] Override is logged in the audit trail with caseworker ID and reason
- [ ] If no override within 3 seconds (voice) or 10 seconds (text), auto-proceed to evals
- [ ] Overridden determinations still run through evals (eval the override, not the original)

**R4: Voice Interface**

Add WebSocket endpoint for voice interaction:

| Component | Choice | Fallback |
|---|---|---|
| STT | Whisper API (OpenAI) | Deepgram (if latency >800ms) |
| TTS | OpenAI TTS API (voice: "alloy") | ElevenLabs (if quality insufficient) |
| Transport | WebSocket (binary audio frames) | — |
| Audio format | PCM 16-bit, 16kHz mono (input), opus (output) | — |

Acceptance criteria:
- [ ] Caseworker speaks → text appears in <500ms (STT latency)
- [ ] Full determination spoken back in <5s total (STT + LLM + TTS)
- [ ] Same 5-layer defense architecture applies to voice path
- [ ] Voice sessions are patient-scoped (same Mem0 patient-{id} scoping)
- [ ] Silence detection: if caseworker is silent for 5 seconds, agent prompts "Anything else?"
- [ ] Interruption handling: caseworker can speak while TTS is playing, TTS stops, new query processes

**R5: LangSmith Observability**

Integrate LangSmith tracing for full agent flow visibility:

Acceptance criteria:
- [ ] Every agent call appears as a span in LangSmith
- [ ] Traces show: input state → agent execution → output state for each node
- [ ] Total determination latency broken down by agent
- [ ] Eval pass/fail visible in trace metadata
- [ ] LLM token usage tracked per agent call
- [ ] Traces queryable by patient-{id}

### Nice-to-Have (P1)

**R6: Framework Comparison Document**

Create `docs/FRAMEWORK_COMPARISON.md` documenting:

| Metric | Plain Python (Phase 1) | LangGraph (Phase 2) |
|---|---|---|
| Lines of code (router) | X | Y |
| Avg determination latency | X ms | Y ms |
| Time to diagnose failure | X min | Y min |
| Time to add new agent | X hours | Y hours |
| Dependencies added | 0 | N |
| Checkpointing | Manual | Built-in |
| HITL support | Custom code | Built-in |
| Observability | stdout logs | LangSmith traces |

Acceptance criteria:
- [ ] Honest comparison — include where LangGraph adds overhead
- [ ] Publishable on LinkedIn as follow-up article
- [ ] Useful as interview talking point for Anthropic/Scale AI

**R7: Voice-Specific Eval Tests**

Add eval tests for voice path:

- STT accuracy: pre-recorded audio samples → verify transcription matches expected text
- TTS latency: measure time from text-ready to audio-streaming
- End-to-end voice latency: speak → hear response (target <5s)
- Interruption test: speak during TTS playback → verify new query processes

Acceptance criteria:
- [ ] Voice evals run in weekly schedule alongside agent evals
- [ ] Voice evals use pre-recorded test audio (no live microphone needed in CI)
- [ ] Failures auto-create GitHub issues

**R8: HITL Override Dashboard (Web UI)**

Simple web page showing:
- Recent determinations with pass/fail status
- Guardrail triggers highlighted
- Override button for caseworker corrections
- Audit log

Acceptance criteria:
- [ ] Accessible at `/dashboard` route
- [ ] Read-only by default, override requires authentication
- [ ] Overrides stored in PostgreSQL with timestamp and caseworker ID

### Future Considerations (P2)

**R9: Multi-turn voice conversations** — "What about her husband?" context resolution
**R10: Multilingual support** — Spanish is highest priority for FQHC populations
**R11: RAG Knowledge Agent** — dynamic policy retrieval for annual Medicaid rule changes
**R12: Fine-tuning** — use override data to fine-tune the model on FQHC-specific patterns
**R13: CrewAI comparison** — build the same system in CrewAI for a three-way framework comparison

---

## Success Metrics

### Leading Indicators (within 1 week of Phase 2 completion)

| Metric | Target | Measurement |
|---|---|---|
| All 16 seed patients produce identical results | 100% | A/B comparison (Phase 1 vs Phase 2) |
| Voice end-to-end latency | <5s | Timed test with pre-recorded audio |
| LangSmith trace coverage | 100% of agent calls traced | LangSmith dashboard |
| HITL interruption works | Override processed in <1s | Manual test |
| Checkpoint persistence | Patient context survives session restart | PostgreSQL query |

### Lagging Indicators (within 1 month)

| Metric | Target | Measurement |
|---|---|---|
| Framework comparison document published | Complete | docs/FRAMEWORK_COMPARISON.md |
| LinkedIn article published | Posted | LinkedIn |
| Interview readiness: can explain LangGraph trade-offs | Confident | Self-assessment |
| Voice demo working end-to-end | Demoable | Screen recording |
| Open source engagement | Stars/forks increase | GitHub metrics |

---

## Technical Architecture

### Directory Structure (additions to Phase 1)

```
medicaid-fqhc-copilot/
├── agents/                       # UNCHANGED from Phase 1
│   ├── eligibility.py
│   ├── memory.py
│   ├── knowledge.py
│   ├── eval_correctness.py
│   ├── eval_efficiency.py
│   └── eval_quality.py
├── graph/                        # NEW — LangGraph orchestration
│   ├── __init__.py
│   ├── state.py                  # CopilotState TypedDict
│   ├── nodes.py                  # Node wrappers for each agent
│   ├── edges.py                  # Conditional routing logic
│   └── copilot.py                # Compiled graph (replaces router.py)
├── voice/                        # NEW — Voice interface
│   ├── __init__.py
│   ├── stt.py                    # Whisper API integration
│   ├── tts.py                    # OpenAI TTS integration
│   ├── websocket.py              # WebSocket handler
│   └── audio_utils.py            # PCM/opus conversion
├── dashboard/                    # NEW — HITL override UI (P1)
│   ├── templates/
│   │   └── dashboard.html
│   └── routes.py
├── docs/                         # NEW — Documentation
│   ├── FRAMEWORK_COMPARISON.md
│   ├── VOICE_ARCHITECTURE.md
│   └── LANGGRAPH_MIGRATION.md
├── router.py                     # PRESERVED — Phase 1 router (kept for comparison)
├── eligibility.py                # UNCHANGED — deterministic engine
├── prompts.py                    # UNCHANGED
├── config.py                     # UPDATED — add voice config, LangSmith keys
├── server.py                     # UPDATED — add /voice WebSocket, /dashboard routes
├── evals/
│   ├── run_correctness.py        # UNCHANGED
│   ├── run_efficiency.py         # UNCHANGED
│   ├── run_quality.py            # UNCHANGED
│   ├── run_all.py                # UNCHANGED
│   └── run_voice.py              # NEW — voice-specific evals
├── tests/
│   ├── test_graph.py             # NEW — LangGraph orchestration tests
│   ├── test_voice.py             # NEW — voice integration tests
│   └── ...                       # Phase 1 tests unchanged
├── render.yaml                   # UPDATED — add voice dependencies
├── .github/
│   └── workflows/
│       ├── deterministic_evals.yml
│       ├── full_agent_evals.yml
│       └── voice_evals.yml       # NEW — weekly voice tests
├── PRD_Phase1.md
└── PRD_Phase2.md                 # This document
```

### LangGraph vs. Plain Python — Key Differences

| Concern | Phase 1 (Plain Python) | Phase 2 (LangGraph) |
|---|---|---|
| Orchestration | `router.py` — sequential function calls | `graph/copilot.py` — StateGraph with typed nodes and edges |
| State passing | Function arguments and return values | `CopilotState` TypedDict flows through the graph |
| Conditional routing | if/else in router.py | `add_conditional_edges` with routing function |
| Checkpointing | None (stateless per request) | `MemorySaver` → PostgreSQL, keyed by patient-{id} |
| HITL | Not supported | `interrupt_before` on eval nodes |
| Streaming | Custom SSE implementation | LangGraph `.astream()` |
| Observability | stdout JSON logs | LangSmith traces (auto-instrumented) |
| Error recovery | try/except in router | LangGraph retry policies per node |

### Voice Architecture

```
┌──────────────┐     WebSocket      ┌──────────────┐
│  Caseworker   │ ◄──── audio ─────► │  FastAPI      │
│  (browser or  │                    │  WebSocket    │
│   device)     │                    │  Handler      │
└──────────────┘                    └──────┬───────┘
                                           │
                                    ┌──────▼───────┐
                                    │  STT (Whisper)│
                                    │  audio → text │
                                    └──────┬───────┘
                                           │
                                    ┌──────▼───────┐
                                    │  LangGraph    │
                                    │  StateGraph   │
                                    │  (same flow)  │
                                    └──────┬───────┘
                                           │
                                    ┌──────▼───────┐
                                    │  TTS (OpenAI) │
                                    │  text → audio │
                                    └──────┬───────┘
                                           │
                                    WebSocket audio
                                    back to caseworker
```

Latency budget:
- STT: ~500ms (Whisper API)
- LLM + Agents: ~1,500ms (same as text path)
- TTS: ~500ms (OpenAI TTS, streaming)
- Network overhead: ~200ms
- **Total: ~2,700ms** (target <5,000ms)

---

## Open Questions

| Question | Owner | Blocking? |
|---|---|---|
| LangSmith pricing — is the free tier sufficient for PoC? | Engineering | Yes — check before integrating |
| Whisper API vs. Deepgram: latency benchmark needed | Engineering | No — start with Whisper, benchmark later |
| Should Phase 1 router.py be preserved or deleted? | Engineering | No — recommend preserve for comparison |
| LangGraph checkpointer: PostgreSQL or SQLite for PoC? | Engineering | No — PostgreSQL (already have it) |
| Voice: browser-based or dedicated device? | Product | No — browser first, device later |
| Should HITL overrides be used as fine-tuning training data? | Engineering/Legal | No — defer to future, flag HIPAA implications |

---

## Implementation Plan

| Week | Deliverable | Validation |
|---|---|---|
| Week 1 | LangGraph StateGraph replaces router.py. All evals pass. | A/B comparison: Phase 1 vs Phase 2 identical |
| Week 2 | Checkpointing + HITL interruption working | Patient context persists across sessions |
| Week 3 | Voice interface (STT + TTS + WebSocket) | Speak → hear determination in <5s |
| Week 4 | LangSmith integration + Framework Comparison doc | Full traces visible, doc published |
| Week 5 | Voice evals, HITL dashboard, polish | Weekly CI runs voice tests, dashboard demoable |

---

## Design Principles

1. **Agents don't change.** Phase 2 changes the orchestration, not the agents. If an agent worked in Phase 1, it works identically in Phase 2.
2. **Voice is an interface, not an agent.** STT and TTS are input/output adapters. The same StateGraph processes voice and text requests.
3. **Framework adoption is a measured decision.** We document exactly what LangGraph gives us (checkpointing, HITL, tracing) and what it costs us (dependency, debugging opacity, learning curve).
4. **Preserve Phase 1 for comparison.** Keep router.py in the repo. The side-by-side comparison is the LinkedIn article and the interview story.
5. **Human-in-the-loop is non-negotiable in healthcare AI.** This was the thesis of the HealthTech Summit 2026 talk. Phase 2 makes it real — caseworkers can interrupt, override, and correct. The system augments human judgment, it doesn't replace it.
