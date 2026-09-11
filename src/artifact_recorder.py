"""
Converts a discovery_run_*.json (produced by agent.py) into a typed,
parameterized artifact that a replay engine can execute without an LLM.

Usage:
    python src/artifact_recorder.py <discovery_run_path> <member_id_used> [artifact_id] [output_path]

Example:
    python src/artifact_recorder.py evidence/discovery_run_20260909_194439.json 12345
"""

import json
import sys
import datetime
from pathlib import Path

ACTIONABLE_TYPES = {"type", "click", "navigate", "extract"}


def _group_events_into_steps(events: list) -> list:
    """
    Split the flat events list back into per-step groups. Each group starts
    at an 'observe' event and runs until the next 'observe' (or end of list).
    This naturally isolates retried attempts into their own groups, so a
    failed attempt never gets mixed into a successful one.
    """
    groups = []
    current = []
    for event in events:
        if event["type"] == "observe" and current:
            groups.append(current)
            current = []
        current.append(event)
    if current:
        groups.append(current)
    return groups


def _extract_phase(group: list, phase: str) -> dict:
    for event in group:
        if event["type"] == phase:
            return event["data"]
    return {}


def _map_output_key(target_description: str) -> str:
    """Match the same keying convention agent.py already uses for extracted_data."""
    key = target_description.lower()
    if "balance" in key:
        return "balance"
    if "name" in key:
        return "member_name"
    return key.replace(" ", "_")  # fallback so unknown extract targets aren't dropped


def build_artifact(
    discovery_run_path: str,
    member_id_used: str,
    goal: str,
    artifact_id: str = "check_member_balance",
    version: str = "1.0.0",
) -> dict:
    """
    Convert one successful discovery run into a typed, replayable artifact.
    Only steps where BOTH the act and checkpoint succeeded are kept.
    """
    run_data = json.loads(Path(discovery_run_path).read_text())
    steps_out = []
    outputs_seen = {}

    for group in _group_events_into_steps(run_data["events"]):
        decide = _extract_phase(group, "decide")
        act = _extract_phase(group, "act")
        checkpoint = _extract_phase(group, "checkpoint")

        action_type = decide.get("action_type")
        if action_type not in ACTIONABLE_TYPES:
            continue  # skips escalate_to_human and malformed decisions

        if not act.get("success") or not checkpoint.get("success"):
            continue  # discovery noise — failed/retried attempt, not the path

        step = {
            "step_id": len(steps_out) + 1,
            "action": action_type,
            "target": decide.get("target", ""),
            "strategy_used": act.get("strategy_used"),
            "checkpoint": checkpoint.get("reason", ""),
        }

        if action_type == "type":
            raw_value = decide.get("value", "")
            step["value"] = "{member_id}" if raw_value == member_id_used else raw_value

        if action_type == "extract":
            output_key = _map_output_key(decide.get("target", ""))
            step["output_key"] = output_key
            outputs_seen[output_key] = "string"

        steps_out.append(step)

    return {
        "metadata": {
            "id": artifact_id,
            "version": version,
            "goal": goal,
            "status": "draft",
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
            "created_by": Path(discovery_run_path).name,
        },
        "contract": {
            "inputs": {"member_id": {"type": "string", "required": True}},
            "outputs": {key: {"type": dtype} for key, dtype in outputs_seen.items()},
        },
        "steps": steps_out,
        # Authored from design intent + error.html's known behavior — this run
        # never hit a failure path, so nothing here is from observed events.
        "error_handling": {
            "member_not_found": {
                "trigger": "Page shows 'Member {id} not found'",
                "response": "return_business_outcome",
            },
            "element_not_found": {
                "trigger": "Resolver exhausts all strategies for a target",
                "response": "escalate_to_human",
            },
            "timeout": {
                "trigger": "Action or page load exceeds expected timeout",
                "response": "escalate_to_human",
            },
        },
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python src/artifact_recorder.py <discovery_run_path> <member_id_used> [artifact_id] [output_path]")
        sys.exit(1)

    discovery_run_path = sys.argv[1]
    member_id_used = sys.argv[2]
    artifact_id = sys.argv[3] if len(sys.argv) > 3 else "check_member_balance"
    output_path = sys.argv[4] if len(sys.argv) > 4 else "evidence/artifact.json"

    goal = "Check balance and get member name for member {member_id}"

    artifact = build_artifact(
        discovery_run_path=discovery_run_path,
        member_id_used=member_id_used,
        goal=goal,
        artifact_id=artifact_id,
    )

    Path(output_path).write_text(json.dumps(artifact, indent=2))
    print(f"✅ Artifact written to {output_path}")
    print(f"   {len(artifact['steps'])} steps, outputs: {list(artifact['contract']['outputs'].keys())}")