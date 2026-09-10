# src/config.py

# Fields to redact (sensitive PII)
REDACTION_LIST = [
    'balance',
    'account',
    'card',
    'member_id',
    'password',
    'ssn',
    'pin'
]

# ========== SAFETY GUARDRAILS ==========

# Actions the agent is never allowed to perform, regardless of goal.
# Matched case-insensitively against the click target description.
BLOCKED_ACTION_KEYWORDS = [
    'withdraw',
    'transfer',
    'delete',
    'close account',
    'submit payment',
]

# Only these hosts may be navigated to. Anything else is refused.
ALLOWED_DOMAINS = [
    'localhost:8000',
    '127.0.0.1:8000',
]

# Paths for saving evidence
EVIDENCE_DIR = 'evidence'