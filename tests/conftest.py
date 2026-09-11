"""
Test setup: put src/ on the import path (modules use flat imports like
`from config import ...`) and make sure phases.py can build its Anthropic
client at import time — no test ever calls the API, but the client is
constructed on import and needs a key present.
"""
import os
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")
