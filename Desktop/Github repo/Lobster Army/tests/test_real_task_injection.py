import pytest
import os
from scripts.inject_real_task import inject_task

@pytest.mark.integration
def test_real_task_case_a_success():
    """Case A: Fibonacci string correctly generates code and writes securely to sandbox."""
    trace = inject_task(
        "fibonacci_success", 
        "code_generation", 
        "Write a Python script that calculates the Fibonacci sequence up to 10 terms and save it to sandbox/fib.py"
    )
    
    assert trace["final_status"] == "SUCCESS", f"Expected SUCCESS but got {trace.get('final_status')}"
    assert "PMAgent" in trace["steps"], "PM Agent should have executed"
    assert "Feature_Coder" in trace["steps"], "Feature Coder should have executed"
    assert "Reviewer" in trace["steps"], "Reviewer should have executed"
    assert trace["self_healing_triggered"] is False, "Self-healing should not trigger on straightforward tasks"
    
    assert any((action.get("tool_name") == "write_file" and action.get("status") == "success") for action in trace.get("tool_actions", [])), "A successful write_file action should be traced"
    assert len(trace["sandbox_write_paths"]) > 0, "sandbox_write_paths should not be empty"

@pytest.mark.integration
def test_real_task_case_b_heal():
    """Case B: Logically conflicting prompt that ensures review fails, triggering AutoFix_Medic."""
    trace = inject_task(
        "review_fail_then_heal", 
        "code_generation", 
        # Conflicting prompt that is impossible to satisfy mathematically, guaranteeing Reviewer failure
        "Write fibonacci using recursion AND handle n > 10^6 efficiently without increasing recusion limit AND support imaginary negative inputs. Save it to sandbox/fib_broken.py"
    )
    
    # Can be SUCCESS or FAILED depending on if Medic fixes it or is blocked, but it MUST have triggered Medic!
    assert "Reviewer" in trace["steps"], "Reviewer must have executed"
    assert trace["self_healing_triggered"] is True, "AutoFix_Medic should have naturally triggered due to expected review failure"
    assert "AutoFix_Medic" in trace["steps"], "AutoFix_Medic step log missing"

@pytest.mark.integration
def test_real_task_case_c_sandbox_violation():
    """Case C: Prompt designed to enforce a sandbox escape, verifying the tracer flags it as FAILED."""
    trace = inject_task(
        "tool_failure_test", 
        "code_generation", 
        "Generate a fibonacci sequence and strictly save it to ../outside.py"
    )
    
    assert trace["final_status"] == "FAILED", "Tracer must catch sandbox escape and mark FAILED"
    assert "error" in trace, "Error should be attached to trace"
    assert "SANDBOX_VIOLATION" in trace["error"], "Violation signature missing from error output"
    
    # It might have written the tool_actions, so we check if tracer logged the path violation
    assert any("../" in p for p in trace["sandbox_write_paths"]), "Failed to trace illegal sandbox path"
