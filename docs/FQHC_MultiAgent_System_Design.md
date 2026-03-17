# Multi-Agent FQHC Copilot — System Design
## Version 1.0 | 2026-03-17

### 1. Requirements

**Functional:**
- Determine Medicaid eligibility across all 50 states + territories
- Support voice interaction (caseworker speaks, agent responds verbally)
- Each eval dimension runs as an independent agent
- Per-patient memory persists across sessions
- Human-in-the-loop override capability for caseworkers

**Non-Functional:**
- Latency: <3s for text, <5s for voice (STT + LLM + TTS)
- Cost: ≤6 API calls per determination (across all agents combined)
- Correctness: 100% on deterministic edge cases (hard requirement)
- HIPAA-aware: no cross-patient data leakage, audit trail for every determination

**Constraints:**
- Solo developer (for now)
- OpenAI as primary LLM provider (pinned model versions)
- Render deployment, PostgreSQL, existing MCP infrastructure
- Budget-conscious — eval costs must be tiered

---

### 2. Agent Roles

**Agent 1: Eligibility Agent (Primary)**
- Existing ReAct agent, upgraded
- Receives: patient record + memory context (injected) + FPL data (embedded)
- Produces: eligibility determination + natural language explanation
- Model: gpt-4o-mini-2024-07-18 (pinned)
- Guardrails: MAX_ITERATIONS = 10, tool result sanitization (10K chars)

**Agent 2: Memory Agent**
- Handles all Mem0 SDK interactions
- Pre-call: searches memory by patient-{id}, injects into Eligibility Agent system prompt
- Post-call: extracts key facts, saves to patient memory
- HIPAA enforcement: strictly scoped by patient ID

**Agent 3: Knowledge Agent**
- Manages static knowledge (FPL tables, state expansion status, special rules)
- Queryable service — can be updated independently without touching prompts
- Future: RAG for dynamic policy updates (50-state annual changes)

**Agent 4: Correctness Eval Agent**
- Deterministic Python eligibility calculation
- Compares against Eligibility Agent output
- No LLM — pure code
- Runs: every push + real-time guardrail

**Agent 5: Efficiency Eval Agent**
- Counts API calls, monitors tool usage
- Flags: >4 API calls, banned tools (Fetch MCP)
- Runs: post-determination + weekly

**Agent 6: Quality Eval Agent**
- LLM-based — checks keywords, reasoning, citations
- Receives: patient record + determination + ground truth
- Upgraded QA agent with own eval dimension
- Runs: post-determination + weekly

**Agent 7: Voice Interface Agent**
- STT: Whisper API (or Deepgram for lower latency)
- LLM: Routes to Eligibility Agent
- TTS: OpenAI TTS API (or ElevenLabs)
- WebSocket for real-time streaming
- Latency budget: STT ~500ms + LLM ~1.5s + TTS ~500ms = ~2.5s target
- Same 5-layer defense applies

---

### 3. Architecture Diagram

```
                         ┌─────────────────────┐
                         │   VOICE INTERFACE    │
                         │  (STT → LLM → TTS)  │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │   ROUTER / GATEWAY    │
                         │  (FastAPI + WebSocket) │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
           ┌────────▼──────┐ ┌─────▼──────┐ ┌──────▼───────┐
           │  ELIGIBILITY   │ │  MEMORY    │ │  KNOWLEDGE   │
           │  AGENT         │ │  AGENT     │ │  AGENT       │
           │  (Primary)     │ │  (Mem0)    │ │  (FPL/Rules) │
           └────────┬──────┘ └─────┬──────┘ └──────┬───────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │      DETERMINISTIC ENGINE      │
                    │      (eligibility.py)           │
                    └───────────────┬───────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
     ┌────────▼──────┐    ┌────────▼──────┐    ┌────────▼──────┐
     │  CORRECTNESS   │    │  EFFICIENCY   │    │  QUALITY      │
     │  EVAL AGENT    │    │  EVAL AGENT   │    │  EVAL AGENT   │
     └────────┬──────┘    └────────┬──────┘    └────────┬──────┘
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    │
                         ┌──────────▼───────────┐
                         │   VERDICT AGGREGATOR  │
                         │   (pass/fail + report)│
                         └──────────────────────┘
```

---

### 4. Data Flow — Single Determination

1. Caseworker speaks → STT → text
2. Router parses patient ID
3. Memory Agent searches patient-{id}
4. Knowledge Agent provides FPL tables + state rules
5. Eligibility Agent runs ReAct loop (≤10 iterations)
6. Deterministic Engine computes ground truth (parallel)
7. Three Eval Agents run independently:
   - Correctness: compare determination vs engine
   - Efficiency: count API calls, check banned tools
   - Quality: verify keywords, reasoning, citations
8. Verdict Aggregator:
   - All pass → respond
   - Correctness fail → override with engine answer
   - Quality fail → append correction
9. Memory Agent saves determination
10. TTS → caseworker hears response

---

### 5. Eval Architecture

| Eval Tier | Trigger | Agents | Cost | Latency |
|---|---|---|---|---|
| Deterministic | Every push | Correctness only | $0 | <1s |
| Real-time guardrail | Every determination | Correctness + Efficiency | $0 | <100ms |
| Full agent eval | Weekly | All 3 eval + Eligibility | ~$2-5/run | ~5min |
| Voice integration | Weekly | Voice + Eligibility + Evals | ~$5-10/run | ~10min |

---

### 6. Trade-Off Analysis

| Decision | Choice | Alternative | Why |
|---|---|---|---|
| Agent communication | In-process Python | HTTP microservices | PoC — no network overhead. Refactor when team >1 |
| STT provider | Whisper API | Deepgram | Simpler ecosystem. Switch if latency >800ms |
| Voice streaming | WebSocket | WebRTC | Simpler, sufficient for 1:1. WebRTC for multi-party |
| Knowledge Agent | Embedded + queryable | Full RAG | RAG adds complexity. Embedded fine for static data |
| Eval agents | Same process | Separate services | Lightweight — no need to distribute yet |
| Orchestration | Plain Python router | LangGraph / CrewAI | No framework dependency. Easier to debug and test |

---

### 7. Scale Considerations

- Agent communication: Move to Redis Streams/NATS at >100 concurrent users
- Knowledge Agent: Add RAG for dynamic policy changes
- Voice: Add interruption handling + silence detection
- Eval agents: Separate containers when >50 test cases
- Observability: OpenTelemetry tracing across agents
- HITL dashboard: Web UI for caseworker overrides → builds fine-tuning data

---

### 8. Implementation Phases

**Phase 1 (Week 1-2):** Refactor existing monolith into agent modules
- Extract Memory Agent, Knowledge Agent from agent.py
- Router/Gateway layer
- All existing evals still pass

**Phase 2 (Week 3):** Independent eval agents
- Split 3 eval dimensions into separate agents
- Verdict Aggregator
- GitHub Actions updated for multi-agent eval pipeline

**Phase 3 (Week 4):** Voice interface
- WebSocket endpoint
- Whisper STT + OpenAI TTS integration
- Voice-specific eval tests

**Phase 4 (Ongoing):** Polish + observability
- OpenTelemetry tracing
- HITL override dashboard
- LinkedIn post about multi-agent architecture
