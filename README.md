# muscle-memory

**LLM-driven UI automation that learns once, replays deterministically.**

An AI agent discovers how to automate a task on a real UI (no APIs).
The successful run is recorded as a reusable, parameterized artifact.
Replay executes that artifact deterministically — no LLM in the loop.

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
- Agent observes page state (form fields, visible text, interactive elements)
- Decides what to do next (with Claude)
- Acts on the UI (Playwright)
- Verifies each action with a checkpoint, retries on failure
- Records every event to a timestamped log

### Phase 2: Recording
- Successful run becomes a structured artifact
- Parameterized for reuse (works with different inputs)
- Versioned (semver in artifact metadata)

### Phase 3: Replay (Deterministic)
- Read artifact + inputs
- Execute steps without LLM
- Distinguish business outcomes (member not found) from technical failures
- Return outputs

```
Discovery   → Playwright + Claude   (live browser, LLM decides)
Recorder    → no Playwright, no LLM (pure file transform)
Replay      → Playwright, no LLM    (live browser, fixed script)
```

---

## Setup

### Requirements
- Python 3.10+
- Claude API key (from Anthropic)

### Installation

```bash
git clone https://github.com/<your-username>/muscle-memory.git
cd muscle-memory
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# API key — either export it, or put it in a .env file (loaded via python-dotenv)
echo 'ANTHROPIC_API_KEY=your-key-here' > .env
```

### Running the Demo

**Terminal 1 — start the mock banking app**
```bash
python src/mock_app.py
# Serves http://localhost:8000/login
```

**Terminal 2 — run the three phases in order**

1. **Discovery** (LLM-driven, Claude in the loop). Goal and member ID are set in the `__main__` block of `agent.py`.
```bash
python src/agent.py
# → evidence/discovery_run_<timestamp>.json + per-step screenshots
```

2. **Record** the successful run as a parameterized artifact. Pass the member ID used during discovery so it can be replaced with `{member_id}`.
```bash
python src/artifact_recorder.py evidence/discovery_run_<timestamp>.json 12345
# → evidence/artifact.json
```

3. **Replay** against a member the LLM never saw — no Claude calls.
```bash
python src/replay_engine.py evidence/artifact.json 67890
# → Success: True, Outputs: {'member_name': 'Jane Smith', 'balance': '2500.0'}

python src/replay_engine.py evidence/artifact.json 99999
# → Success: False, Reason: business_outcome (member not found — reported, not retried)
```
### Running the tests

```bash
pytest -v
```

Nineteen unit tests covering parameter substitution, guardrails, redaction, and artifact recording. No browser or API key required.
---

## Project Structure

```
muscle-memory/
├── README.md
├── DESIGN_NOTES.md               # Architecture decisions and rationale
├── REPORT.md                     # Design write-up
├── requirements.txt
├── members.json                  # Mock app data (3 test members)
├── .env                          # ANTHROPIC_API_KEY (gitignored)
│
├── src/
│   ├── mock_app.py               # Flask app — hostile banking UI
│   ├── agent.py                  # Discovery loop orchestrator (7 phases)
│   ├── phases.py                 # OBSERVE / DECIDE / ACT / CHECKPOINT / HANDLE / STOP / RECORD
│   │                             #   + multi-signal element resolver (find_element)
│   ├── helpers.py                # Page extraction, redaction, value extraction, response parsing
│   ├── config.py                 # Redaction list, evidence directory
│   ├── artifact_recorder.py      # discovery_run.json → artifact.json
│   └── replay_engine.py          # Deterministic replay, no LLM
│
├── templates/                    # login / results / action / error pages
│
└── evidence/
    ├── discovery_run_<ts>.json   # Full event log from a discovery run
    ├── step_NNN_screenshot.png   # Per-step screenshots from discovery
    ├── artifact.json             # Recorded, parameterized artifact
    └── replay_run_<id>_<ts>.json # Replay execution logs
├── tests/
│   ├── conftest.py               # Puts src/ on the path, stubs the API key
│   ├── test_replay.py
│   ├── test_guardrails.py
│   ├── test_redaction.py
│   └── test_recorder.py
```

---

## Design Decisions

See **DESIGN_NOTES.md** for:
- Why we chose hostile HTML over clean UIs
- Multi-signal locator strategy (5 fallback strategies)
- Agent loop structure (7 phases)
- Error handling + human escalation
- Security (redaction of PII)

---

## Key Features

**Hostile HTML target** — nested-table layout, no IDs, randomized class names, div-as-button controls (login + results pages)
**Multi-signal element resolver** — placeholder → button text → accessibility attributes → CSS → text match, in priority order
**LLM-driven discovery** — 7-phase loop with per-action-type checkpoints and bounded retry
**Typed, parameterized artifact** — contract (inputs/outputs), ordered steps, checkpoints, `{member_id}` placeholders
**Deterministic replay** — same artifact, unseen member ID, zero LLM calls (verified: member 67890)
**Business-outcome handling** — member-not-found detected and reported distinctly from technical failure (verified: member 99999)
**Redaction** — sensitive form values redacted before reaching the LLM; passwords never captured
🔲 **Action allowlist** — block withdraw/transfer-type actions — *in progress*
🔲 **Human escalation** — pause / operator takeover / resume — *in progress*

---

## Status

**Done:** mock app · discovery loop · artifact recording · replay engine · verified evidence (discovery run, artifact, two replay runs)
**In progress:** action allowlist · human escalation · tests · REPORT.md

---

## License

MIT

---

## Contact

Built for Interface.ai assignment.
Questions? See DESIGN_NOTES.md for design rationale.