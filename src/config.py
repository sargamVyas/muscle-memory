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

# Paths for saving evidence
EVIDENCE_DIR = 'evidence'