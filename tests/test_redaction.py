from helpers import redact_text, redact_value


def test_balance_value_is_masked_label_kept():
    out = redact_text("Action Complete Name: John Doe Balance: $1500.0 Back to Login")
    assert "Balance: [REDACTED]" in out
    assert "1500" not in out
    assert "Name: John Doe" in out  # name is not in REDACTION_LIST


def test_member_id_value_is_masked():
    out = redact_text("Member Details Member ID: 12345 Name: John Doe")
    assert "Member ID: [REDACTED]" in out
    assert "12345" not in out


def test_label_without_separator_is_untouched():
    # Regression: an earlier version ate the word "Search" here, which made
    # the agent think the field was pre-filled and click instead of type.
    text = "Member Banking System Member ID Search"
    assert redact_text(text) == text


def test_keyword_inside_another_word_is_untouched():
    # 'pin' must not match inside 'shipping'
    text = "Free shipping: yes"
    assert redact_text(text) == text


def test_redact_value_by_field_name():
    assert redact_value("balance", "1500.0") == "[REDACTED]"
    assert redact_value("member_name", "John Doe") == "John Doe"
