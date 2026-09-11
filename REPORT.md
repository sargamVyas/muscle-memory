# muscle-memory — Design Report

**Task:** Build a system where an LLM discovers how to complete a goal on a hostile UI, records the successful path as a typed artifact, and replays that artifact deterministically with no LLM in the loop. Add human escalation, safety guardrails, and observability.

**What I built:** A Flask mock of a legacy banking UI, a 7-phase LLM-driven discovery loop (Claude + Playwright), an artifact recorder, a deterministic replay engine, code-enforced guardrails, and an operator escalation path. Every claim below has an evidence file in `evidence/`.

---

## 1. The core split, and where the LLM cost goes away

```
Discovery   → Playwright + Claude   (live browser, LLM decides each step)
Recorder    → no Playwright, no LLM (pure JSON → JSON transform)
Replay      → Playwright, no LLM    (live browser, fixed steps)
```

Discovery ran once on member `12345` and produced a 5-step artifact: type member ID → click Search → extract name → click Check Balance → extract balance. Replay then executed that artifact against member `67890` — an input the LLM never saw — and returned `{'member_name': 'Jane Smith', 'balance': '2500.0'}` with zero API calls (`replay_run_67890_*.json`). Against `99999`, which doesn't exist, replay stopped at step 3 with `reason: business_outcome / member_not_found` rather than a confusing technical failure (`replay_run_99999_*.json`).

The replay engine imports the exact same `act_type` / `act_click` / `act_extract` / `checkpoint` functions discovery used. This wasn't just code reuse — it's the guarantee that a step verified during discovery is executed identically at replay.

## 2. Design decisions that mattered

**Filtered observation, not screenshots or the full DOM.** Claude sees form fields (with current values), visible text, interactive elements, and a list of what's already been collected. Fewer tokens, easier to redact, and the "already collected" line turned out to be load-bearing: without it, Claude has no memory across steps and will re-extract the same field forever.

**Human-readable targets + a multi-signal resolver, re-run at replay.** The artifact says `"target": "Check Balance"`, not a CSS path. `find_element` tries, in order: placeholder text → button text → accessibility attributes → CSS selector → visible-text match. Replay calls the same resolver, so a class-name change on the hostile page doesn't break the artifact. The artifact records which strategy won per step (`strategy_used`), which is how I know only two of the five strategies were ever needed on this mock (see §5).

**Checkpoints are per action type, not one rule.** `type` is verified by reading the field back; `click` by URL change; `extract` by the value being present. My first version required a URL change for every action, which made every `type` step "fail" by design and burn the retry budget — it worked on a one-field form and would have broken on the first two-field form. This is the bug I'm most glad I caught before building replay on top of it.

**Goal completion is tied to captured data, not page text.** `should_stop` originally fired when the word "balance" appeared anywhere in the HTML — which happened *before* Claude got a turn to extract it. Now it requires `extracted_data` to contain the outputs the goal asks for. The loop can't declare victory on data it hasn't actually captured.

**Guardrails are enforced in code on both paths.** `BLOCKED_ACTION_KEYWORDS` (withdraw, transfer, delete…) and `ALLOWED_DOMAINS` live in `config.py`. `check_guardrails` runs inside `act_on_page` (discovery) and inside the replay step loop, so a hand-edited artifact can't sneak a Withdraw past either. The prompt also tells Claude what's blocked. Evidence for both layers: Claude refused a withdraw goal at step 1 without touching the page (`discovery_run_20260910_181015.json`); a replay of an artifact with a Withdraw step baked in stopped with `guardrail_blocked` (`artifact_withdraw_test.json` + its replay run).

**Redaction is one policy applied in three places.** `REDACTION_LIST` governs form-field values, visible page text, and the "already collected" summary. The balance never enters Claude's context — the observation shows `Balance: [REDACTED]`, and the `extract` action reads the raw page. The LLM orchestrates extraction of a value it never sees. Getting here required two fixes (§4).

**Escalation keeps the browser open.** On escalation the loop saves an event checkpoint, screenshots the page, and blocks on operator input. `resume` re-observes from whatever the page looks like now; `abort` exits cleanly. With `HEADLESS=False` the operator can act in the browser during the pause. Both the DECIDE path (LLM refuses) and the HANDLE path (retries exhausted) route through it (`discovery_run_20260910_191815.json`, `discovery_run_20260910_193318.json`).

## 3. Artifact schema

```json
{
  "metadata":  { "id", "version", "goal", "status", "created_at", "created_by" },
  "contract":  { "inputs": { "member_id": {...} }, "outputs": { "member_name": {...}, "balance": {...} } },
  "steps":     [ { "step_id", "action", "target", "value": "{member_id}", "strategy_used", "checkpoint", "output_key" } ],
  "error_handling": { "member_not_found": {...}, "element_not_found": {...}, "timeout": {...} }
}
```

The recorder keeps only steps where both the act and the checkpoint succeeded, so retries and failed attempts never make it into the artifact. `member_not_found` in `error_handling` is verified (the 99999 replay); `element_not_found` and `timeout` are authored from design intent and not yet exercised.

## 4. What broke, and what it taught me

| Bug | Cause | Fix |
|---|---|---|
| Every `type` step "failed" checkpoint | One URL-change rule for all actions | Per-action-type verification |
| Hidden input matched every click target | `'' in "check balance"` is `True` — empty placeholder is a substring of anything | Guard the substring fallback on non-empty |
| Name extraction silently failed on one page | `results.html` said `Name:`, `action.html` said `Member:` | Consistent labels; the regex was fine |
| Replay failed at step 1 | `{member_id}` substituted for the action but not for the checkpoint's expected value | Substitute once, up front |
| Claude clicked Search on an empty field | Redaction turned `Member ID Search` into `Member ID [REDACTED]` — Claude read that as a pre-filled field | Require a separator + word boundaries; only mask real values |
| Claude escalated instead of extracting | Saw `Balance: [REDACTED]`, reasoned it couldn't extract a placeholder | Tell it redacted values are present and extractable |

The last two are the ones I'd flag to anyone building this: **redaction that changes what a page looks like changes what the agent does.** A hidden value has to stay recognizably a value, and the agent has to know the difference between "hidden from you" and "not there."

The replay bug was caught by the checkpoint, not by me — the field read back `67890`, the expected value was the literal `{member_id}`, mismatch, fail. That's the checkpoint doing its job across the artifact/replay boundary.

## 5. Known limitations — honest version

- **Only the login page is truly hostile** (nested tables, randomized classes). Results and action pages are clean HTML. Consequence: every element resolved via placeholder or button text; the accessibility, CSS, and text-match strategies exist but were never needed. The resolver is designed for the hard case; this mock didn't force it.
- **Guardrails match on labels.** A UI that labels the withdraw button "Proceed" evades the keyword list. The stronger version classifies by *effect* — e.g. a POST to a state-changing endpoint — not by button text.
- **Resolver strategy 3 walks every DOM node** (`query_selector_all('*')`) and can match an outer container that merely contains the keyword. Never triggered here; would need scoping on a large page.
- **Goal parsing is substring matching** (`"check balance" in goal`). A differently-phrased goal wouldn't trigger completion. The right fix is driving completion from the contract's required outputs, not the goal text.
- **Single-input contract; the recorder is told which literal to parameterize.** Auto-detecting parameters from the run is possible but I chose explicit over clever.
- **Extraction is regex over `label: value` text.** Works for this layout; wouldn't for a data grid without a label adjacent to the value.
- **Not tested:** iframes/framesets, session expiry, timeouts, a UI that changes between discovery and replay.

## 6. Generalization to the real environment (§3.7)

The artifact is per-task by design; the *system* is what's reusable. A new tenant, or a "withdraw" flow instead of "check balance," is a new discovery run through the same loop producing a new artifact — no code changes. Tenant variants would be separate artifacts sharing an `id` with different `version`s.

Heterogeneous surfaces plug into two seams. The resolver is an ordered list of strategies, so screenshot-plus-coordinates becomes strategy 6 for pages with no usable DOM. The `act_*` / `checkpoint` functions take a `page` object, so a desktop or OS-level surface is a different backend implementing that same small interface. Nothing in the loop, recorder, or replay engine knows it's talking to a browser.

Drift is detected, not prevented: if the UI changes and a step's checkpoint fails at replay, the engine returns `step_failed` and stops. That failure is the signal to re-run discovery and record a new version.

## 7. What I'd do next, in order

1. Make the action page use `<div>`s instead of `<button>`s so the text-match fallback is exercised, not just implemented.
2. Drive `should_stop` from the contract's required outputs instead of goal text.
3. Effect-based guardrails (inspect the form action / HTTP method, not the label).
4. Screenshot-on-failure and structured logs, separate from the event JSON.
5. Screenshot + coordinates as a resolver strategy, and one test against an iframe.

---

**Evidence index** (`evidence/`): `discovery_run_20260911_173107.json` — happy path with redaction on · `artifact.json` — 5-step artifact with `strategy_used` · `replay_run_67890_*` — unseen input, no LLM · `replay_run_99999_*` — business outcome · `artifact_withdraw_test.json` + replay — code-level guardrail · `discovery_run_20260910_181015.json` — prompt-level refusal · `discovery_run_20260910_191815.json` — escalation resume then abort · `discovery_run_20260910_193318.json` — escalation after retries exhausted · `step_*.png`, `escalation_*.png` — per-step and pause screenshots.
