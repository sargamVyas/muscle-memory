# Computer-Use Automation System — Design Notes

**Project:** Build LLM-driven UI automation system with deterministic replay
**Timeline:** 2-3 weeks, 3-4 hours/day
**Author:** Started [Date]

---

# Day 1: Architecture Decisions

## Decision 1: Target Application

### What We Decided
Build a **scoped, intentionally hostile mock web application** for automation testing.

### Why
- **Matches the problem domain** — The assignment emphasizes legacy banking UIs with no API and no clean DOM. This is the *hard* case we're actually solving for.
- **Proves the design** — If our approach works on hostile HTML, it works in production. Clean UIs don't validate robustness.
- **Credibility** — Shows we understood the assignment, not taking the easy path.
- **Manageable scope** — A simple mock (not a full banking system) fits our timeline.

### Advantages of This Choice
✅ **Realistic** — Mirrors real enterprise environments (table layouts, nested divs, no test IDs)
✅ **Validates design** — Forces us to handle UI instability, CSS selector fragility
✅ **Controlled environment** — We build it, so no flaky hosting or external dependencies
✅ **Differentiator** — Most submissions probably pick clean UIs; this shows judgment
✅ **Better learning** — Forces deeper thinking about robustness

### Disadvantages / Tradeoffs
❌ **More engineering work** — Building a hostile mock takes 4-6 hours
❌ **Slower iteration** — Flaky selectors = more debugging
❌ **Higher risk** — If mock is too hostile, we lose time

### Alternatives Considered

**Option 1: Clean modern web app** (React, Shopify sandbox)
- *Why not:* Doesn't match problem. Misses the hard part (robust element targeting when selectors are unstable).

**Option 3: Hybrid** (clean for discovery, hostile for testing)
- *Why not:* Extra setup complexity. But a valid fallback if we get stuck mid-project.

### Key Concept: What "Hostile" Means
**Intentionally hostile surface** = UI designed to be hard to automate (like real legacy systems)
- **Framesets** — UI split across `<iframe>` elements
- **Table-based layout** — No semantic HTML, deeply nested `<table>` for layout
- **Non-semantic markup** — `<div class="xyz123">` instead of `<button>` or `<input>`
- **No test IDs** — Developers never added `data-testid` or stable attributes
- **Server-rendered** — Page reloads on every action, state in URL params or hidden fields
- **Visual layout only** — Screenshot + coordinates might be the only reliable surface

**Our mock:** Simple Flask app with 1-2 forms. Intentional friction: table layout, no data-testid, nested divs, maybe one `<iframe>`. Stable but ugly.

**Example flow:** Member ID lookup → form submission → details display (table) → initiate action

---

## Decision 2: Computer-Use Approach

### What We Decided
Use **Playwright (browser automation)** as primary approach, with **accessibility tree as fallback** for locating elements.

### Why
- **Realistic** — Production systems use this layered approach (try smart selectors, fall back gracefully)
- **Fits timeline** — No extra vision complexity, straightforward implementation
- **Works for hostile surfaces** — Accessibility tree is more stable than raw DOM selectors
- **Matches tools** — Playwright has excellent APIs and documentation

### Advantages of This Choice
✅ **Robust** — Two-tier targeting: primary (CSS/XPath) + fallback (accessibility)
✅ **Fast** — Browser automation is quick for discovery loop
✅ **Deterministic for replay** — Selectors are your artifact foundation
✅ **Practical** — This is how real production automation works

### Disadvantages / Tradeoffs
❌ **Hostile HTML has unstable selectors** — CSS classes change, no IDs, so fallback strategy is critical
❌ **Accessibility tree not guaranteed** — Legacy apps often have broken trees

### Alternatives Considered

**Option B: Screenshot + vision** (Claude sees the UI visually)
- *Why not:* More LLM calls during discovery = slower and more expensive. Replay determinism is harder (coordinates can drift). Good for pure "computer-use" angle but breaks timeline.

**Option C: Accessibility tree only**
- *Why not:* Primary locator without CSS fallback is fragile. Better to have both.

### Key Concepts

**Playwright:**
- Modern browser automation library (fast, good APIs)
- Can query elements via CSS selectors, XPath, accessibility attributes
- Can take screenshots, read page state, simulate clicks/typing

**Primary locator:** CSS selector or XPath (stable if page is designed well)

**Fallback locator:** Accessibility tree
- What screen readers see (role + accessible name)
- More stable because based on semantic meaning, not styling
- Example: `{role: "button", name: "Search"}` instead of `.btn-primary.search-btn`

**Why fallback matters for hostile HTML:**
- Hostile surfaces = unstable CSS classes, random IDs, no test attributes
- Accessibility tree = based on semantic intent (a button is a button, regardless of class name)
- Strategy: Try CSS first (fast). If it fails, try accessibility (more reliable).

---

## Decision 3: LLM Observation Strategy

### What We Decided
The LLM sees **filtered, extracted form fields** (not the full accessibility tree) with their current values, plus page title, visible text, and error messages.

### Why
- **Fewer tokens** — No full tree dump, only relevant information
- **Better focus** — Cleaner context = better LLM reasoning
- **Security-conscious** — Redact sensitive data (balance, account numbers) from LLM observation
- **Efficient cost** — Fewer tokens = faster + cheaper
- **Same robustness** — Still have accessibility metadata for targeting

### Advantages of This Choice
✅ **Cost-effective** — Fewer tokens per step
✅ **Clear signal** — LLM sees essentials: "there's a field called Member ID, empty, required"
✅ **Security** — Sensitive data redacted
✅ **Debugging** — Easy to see what Claude saw and why it decided to act
✅ **Realistic** — This is how production systems filter observations

### Disadvantages / Tradeoffs
❌ **Requires extraction logic** — Need to parse UI and identify form fields
❌ **Risk of missing context** — If we filter too aggressively, we might hide important info
❌ **Extra code** — Field extraction adds ~50 lines of code

### Alternatives Considered

**Option A: "See everything"** (full accessibility tree)
- *Why not:* Too many tokens. LLM might hallucinate actions for elements that don't exist. Noisier = worse decisions.

**Option C: Screenshot + questions** (vision-based)
- *Why not:* Many more tokens. Slower discovery. Breaks timeline.

### Key Concepts

**What the LLM observes at each step:**
```
{
  page_title: "Member search",
  url: "http://localhost:8000/members",
  form_fields: [
    {label: "Member ID", type: "input", value: "", role: "searchbox", required: true},
    {label: "Search", type: "button", role: "button"}
  ],
  visible_text: "Enter a member ID to search",
  messages: [],  // errors, if any
  last_action_result: "success"
}
```

**Claude's prompt is simple:**
- Goal
- Current page name + URL
- Available form fields
- Visible text
- Any errors
- → "What's next?"

**Claude responds:**
```json
{
  "reasoning": "The form is asking for a member ID. I should type the member ID.",
  "action_type": "type",
  "target": {"role": "searchbox", "name": "Member ID"},
  "value": "12345"
}
```

**Redaction:** Don't expose sensitive fields unnecessarily
- Example: if field is labeled "Savings Balance", show `"1500**"` not `"1500.00"`
- Fields to redact: balance, account, password, token, SSN, PIN, card, member_id

---

## Decision 4: Artifact Schema (Recording Format)

### What We Decided
Record successful discovery runs as **typed, parameterized, version-tracked artifacts** that can be replayed deterministically.

### Why
- **Reusable** — Same artifact works with different inputs (member_id = 12345 vs. 67890)
- **Reviewable** — Humans can read it and understand what it does
- **Deterministic** — Replay engine has no LLM; it just follows the artifact
- **Versionable** — Track variants across tenants (lookup_member:1.0 vs. 1.1)
- **Auditable** — Clear record of what was automated and how

### Advantages of This Choice
✅ **Production-ready** — This is how real systems record automation
✅ **Scales to multi-tenant** — Version tracking enables reuse across institutions
✅ **Separation of concerns** — LLM discovery separate from deterministic replay
✅ **Debuggable** — Error handling is explicit (business outcomes vs. failures)

### Disadvantages / Tradeoffs
❌ **More complex schema** — Requires careful design (metadata, steps, error handling, etc.)
❌ **Extraction logic needed** — Converting discovery run → artifact requires code
❌ **Edge cases** — Parameterization, timeout handling, etc.

### Alternatives Considered

**Naive approach:** Just save LLM transcript
- *Why not:* Not reusable. Contains reasoning that changes per run. Doesn't help replay.

**Flat step list:** Just steps, no contract/metadata
- *Why not:* Not reviewable. Caller doesn't know inputs/outputs. No version tracking.

### Key Concepts

**Artifact has 5 parts:**

**1. Metadata**
- ID: "lookup_member"
- Version: "1.0.0" (semver, tracks variants)
- Status: "draft" | "approved" | "deprecated"
- Created: timestamp + discovery run ID

**2. Contract (API)**
- **Inputs:** What caller provides (e.g., member_id: string)
- **Outputs:** What caller gets back (e.g., savings_balance, member_name)

**3. Steps (the flow)**
- Each step is a recorded action (navigate, click, type, wait, extract)
- Each step has: action, target (accessibility role + name, CSS fallback), checkpoint (how to know it worked), timeout, on_failure (retry/escalate)

**4. Error Handling**
- **Expected business outcomes:** "no member found" → return {success: false, reason: "member_not_found"}
- **Recoverable conditions:** timeout → retry 3x
- **Hard failures:** session expired, layout changed → escalate to human

**5. Parameterization**
- Values from caller are inserted at replay time
- Artifact uses placeholders: `{member_id}`
- Replay substitutes actual values

**Example artifact structure (conceptual):**
```
Metadata:
  id: "lookup_member_and_extract_balance"
  version: "1.0.0"
  goal: "Look up member by ID, extract savings balance"

Contract:
  inputs: {member_id: string}
  outputs: {savings_balance: string, member_name: string}

Steps:
  1. Navigate to http://localhost:8000/members
     Checkpoint: page_loads (wait for searchbox to appear)
  
  2. Type into "Member ID" field
     Value: {member_id} (parameterized)
     Checkpoint: text_appears (verify text in field)
  
  3. Click "Search" button
     Checkpoint: page_changes (URL changes or results appear)
  
  4. Wait for results
     Checkpoint: element_visible (wait for results container)
  
  5. Extract data
     Extract: savings_balance, member_name (using regex or selectors)
     Checkpoint: data_extracted

Error Handling:
  If "No member found" appears:
    → Return {success: false, reason: "member_not_found"}
  If session expires:
    → Escalate to human
  If selector not found (after 3 retries):
    → Escalate to human
```

---

## Summary: Design Decisions So Far

| Phase | Decision | Why | Key Tradeoff |
|-------|----------|-----|--------------|
| **Target** | Scoped hostile mock | Matches problem, validates design | More engineering work |
| **Computer-use** | Playwright + Accessibility fallback | Robust, realistic | Need good fallback strategy |
| **Observation** | Filtered fields (not full tree) | Fewer tokens, better focus | Need extraction logic |
| **Artifact** | Typed, parameterized, versioned | Reusable, deterministic, auditable | Complex schema |

---

## Architecture Diagram
[See visual: Three phases (discovery, recording, replay) with support systems]

---

# Day 2: Smaller Details & Mock App Architecture

## Decision 4b: Multi-Signal Locator Resolution Strategy

### What We Decided
Use a **priority-ordered, multi-signal resolver** to find elements on the UI. Don't just rely on one method.

**Locator resolver tries in order:**
1. **Semantic/Accessibility** — role + name (e.g., "textbox" named "Member ID")
2. **Label/Text Relationship** — find input by associated label
3. **DOM Structure** — CSS selector, XPath (fallback)
4. **Visual Location** — screenshot coordinates (last resort)

### Why
- **Robust** — If one signal breaks, next one takes over (graceful degradation)
- **Hostile-HTML friendly** — Handles broken accessibility, missing IDs, unstable classes
- **Production-grade** — This is how real Selenium/Playwright frameworks work
- **Multi-tenant ready** — Different tenants have different UI strengths:
  - Tenant A: Good accessibility
  - Tenant B: No accessibility, but good labels
  - Tenant C: Neither, only visual stability
  - Same artifact works everywhere (different signal wins each time)
- **Human-readable** — Artifact says `"Member ID input"` not complex selector

### Advantages of This Choice
✅ **Defensive programming** — One failing signal doesn't crash replay
✅ **Realistic** — Mirrors production automation systems
✅ **Scalable** — Enables multi-tenant reuse
✅ **Debuggable** — Clear which signal succeeded

### Disadvantages / Tradeoffs
❌ **More complex** — Need to implement 4 different strategies (~50 lines per strategy)
❌ **Artifacts are bigger** — Store all 4 strategies (but still readable)
❌ **More debugging** — Need to understand which signal won (but provides valuable info)

### Alternatives Considered

**Simpler approach:** Just CSS selector + accessibility tree (2 signals)
- *Why not:* Doesn't handle all failure modes. Misses label/visual strategies that work when both fail.

### Key Concept

**Artifact target format:**
```json
{
  "description": "Member ID input",
  "strategies": [
    {
      "type": "accessibility",
      "role": "textbox",
      "name": "Member ID"
    },
    {
      "type": "label",
      "associated_label": "Member ID"
    },
    {
      "type": "css",
      "selector": "input[name='member_id']"
    },
    {
      "type": "visual",
      "approximate_location": "top-left of form"
    }
  ]
}
```

**Replay logic:**
```
For each strategy in order:
  Try to find element
  If found → use it ✓
  If not found → try next strategy
If all strategies fail → escalate to human
```

---

## Decision 5: Artifact Storage Format

### What We Decided
Store artifacts as **JSON** (not YAML).

### Why
- **Cross-compatible** — Every language has JSON support (Python, JavaScript, Go, etc.)
- **Language-agnostic** — Can share artifacts across different services/languages
- **Data types clear** — No ambiguity (string is string, not accidentally parsed as boolean)
- **Universal standard** — JSON is the de facto standard for data exchange
- **Easy validation** — JSON Schema available for structured validation

### Advantages of This Choice
✅ **Portable** — Share between Python backend + JavaScript frontend + Go service
✅ **Unambiguous** — Type safety built in
✅ **Industry standard** — Everyone knows JSON
✅ **Future-proof** — Won't change, widely supported forever

### Disadvantages / Tradeoffs
❌ **Slightly verbose** — More characters than YAML
❌ **Less readable than YAML** — But readability is secondary to compatibility

### Alternatives Considered

**YAML:**
- *Why not:* Python-heavy, different parsing libraries behave differently, less universal support.

---

## Decision 6: Redaction Strategy (Security)

### What We Decided
**Completely omit** sensitive fields (password, SSN, PIN) from LLM observation.
**Redact** (show truncated version) for PII fields (balance, account, member_id).

### Why
- **Password/SSN/PIN never needed by LLM** — LLM only needs to know "there's a field" and what to type, not the actual secret
- **Defense in depth** — Smaller surface for data exposure
- **Regulatory compliance** — Financial data protection (GLBA, etc.)
- **Best practice** — Don't expose secrets unnecessarily

### Advantages of This Choice
✅ **Security-conscious** — Minimal PII exposure
✅ **Realistic** — Production systems do this
✅ **Regulatory-friendly** — Meets compliance standards
✅ **No functionality loss** — LLM still works perfectly

### Disadvantages / Tradeoffs
❌ **Extra redaction logic** — ~30 lines of code
❌ **Must maintain redaction list** — If new sensitive fields added, must update

### Redaction Implementation

**Completely omit:**
```json
{
  "form_fields": [
    {"label": "Username", "value": "john_doe"},
    {"label": "Password", "type": "password"}  // No value, just metadata
  ]
}
```

**Redact (truncate):**
```json
{
  "form_fields": [
    {"label": "Member ID", "value": "1234****"},
    {"label": "Savings Balance", "value": "150**"}
  ]
}
```

**Redaction list:**
```
OMIT COMPLETELY:
  - password
  - ssn
  - pin

REDACT (show truncated):
  - balance
  - account
  - card
  - member_id
```

---

## Decision 7: Mock App Architecture

### What We Decided

**Flow:** Automate "Check Balance" operation (Option B)
- Login with member ID
- Search/navigate to member details
- Select "check balance" action
- View and extract balance

**Hostile patterns per page:**

| Page | Hostile Patterns | Semantics | Why |
|------|------------------|-----------|-----|
| **Login** | Table-based layout | ✅ Real `<input>`, `<button>` | Tests Pattern 1; accessibility fallback works |
| **Search/Results** | Table layout + no IDs | ✅ Semantic elements inside | Tests Patterns 1, 2; CSS breaks, accessibility works |
| **Action** | No IDs + missing semantics | ❌ Divs instead of buttons | Tests Patterns 2, 3; forces text/label matching |

### Why This Design

✅ **Tests all 3 hostile patterns** — Validates our design handles real friction
✅ **Tests all 4 locator signals** — Each page uses different strategy:
  - Page 1: Accessibility tree (primary)
  - Page 2: Accessibility + labels (secondary)
  - Page 3: Text matching (fallback)
✅ **Realistic** — Mirrors actual legacy banking UIs
✅ **Deterministic replay** — Same flow works every time
✅ **Data extraction** — Can extract balance and validate system
✅ **Error handling testable** — Can inject "member not found", etc.

### Advantages of This Choice
✅ **Comprehensive** — Tests full system end-to-end
✅ **Credible** — Shows deep understanding of hostile HTML
✅ **Evaluation-friendly** — Evaluators see all 4 locator signals in action

### Disadvantages / Tradeoffs
❌ **4 pages to build** — But each is simple (not full banking system)
❌ **HTML must be carefully hostile** — Can't be too broken (accessibility must still work)

### Key Constraint

**For Page 3 to work:** Action options must have **clear, distinctive text**
```html
<!-- GOOD -->
<div class="option">Check Balance</div>
<div class="option">Withdraw</div>

<!-- BAD (text too generic) -->
<div class="option">Option 1</div>
<div class="option">Option 2</div>
```

Resolver needs clear text to match on.

---

## Decision 8: Artifact Storage & Format

### What We Decided
Artifact stored as **JSON** with this structure:

```json
{
  "metadata": {
    "id": "check_member_balance",
    "version": "1.0.0",
    "goal": "Check member savings balance",
    "status": "draft",
    "created_at": "2025-01-16T...",
    "created_by": "discovery_run_001"
  },
  
  "contract": {
    "inputs": {
      "member_id": {"type": "string", "required": true}
    },
    "outputs": {
      "savings_balance": {"type": "string"},
      "member_name": {"type": "string"}
    }
  },
  
  "steps": [
    {
      "step_id": 1,
      "action": "navigate",
      "url": "http://localhost:8000/login",
      "checkpoint": "page_loads"
    },
    // ... more steps
  ],
  
  "error_handling": {
    "member_not_found": {
      "trigger": "Page shows 'No member found'",
      "response": "return_business_outcome"
    }
    // ... more handlers
  }
}
```

### Why This Format
- **Clear contract** — Callers know inputs/outputs
- **Traceable** — Metadata shows creation source
- **Replayable** — Replay engine has everything needed
- **Versionable** — Track variants across tenants
- **Debuggable** — Error handling is explicit

---

## Summary: All Decisions Locked

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| 1 | Target | Scoped hostile mock | Matches problem, validates design |
| 2 | Computer-use | Playwright + Accessibility | Robust, realistic |
| 3 | LLM observes | Filtered fields | Fewer tokens, better focus |
| 4 | Artifact schema | Typed, parameterized | Reusable, deterministic |
| 4b | Locator strategy | 4-signal resolver | Handles all failure modes |
| 5 | Storage format | JSON | Cross-compatible |
| 6 | Redaction | Omit sensitive, redact PII | Security-conscious |
| 7 | Mock app | Check balance flow, 3 pages | Tests all patterns, realistic |
| 8 | Artifact format | JSON with metadata + steps | Clear, traceable, replayable |

---

## Decision 9: Agent Loop Structure (LLM-Driven Discovery)

### What We Decided

The agent loop has **7 sequential phases**, repeated until goal achieved or stop condition hit:

**Phase 1: OBSERVE**
- Read current page state
- Extract form fields (filtered, not full tree)
- Include: member ID, goal (check balance or withdraw), last action result
- Record as EVENT

**Phase 2: DECIDE**
- Send to Claude: "Given member_id={member_id}, goal={goal}, current state={state}, what's next?"
- Claude responds with JSON: `{action_type, target_description, value, reasoning}`

**Phase 3: ACT**
- Use multi-signal resolver to find element:
  1. Try accessibility tree (role + name)
  2. Try label/text relationship
  3. Try CSS selector
  4. Try visual coordinates
- Perform action (click, type, navigate, wait)
- Record as EVENT

**Phase 4: CHECKPOINT (Verify action worked)**
- Check all three signals:
  1. Did text appear? (e.g., "Balance: $1500")
  2. Did DOM change? (elements added/removed)
  3. Did URL change?
- All 3 pass → Step succeeded ✓
- Any fail → Step failed ✗

**Phase 5: HANDLE RESULT**
- **Success:** Continue to next iteration
- **Timeout:** Log warning, retry 1x (wait 1 sec), then escalate
- **Selector not found:** Try next strategy in multi-signal resolver
- **All strategies failed:** Escalate to human
- **Business outcome** (e.g., "member not found"): Return result to caller
- **Hard failure** (e.g., "access denied"): Escalate to human

**Phase 6: STOP CONDITIONS**
Exit loop if any condition hit (whichever first):
- Same error seen 3x → Stuck, escalate
- Max steps reached (20) → Give up, escalate
- Time limit exceeded (5 min) → Timeout, escalate
- Goal achieved → Success, extract outputs
- Escalation needed → Stop, ask human

**Phase 7: RECORD**
Save all events/evidence for artifact:
```json
{
  "discovery_run_id": "run_001",
  "goal": "Check balance for member 12345",
  "events": [
    {"type": "click", "target": "Search button", "timestamp": "2025-01-16T10:30:45Z"},
    {"type": "page_load", "url": "http://localhost:8000/results", "timestamp": "2025-01-16T10:30:47Z"},
    {"type": "text_appeared", "text": "Member Details", "timestamp": "2025-01-16T10:30:48Z"}
  ],
  "success": true,
  "reason": "Goal achieved",
  "outputs": {
    "member_name": "John Doe",
    "savings_balance": "$1500.00"
  }
}
```

### Why

- **Clear separation of concerns** — Each phase has specific responsibility
- **Robust** — Multi-signal resolver handles hostile HTML
- **Safe** — Retry strategy prevents transient failures, escalation prevents risky continuation
- **Observable** — Events logged for debugging and analysis
- **Production-grade** — Mirrors real automation systems

### Advantages of This Choice

✅ **Handles all failure modes** — Timeout, selector not found, business outcomes, hard failures
✅ **Observable** — Event logging enables analysis of "where things go wrong"
✅ **Safe for financial systems** — Won't blindly continue on risky actions (timeout, access denied)
✅ **Scalable** — Same loop works for different goals with parameterized inputs
✅ **Debuggable** — Events + timestamps enable reproducible debugging
✅ **Multi-signal fallback** — Each strategy can retry with different approach

### Disadvantages / Tradeoffs

❌ **Complex logic** — 7 phases + error handling = more code
❌ **Many decisions** — When to retry vs escalate requires careful tuning
❌ **Event logging overhead** — Recording every action has small performance cost (negligible for discovery)

### Alternatives Considered

**Simpler approach:** Just try action, if fails → escalate
- *Why not:* Misses transient failures (timeouts), doesn't leverage multi-signal resolver, not production-quality

**Vision-based loop:** Claude sees screenshot, makes decisions
- *Why not:* Already decided against (more tokens, slower, breaks timeline)

### Key Insights

**Why checkpoint uses all 3 signals:**
- URL change alone ❌ misses modals, SPAs, slow loads
- DOM change alone ❌ can't distinguish placeholder changes from real results
- Text appearing ✅ most reliable (if "Balance: $1500" shows, goal likely succeeded)
- **All 3 together** → High confidence step actually worked

**Why multi-signal resolver retries with different strategy:**
```
Find "Member ID input":

Try 1: CSS selector "input.member_id"
  → Class changed by vendor, not found ❌

Try 2: Accessibility tree (role="textbox", name="Member ID")
  → Found ✓ (fallback works!)

This is why having 4 strategies matters for hostile HTML.
```

**Why record events (not just artifact):**
- Artifact stores cleaned-up steps (for replay)
- Events store raw history (for analysis + debugging)
- "Why did step 3 fail? Let me check the events..." ← valuable for tuning system

---

## Complete Agent Loop Pseudocode

```
agent_loop(goal, member_id, max_steps=20, timeout=300_seconds):
  
  start_time = now()
  steps_taken = 0
  consecutive_errors = 0
  events = []
  
  while steps_taken < max_steps:
    
    // PHASE 1: OBSERVE
    current_state = observe_page()
    observation = extract_fields(current_state)  // filtered, not full tree
    events.append({type: "observe", state: observation})
    
    // PHASE 2: DECIDE
    claude_response = call_claude(
      goal: goal,
      member_id: member_id,
      current_state: observation,
      last_action_result: last_result
    )
    action = parse_response(claude_response)  // {action_type, target_description, value}
    events.append({type: "decide", action: action})
    
    // PHASE 3: ACT
    try:
      element = resolve_target(action.target_description)  // multi-signal resolver
      result = perform_action(element, action)  // click, type, navigate
      events.append({type: "act", result: result})
    except TargetNotFound:
      consecutive_errors += 1
      if consecutive_errors >= 3:
        escalate_to_human("Selector not found 3x")
        return ESCALATED
      continue  // try next iteration with different strategy
    
    // PHASE 4: CHECKPOINT
    try:
      checkpoint_passed = verify_checkpoint(action):
        check_text_appeared? ✓
        check_dom_changed? ✓
        check_url_changed? ✓
      
      if checkpoint_passed:
        consecutive_errors = 0
        last_result = "success"
      else:
        consecutive_errors += 1
        last_result = "checkpoint_failed"
    
    except Timeout:
      log_warning("Action timed out")
      retry_once()  // wait 1 sec, try again
      if still_timeout:
        escalate_to_human("Persistent timeout")
        return ESCALATED
    
    // PHASE 5: HANDLE RESULT
    if goal_achieved(observation):
      extract_outputs = extract_data(observation)
      return SUCCESS, extract_outputs, events
    
    if consecutive_errors >= 3:
      escalate_to_human("Stuck: same error 3x")
      return ESCALATED
    
    // PHASE 6: STOP CONDITIONS
    if elapsed_time > timeout:
      escalate_to_human("Time limit exceeded")
      return ESCALATED
    
    steps_taken += 1
    
    // PHASE 7: RECORD
    events.append({type: "checkpoint", passed: checkpoint_passed})
  
  // Max steps reached
  escalate_to_human("Max steps exceeded")
  return ESCALATED, events
```

---

## Tomorrow's Session Plan

**Agenda:**
1. ✅ Agent loop structure (DONE)
2. ✅ Mock app architecture (DONE)
3. **Set up GitHub repository** (NEW)
4. **Artifact recording flow** (thinking)
5. **Replay engine logic** (thinking)
6. **Ready to code!**

---

