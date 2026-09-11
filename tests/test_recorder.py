import json

from artifact_recorder import build_artifact


def _ev(type_, data):
    return {"timestamp": "2026-09-11T00:00:00Z", "type": type_, "data": data}


def _discovery_run():
    """
    A synthetic run with: a successful type, a FAILED click followed by a
    successful retry, a successful extract, and an escalate decision with
    no act. Only the three successful steps should survive.
    """
    obs = _ev("observe", {"url": "http://localhost:8000/login"})
    return {"events": [
        # step 1: type — success
        obs,
        _ev("decide", {"action_type": "type", "target": "Enter Member ID", "value": "12345"}),
        _ev("act", {"action": "type", "success": True, "strategy_used": "placeholder_text"}),
        _ev("checkpoint", {"success": True, "reason": "value_entered"}),
        _ev("handle", {"action": "continue"}),
        _ev("stop", {"should_stop": False}),
        # step 2: click — FAILED (should be dropped)
        obs,
        _ev("decide", {"action_type": "click", "target": "Search"}),
        _ev("act", {"action": "click", "success": False, "element_found": False, "strategy_used": "none"}),
        _ev("checkpoint", {"success": False, "reason": "click_no_effect"}),
        _ev("handle", {"action": "retry"}),
        # step 3: click — retry succeeds
        obs,
        _ev("decide", {"action_type": "click", "target": "Search"}),
        _ev("act", {"action": "click", "success": True, "strategy_used": "button_text"}),
        _ev("checkpoint", {"success": True, "reason": "url_changed"}),
        _ev("handle", {"action": "continue"}),
        _ev("stop", {"should_stop": False}),
        # step 4: extract — success
        obs,
        _ev("decide", {"action_type": "extract", "target": "balance"}),
        _ev("act", {"action": "extract", "success": True, "strategy_used": "regex_pattern", "extracted_value": "1500.0"}),
        _ev("checkpoint", {"success": True, "reason": "value_extracted"}),
        _ev("handle", {"action": "continue"}),
        _ev("stop", {"should_stop": True, "reason": "goal_achieved"}),
        # step 5: escalate — no act, must be ignored
        obs,
        _ev("decide", {"action_type": "escalate_to_human", "reason": "stuck"}),
    ]}


def test_build_artifact_keeps_only_successful_steps(tmp_path):
    run_path = tmp_path / "discovery_run_test.json"
    run_path.write_text(json.dumps(_discovery_run()))

    artifact = build_artifact(str(run_path), member_id_used="12345", goal="Check balance for {member_id}")

    steps = artifact["steps"]
    assert [s["action"] for s in steps] == ["type", "click", "extract"]
    assert [s["step_id"] for s in steps] == [1, 2, 3]


def test_typed_value_is_parameterized(tmp_path):
    run_path = tmp_path / "discovery_run_test.json"
    run_path.write_text(json.dumps(_discovery_run()))

    artifact = build_artifact(str(run_path), member_id_used="12345", goal="g")

    assert artifact["steps"][0]["value"] == "{member_id}"
    assert "12345" not in json.dumps(artifact["steps"])


def test_extract_step_declares_output_and_contract(tmp_path):
    run_path = tmp_path / "discovery_run_test.json"
    run_path.write_text(json.dumps(_discovery_run()))

    artifact = build_artifact(str(run_path), member_id_used="12345", goal="g")

    extract_step = artifact["steps"][2]
    assert extract_step["output_key"] == "balance"
    assert "balance" in artifact["contract"]["outputs"]
    # the extracted value itself must NOT be baked into the artifact
    assert "1500" not in json.dumps(artifact)


def test_strategy_used_is_recorded(tmp_path):
    run_path = tmp_path / "discovery_run_test.json"
    run_path.write_text(json.dumps(_discovery_run()))

    artifact = build_artifact(str(run_path), member_id_used="12345", goal="g")

    assert [s["strategy_used"] for s in artifact["steps"]] == ["placeholder_text", "button_text", "regex_pattern"]
