import pytest
import json
from workflows.orchestration.pm_agent import (
    generate_execution_plan, 
    _validate_plan, 
    normalize_plan,
    AVAILABLE_AGENTS
)

class MockLLM:
    def __init__(self, response):
        self.response = response
        
    def complete(self, prompt, **kwargs):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

def test_tool_usage():
    # Test Case 1 — Tool Usage
    # Input: Read README.md and fetch https://api.github.com to write a script
    valid_json = """
    {
      "execution_plan": [
        {
          "step_order": 1,
          "agent": "Feature_Coder",
          "instruction": "Write a script based on context",
          "file_path": "README.md",
          "url": "https://api.github.com"
        }
      ]
    }
    """
    llm = MockLLM(valid_json)
    plan = generate_execution_plan("Read README.md and fetch https://api.github.com to write a script", llm)
    
    assert "execution_plan" in plan
    step = plan["execution_plan"][0]
    assert step["file_path"] == "README.md"
    assert step["url"] == "https://api.github.com"

def test_no_tool():
    # Test Case 2 — No Tool
    # Input: Write a simple hello world python script
    valid_json = """
    {
      "execution_plan": [
        {
          "step_order": 1,
          "agent": "Feature_Coder",
          "instruction": "Write a simple hello world script in Python"
        }
      ]
    }
    """
    llm = MockLLM(valid_json)
    plan = generate_execution_plan("Write a simple hello world python script", llm)
    
    assert len(plan["execution_plan"]) == 1
    step = plan["execution_plan"][0]
    assert step["agent"] == "Feature_Coder"
    assert "url" not in step
    assert "file_path" not in step

def test_multi_step():
    # Test Case 3 — Multi-Step
    # Input: Build a robust API client with validation
    valid_json = """
    {
      "execution_plan": [
        {
          "step_order": 1,
          "agent": "Feature_Coder",
          "instruction": "Build a robust API client with validation"
        },
        {
          "step_order": 2,
          "agent": "Reviewer",
          "instruction": "Review the API client for robustness and validation logic"
        }
      ]
    }
    """
    llm = MockLLM(valid_json)
    plan = generate_execution_plan("Build a robust API client with validation", llm)
    
    assert len(plan["execution_plan"]) == 2
    agents = [step["agent"] for step in plan["execution_plan"]]
    
    assert "Feature_Coder" in agents
    assert "Reviewer" in agents
    assert "AutoFix_Medic" not in agents

def test_autofix_medic_rejected():
    invalid_json = """
    {
      "execution_plan": [
        {
          "step_order": 1,
          "agent": "AutoFix_Medic",
          "instruction": "Fix something"
        }
      ]
    }
    """
    llm = MockLLM(invalid_json)
    plan = generate_execution_plan("Trigger autofix", llm)
    # Should fallback because AutoFix_Medic is strictly rejected
    assert plan["execution_plan"][0]["agent"] == "Feature_Coder"
    assert plan["execution_plan"][0]["instruction"] == "Analyze task and gather context"

def test_malformed_json_fallback():
    llm = MockLLM("THIS IS NOT JSON")
    plan = generate_execution_plan("Do something", llm)
    assert plan["execution_plan"][0]["agent"] == "Feature_Coder"
    assert plan["execution_plan"][0]["instruction"] == "Analyze task and gather context"

def test_normalization_sorting_and_reindexing():
    unordered_json = """
    {
      "execution_plan": [
        {
          "step_order": 99,
          "agent": "Reviewer",
          "instruction": "Code it"
        },
        {
          "step_order": -5,
          "agent": "Feature_Coder",
          "instruction": "Read first",
          "file_path": "README.md"
        }
      ]
    }
    """
    llm = MockLLM(unordered_json)
    plan = generate_execution_plan("Do something", llm)
    
    assert len(plan["execution_plan"]) == 2
    
    # -5 comes first, so it becomes step 1. 'Feature_Coder'
    assert plan["execution_plan"][0]["step_order"] == 1
    assert plan["execution_plan"][0]["agent"] == "Feature_Coder"
    assert plan["execution_plan"][0]["file_path"] == "README.md"
    
    # 99 comes second, so it becomes step 2. 'Reviewer'
    assert plan["execution_plan"][1]["step_order"] == 2
    assert plan["execution_plan"][1]["agent"] == "Reviewer"

def test_empty_execution_plan_fallback():
    empty_plan_json = """
    {
      "execution_plan": []
    }
    """
    llm = MockLLM(empty_plan_json)
    plan = generate_execution_plan("Do something", llm)
    assert plan["execution_plan"][0]["agent"] == "Feature_Coder"

def test_extra_keys_discarded_by_normalization():
    extra_keys_json = """
    {
      "some_extra_root_key": "should_be_removed",
      "execution_plan": [
        {
          "step_order": 1,
          "agent": "Feature_Coder",
          "instruction": " Read files ",
          "extra_step_key": "will_be_gone",
          "url": "   https://example.com   "
        }
      ]
    }
    """
    llm = MockLLM(extra_keys_json)
    plan = generate_execution_plan("Do something", llm)
    
    # Root key should be gone
    assert "some_extra_root_key" not in plan
    
    # Step key should be gone
    step = plan["execution_plan"][0]
    assert "extra_step_key" not in step
    
    # Instruction and url should be stripped
    assert step["instruction"] == "Read files"
    assert step["url"] == "https://example.com"

def test_string_int_coercion_rejected():
    string_int_json = """
    {
      "execution_plan": [
        {
          "step_order": "1",
          "agent": "Feature_Coder",
          "instruction": "Read files"
        }
      ]
    }
    """
    llm = MockLLM(string_int_json)
    plan = generate_execution_plan("Do something", llm)
    assert plan["execution_plan"][0]["agent"] == "Feature_Coder"
    assert plan["execution_plan"][0]["instruction"] == "Analyze task and gather context"

def test_pm_step_limit():
    # Test 1 — PM Step Limit (Mock PM output with 6 steps)
    steps = []
    for i in range(1, 7):
        steps.append({
            "step_order": i,
            "agent": "Feature_Coder",
            "instruction": f"Instruction {i}"
        })
    json_str = '{"execution_plan": ' + json.dumps(steps) + '}'
    llm = MockLLM(json_str)
    plan = generate_execution_plan("Trigger 6 steps", llm)
    
    # Should be limited to 5 steps
    assert len(plan["execution_plan"]) == 5
    assert plan["execution_plan"][-1]["step_order"] == 5

def test_pm_instruction_limit():
    # Test 2 — PM Instruction Limit (Mock instruction 5000 chars)
    long_instruction = "A" * 5000
    json_str = '{"execution_plan": [{"step_order": 1, "agent": "Feature_Coder", "instruction": "' + long_instruction + '"}]}'
    llm = MockLLM(json_str)
    plan = generate_execution_plan("Long instruction", llm)
    
    assert len(plan["execution_plan"]) == 1
    # Should be truncated to 2000 chars
    assert len(plan["execution_plan"][0]["instruction"]) == 2000
    assert plan["execution_plan"][0]["instruction"] == "A" * 2000
