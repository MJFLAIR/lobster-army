import pytest
import time
from workflows.strategy.auto_fix_policy import is_auto_fix_eligible, classify_fix_scope

def dict_mock(**kwargs):
    d = {
        "incident_hash": "hash123",
        "priority_level": "P1",
        "trend": "spiking",
        "confidence": "HIGH",
        "error": "Some error"
    }
    d.update(kwargs)
    return d

def test_auto_fix_eligible():
    incident = dict_mock()
    is_e, reason = is_auto_fix_eligible(incident)
    assert is_e is True
    assert reason == "eligible"

def test_auto_fix_fails_on_p2():
    incident = dict_mock(priority_level="P2")
    is_e, reason = is_auto_fix_eligible(incident)
    assert is_e is False
    assert reason == "not_p1"
    
def test_auto_fix_fails_trend():
    incident = dict_mock(trend="rising")
    is_e, reason = is_auto_fix_eligible(incident)
    assert is_e is False
    assert reason == "trend_not_spiking"

def test_auto_fix_cooldown():
    incident = dict_mock(auto_fix_last_attempt_ts=time.time())
    is_e, reason = is_auto_fix_eligible(incident)
    assert is_e is False
    assert reason == "cooldown_active"
    
def test_classify_scope():
    c1 = {
        "allowed_files": ["a", "b", "c"]
    }
    assert classify_fix_scope(c1) == "wide"
    
    c2 = {
        "allowed_files": ["a"],
        "error_summary": "npm install failed"
    }
    assert classify_fix_scope(c2) == "wide"
    
    c3 = {
        "allowed_files": ["a"],
        "failure_type": "database"
    }
    assert classify_fix_scope(c3) == "wide"
    
    c4 = {
        "allowed_files": ["app.py"],
        "failure_type": "crash",
        "error_summary": "NameError: foo"
    }
    assert classify_fix_scope(c4) == "narrow"
