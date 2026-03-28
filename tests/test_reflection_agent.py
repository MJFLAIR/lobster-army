import pytest
import os
import json
import tempfile
from unittest.mock import MagicMock
from workflows.learning.reflection_agent import (
    extract_recoveries,
    validate_learning,
    update_knowledge_base,
    process_diff_for_learnings
)

def test_skip_empty_diff():
    diff = {"step_diffs": [{"type": "UNCHANGED"}, {"type": "REGRESSED"}]}
    assert len(extract_recoveries(diff)) == 0
    
    llm = MagicMock()
    built = process_diff_for_learnings(diff, llm, db_path="dummy.json")
    assert built == 0
    llm.complete.assert_not_called()

def test_low_confidence_filtered():
    learning = {
        "target_agent": "Coder",
        "failure_pattern": "syntax error",
        "fix_pattern": "fixed syntax",
        "new_rule": "Write better code without syntax errors",
        "confidence_score": 0.5
    }
    assert not validate_learning(learning)

def test_learning_generated_and_saved():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
        
    diff = {
        "step_diffs": [
            {"step_order": 1, "agent": "Reviewer", "type": "RECOVERED", "from": "failed", "to": "success"}
        ]
    }
    
    valid_json = """
    {
        "target_agent": "Reviewer",
        "failure_pattern": "missed null check",
        "fix_pattern": "added null check",
        "new_rule": "Always check for null before accessing object properties",
        "confidence_score": 0.85
    }
    """
    llm = MagicMock()
    llm.complete.return_value = valid_json
    
    added = process_diff_for_learnings(diff, llm, db_path=db_path)
    assert added == 1
    
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
        
    assert len(db) == 1
    assert db[0]["target_agent"] == "Reviewer"
    assert db[0]["occurrence_count"] == 1
    
    os.remove(db_path)

def test_rule_merge_logic():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        db_path = tmp.name
        
    initial_db = [{
        "target_agent": "Feature_Coder",
        "failure_pattern": "import error",
        "fix_pattern": "added imports",
        "new_rule": "Add imports before usage",
        "confidence_score": 0.80,
        "occurrence_count": 1
    }]
    
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(initial_db, f)
        
    new_learning = {
        "target_agent": "Feature_Coder",
        "failure_pattern": "import error",
        "fix_pattern": "added more imports",
        "new_rule": "Always verify import paths meticulously",
        "confidence_score": 0.80
    }
    
    update_knowledge_base(new_learning, db_path=db_path)
    
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)
        
    assert len(db) == 1
    merged_rule = db[0]
    
    assert merged_rule["occurrence_count"] == 2
    assert merged_rule["confidence_score"] == 0.85
    assert merged_rule["new_rule"] == "Always verify import paths meticulously"
    
    os.remove(db_path)
