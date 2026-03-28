import pytest
import os
import json
import tempfile
from workflows.learning.knowledge_injector import enrich_instruction_with_learnings

def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

def test_empty_files():
    res = enrich_instruction_with_learnings("AgentA", "Do X", db_path="dummy_xx1.json", override_path="dummy_xx2.json")
    assert res == "Do X"

def test_corrupted_json():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
    with open(db_path, "w") as f:
        f.write("NOT JSON")
        
    res = enrich_instruction_with_learnings("AgentA", "Do X", db_path=db_path, override_path="x")
    assert res == "Do X"
    os.remove(db_path)

def test_agent_filtering():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
        
    rules = [
        {"target_agent": "AgentA", "rule": "Rule A", "confidence": 0.90},
        {"target_agent": "AgentB", "rule": "Rule B", "confidence": 0.90}
    ]
    write_json(db_path, rules)
    
    res = enrich_instruction_with_learnings("AgentA", "Do X", db_path=db_path)
    assert "Rule A" in res
    assert "Rule B" not in res
    
    os.remove(db_path)

def test_confidence_threshold():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
        
    rules = [
        {"target_agent": "AgentA", "rule": "Good Rule", "confidence": 0.80},
        {"target_agent": "AgentA", "rule": "Bad Rule", "confidence": 0.70}
    ]
    write_json(db_path, rules)
    
    res = enrich_instruction_with_learnings("AgentA", "Do X", db_path=db_path)
    assert "Good Rule" in res
    assert "Bad Rule" not in res
    
    os.remove(db_path)

def test_override_priority():
    with tempfile.NamedTemporaryFile(delete=False) as tmp1, tempfile.NamedTemporaryFile(delete=False) as tmp2:
        db_path = tmp1.name
        ov_path = tmp2.name
        
    db_rules = [
        {"target_agent": "AgentA", "rule": "Test Rule", "confidence": 0.80}
    ]
    ov_rules = [
        {"target_agent": "AgentA", "rule": "Test Rule", "confidence": 0.99}
    ]
    
    write_json(db_path, db_rules)
    write_json(ov_path, ov_rules)
    
    res = enrich_instruction_with_learnings("AgentA", "Do X", db_path=db_path, override_path=ov_path)
    assert "(Confidence: 0.99)" in res
    assert "(Confidence: 0.8)" not in res
    
    os.remove(db_path)
    os.remove(ov_path)

def test_injection_format():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
        
    rules = [{"target_agent": "AgentA", "rule": "Always wash hands", "confidence": 0.95}]
    write_json(db_path, rules)
    
    res = enrich_instruction_with_learnings("AgentA", "Cook food", db_path=db_path)
    
    assert res.startswith("Cook food\\n\\n---\\n\\n⚠️ SYSTEM MEMORY (HIGH CONFIDENCE RULES)")
    assert "1. Always wash hands (Confidence: 0.95)" in res
    
    os.remove(db_path)

def test_max_rules():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
        
    rules = [
        {"target_agent": "AgentA", "rule": "Rule 1", "confidence": 0.91},
        {"target_agent": "AgentA", "rule": "Rule 2", "confidence": 0.95},
        {"target_agent": "AgentA", "rule": "Rule 3", "confidence": 0.80}
    ]
    write_json(db_path, rules)
    
    res = enrich_instruction_with_learnings("AgentA", "Do", db_path=db_path, override_path="dummy", max_rules=2)
    assert "Rule 2" in res
    assert "Rule 1" in res
    assert "Rule 3" not in res
    
    os.remove(db_path)
