# muscle-memory

**LLM-driven UI automation that learns once, replays deterministically.**

An AI agent discovers how to automate a task on a real UI (no APIs). 
The successful run is recorded as a reusable artifact. 
Replay executes that artifact deterministically—no LLM in the loop.

Built for legacy banking UIs and other hostile interfaces where robust element targeting and error handling matter.

---

## The Problem

Most UI automation systems either:
- **Require APIs** (not available in legacy systems)
- **Hallucinate** (LLM every time, slow and unreliable)
- **Break on UI changes** (fragile selectors)

**muscle-memory solves this:**
1. LLM discovers the flow once (learns it)
2. Flow is recorded as a typed artifact
3. Replay executes it deterministically (fast, reliable, no model needed)

---

## How It Works

### Phase 1: Discovery (LLM-driven)
- Agent observes page state
- Decides what to do (with Claude)
- Acts on the UI (Playwright)
- Records what happened

### Phase 2: Recording
- Successful run becomes a structured artifact
- Parameterized for reuse (works with different inputs)
- Versioned (tracks variants across tenants)

### Phase 3: Replay (Deterministic)
- Read artifact + inputs
- Execute steps without LLM
- Handle errors gracefully
- Return outputs

---

## Setup

### Requirements
- Python 3.10+
- Claude API key (from Anthropic)

### Installation

```bash
# Clone repo
git clone https://github.com/sargam.shukla12/muscle-memory.git
cd muscle-memory

# Install dependencies (updated as we code)
pip install -r requirements.txt

# Set Claude API key
export ANTHROPIC_API_KEY="your-key-here"
```

### Running the Demo

**1. Start the mock app (hostile banking UI)**
```bash
python src/mock_app.py
# Opens http://localhost:8000
```

**2. Run agent discovery** (LLM learns the flow)
```bash
python src/agent.py \
  --goal "check balance for member 12345" \
  --member_id 12345 \
  --output artifact.json
```

**3. Run replay** (deterministic execution, no LLM)
```bash
python src/replay_engine.py \
  --artifact artifact.json \
  --member_id 67890
# Same flow, different input, no model needed
```

---

## Project Structure

```
muscle-memory/
├── README.md                 # This file
├── DESIGN_NOTES.md          # Complete architecture decisions
├── REPORT.md                # Design write-up (1-3 pages)
│
├── src/
│   ├── __init__.py
│   ├── agent.py             # LLM-driven agent loop
│   ├── mock_app.py          # Flask app (hostile HTML)
│   ├── replay_engine.py     # Deterministic execution
│   └── locator.py           # Multi-signal element resolver
│
├── tests/
│   ├── __init__.py
│   └── test_replay.py       # Replay logic tests
│
├── evidence/
│   ├── discovery_run_001.json      # Artifact from discovery
│   ├── discovery_logs.txt          # Events + debugging
│   ├── replay_run_001.json         # Replay execution
│   └── screenshots/                # Evidence images
│
├── requirements.txt         # Dependencies
└── .gitignore
```

---

## Design Decisions

See **DESIGN_NOTES.md** for:
- Why we chose hostile HTML over clean UIs
- Multi-signal locator strategy (4 fallback strategies)
- Agent loop structure (7 phases)
- Error handling + human escalation
- Security (redaction of PII)

---

## Key Features

✅ **Handles hostile HTML** — Table layouts, no IDs, missing semantics  
✅ **Robust element targeting** — Accessibility tree + label + CSS + visual fallbacks  
✅ **Deterministic replay** — Same inputs → same outputs, no LLM needed  
✅ **Error handling** — Business outcomes, recoverable errors, hard failures  
✅ **Human escalation** — Pause automation, let human intervene, resume  
✅ **Security** — Redacts PII, omits secrets, allowlist enforcement  

---

## Status

**In Progress:**
- Mock app structure
- Agent loop implementation
- Artifact recording
- Replay engine
- Real discovery run + evidence

**See DESIGN_NOTES.md for architecture overview.**

---

## License

MIT

---

## Contact

Built for Interface.ai assignment.  
Questions? See DESIGN_NOTES.md for design rationale.
