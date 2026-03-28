import pytest
from workflows.strategy.auto_fix_context import build_auto_fix_context

def test_build_context_no_file():
    incident = {
        "incident_hash": "123",
        "error": "Something went very wrong here."
    }
    ctx = build_auto_fix_context(incident)
    assert ctx["status"] == "BLOCKED"
    assert ctx["reason"] == "missing_target_file"

def test_build_context_with_file():
    incident = {
        "incident_hash": "123",
        "error": r'Traceback (most recent call last):\n  File "main.py", line 10, in <module>\n    foo()'
    }
    ctx = build_auto_fix_context(incident)
    assert ctx["status"] == "READY"
    assert ctx["target_file"] == "main.py"
    assert ctx["allowed_files"] == ["main.py"]
