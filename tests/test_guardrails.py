from phases import check_guardrails


def test_withdraw_click_is_blocked():
    allowed, reason = check_guardrails("click", target="Withdraw")
    assert allowed is False
    assert "withdraw" in reason.lower()


def test_blocked_keyword_is_case_insensitive():
    allowed, _ = check_guardrails("click", target="WITHDRAW FUNDS")
    assert allowed is False


def test_check_balance_click_is_allowed():
    allowed, _ = check_guardrails("click", target="Check Balance")
    assert allowed is True


def test_navigate_off_domain_is_blocked():
    allowed, reason = check_guardrails("navigate", url="http://evil.example.com/login")
    assert allowed is False
    assert "allowed domains" in reason


def test_navigate_on_domain_is_allowed():
    allowed, _ = check_guardrails("navigate", url="http://localhost:8000/login")
    assert allowed is True


def test_type_is_not_subject_to_click_keywords():
    # Typing the word "withdraw" into a search box is not a withdrawal.
    allowed, _ = check_guardrails("type", target="Enter Member ID")
    assert allowed is True
