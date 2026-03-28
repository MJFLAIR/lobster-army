import pytest
import os
import tempfile
from workflows.tools.read_file import read_file
from workflows.orchestration.task_router import execute_plan
from unittest.mock import MagicMock

def test_read_file_success():
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), delete=False, suffix=".py") as tmp:
        tmp.write(b"def test(): pass")
        path = os.path.basename(tmp.name)
        
    res = read_file(path)
    assert res["status"] == "success"
    assert "def test(): pass" in res["content"]
    
    os.remove(tmp.name)

def test_invalid_path_traversal():
    res = read_file("../secret.txt")
    assert res["status"] == "failed"
    assert "traversal" in res["error"]

def test_absolute_path():
    res = read_file("/etc/passwd")
    assert res["status"] == "failed"
    assert "absolute" in res["error"]

def test_binary_file():
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), delete=False) as tmp:
        tmp.write(bytes([255, 254, 0, 0]))
        path = os.path.basename(tmp.name)
        
    res = read_file(path)
    assert res["status"] == "failed"
    assert "binary" in res["error"]
    
    os.remove(tmp.name)

def test_file_not_found():
    res = read_file("does_not_exist_xyz.txt")
    assert res["status"] == "failed"
    assert "not found" in res["error"]

def test_context_injection_in_router():
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), delete=False, suffix=".py") as tmp:
        tmp.write(b"real code content")
        path = os.path.basename(tmp.name)
        
    handler_mock = MagicMock(return_value={"status": "success"})
    registry = {"TEST_AGENT": handler_mock}
    
    plan = {
        "execution_plan": [
            {
                "step_order": 1,
                "assigned_agent": "TEST_AGENT",
                "instruction": "Fix something",
                "file_path": path
            }
        ]
    }
    
    trace = execute_plan(plan, registry)
    
    # Verify instruction contains FILE CONTEXT
    args, kwargs = handler_mock.call_args
    passed_instruction = args[0]
    
    assert "### FILE CONTEXT ###" in passed_instruction
    assert "real code content" in passed_instruction
    assert "Fix something" in passed_instruction
    
    os.remove(tmp.name)

def test_tool_failure_fallback_in_router():
    handler_mock = MagicMock(return_value={"status": "success"})
    registry = {"TEST_AGENT": handler_mock}
    
    plan = {
        "execution_plan": [
            {
                "step_order": 1,
                "assigned_agent": "TEST_AGENT",
                "instruction": "Fix something",
                "file_path": "non-existent-local-file.py"
            }
        ]
    }
    
    trace = execute_plan(plan, registry)
    
    # Verify instruction DOES NOT contain FILE CONTEXT but still runs organically
    args, kwargs = handler_mock.call_args
    passed_instruction = args[0]
    
    assert "### FILE CONTEXT ###" not in passed_instruction
    assert "Fix something" in passed_instruction

def test_large_context_truncation_in_router():
    with tempfile.NamedTemporaryFile(dir=os.getcwd(), delete=False, suffix=".py") as tmp:
        large_content = "B" * 8500
        tmp.write(large_content.encode("utf-8"))
        path = os.path.basename(tmp.name)
        
    handler_mock = MagicMock(return_value={"status": "success"})
    registry = {"TEST_AGENT": handler_mock}
    
    plan = {
        "execution_plan": [
            {
                "step_order": 1,
                "assigned_agent": "TEST_AGENT",
                "instruction": "Fix something",
                "file_path": path
            }
        ]
    }
    
    trace = execute_plan(plan, registry)
    
    args, kwargs = handler_mock.call_args
    passed_instruction = args[0]
    
    assert "...[TRUNCATED]" in passed_instruction
    assert passed_instruction.count("B") == 8000
    
    os.remove(tmp.name)
