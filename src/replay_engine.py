"""
Deterministic replay engine — executes a recorded artifact without any LLM.
Reuses the same act_*/checkpoint functions discovery already verified, so
replay behaves identically to how the step worked during discovery.

Usage:
    python src/replay_engine.py <artifact_path> <member_id>

Example:
    python src/replay_engine.py evidence/artifact.json 67890
"""

import json
import sys
import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

from phases import act_type, act_click, act_navigate, act_extract, checkpoint
from config import EVIDENCE_DIR

from phases import act_type, act_click, act_navigate, act_extract, checkpoint, check_guardrails


def substitute_params(value, params: dict):
    """Replace {param_name} placeholders with actual values."""
    if not isinstance(value, str):
        return value
    for key, val in params.items():
        value = value.replace(f"{{{key}}}", str(val))
    return value


def detect_business_outcome(page):
    """
    Check whether we've landed on a known non-error, non-success page
    (e.g. 'member not found'). Distinct from a technical step failure —
    this is an expected outcome the caller should be told about plainly,
    not something to retry or escalate.
    """
    try:
        content = page.content().lower()
        if "not found" in content:
            return {"outcome": "member_not_found", "message": "Member not found"}
    except Exception:
        pass
    return None


def replay_artifact(artifact_path: str, params: dict, start_url: str = "http://localhost:8000/login") -> dict:
    """
    Load an artifact and execute its steps deterministically. No LLM calls —
    every action here uses the exact same act_*/checkpoint functions that
    verified this path during discovery.
    """
    artifact = json.loads(Path(artifact_path).read_text())
    steps = artifact["steps"]

    outputs = {}
    steps_log = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(start_url)

        for step in steps:
            action_type = step["action"]
            target = substitute_params(step.get("target", ""), params)
            value = substitute_params(step.get("value", ""), params)
            previous_url = page.url

            # Check before each step — catches the case where the previous
            # step's click landed us on error.html instead of the expected page.
            business_outcome = detect_business_outcome(page)

            if business_outcome:
                browser.close()
                return {
                    "success": False,
                    "outputs": outputs,
                    "reason": "business_outcome",
                    "details": business_outcome,
                    "steps_executed": steps_log,
                }

            allowed, reason = check_guardrails(action_type, target, step.get("url", ""))
            if not allowed:
                browser.close()
                return {
                    "success": False,
                    "outputs": outputs,
                    "reason": "guardrail_blocked",
                    "details": {"step_id": step["step_id"], "reason": reason},
                    "steps_executed": steps_log,
                }

            if action_type == "type":
                result = act_type(page, target, value)                 # <-- no longer substitutes inline
            elif action_type == "click":
                result = act_click(page, target)
            elif action_type == "navigate":
                result = act_navigate(page, substitute_params(step.get("url", ""), params))
            elif action_type == "extract":
                result = act_extract(page, target)
                if result.get("success"):
                    outputs[step["output_key"]] = result.get("extracted_value")
            else:
                result = {"success": False, "result": f"Unknown action type: {action_type}"}

            fake_decision = {"action_type": action_type, "target": target, "value": value}   # <-- substituted value
            checkpoint_result = checkpoint(page, previous_url, fake_decision)

            steps_log.append({
                "step_id": step["step_id"],
                "action": action_type,
                "act_result": result,
                "checkpoint_result": checkpoint_result,
            })

            if not result.get("success") or not checkpoint_result.get("success"):
                # No LLM here to retry or reroute — a technical failure at replay
                # time means the artifact no longer matches the live UI. Stop
                # and surface it rather than guess.
                browser.close()
                return {
                    "success": False,
                    "outputs": outputs,
                    "reason": "step_failed",
                    "details": {
                        "step_id": step["step_id"],
                        "action": action_type,
                        "act_result": result,
                        "checkpoint_result": checkpoint_result,
                    },
                    "steps_executed": steps_log,
                }

        browser.close()

    return {
        "success": True,
        "outputs": outputs,
        "reason": "goal_achieved",
        "steps_executed": steps_log,
    }


def save_replay_evidence(result: dict, member_id: str) -> str:
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filepath = f"{EVIDENCE_DIR}/replay_run_{member_id}_{timestamp}.json"
    Path(filepath).write_text(json.dumps(result, indent=2))
    return filepath


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/replay_engine.py <artifact_path> <member_id>")
        sys.exit(1)

    artifact_path = sys.argv[1]
    member_id = sys.argv[2]

    print(f"Replaying artifact: {artifact_path}")
    print(f"Parameters: member_id={member_id}\n")

    result = replay_artifact(artifact_path, {"member_id": member_id})
    evidence_path = save_replay_evidence(result, member_id)

    print("=" * 60)
    print("REPLAY FINISHED")
    print("=" * 60)
    print(f"Success: {result['success']}")
    print(f"Reason: {result['reason']}")
    print(f"Outputs: {result['outputs']}")
    print(f"Evidence saved to: {evidence_path}")