from replay_engine import substitute_params


def test_placeholder_is_substituted():
    assert substitute_params("{member_id}", {"member_id": "67890"}) == "67890"


def test_placeholder_inside_text():
    out = substitute_params("Check balance for member {member_id}", {"member_id": "67890"})
    assert out == "Check balance for member 67890"


def test_text_without_placeholder_unchanged():
    assert substitute_params("Check Balance", {"member_id": "67890"}) == "Check Balance"


def test_non_string_values_pass_through():
    assert substitute_params(None, {"member_id": "67890"}) is None
    assert substitute_params(5, {"member_id": "67890"}) == 5
