import sys
import os
import json
import logging
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from workflows.storage.db import DB
from workflows.models.task import Task
from runtime.task_worker import TaskWorker

logging.basicConfig(level=logging.INFO)

def inject_task(test_case: str, task_type: str, input_text: str, meta_extra: dict = None) -> dict:
    print(f"[REAL_TASK_INJECT_START] test_case={test_case}")
    
    # 1. Prepare Payload
    task_id = int(time.time() * 1000)
    meta = {
        "source": "real_task_injection",
        "test_case": test_case,
        "task_type": task_type,
        "input": input_text
    }
    if meta_extra:
        meta.update(meta_extra)
        
    task_payload = Task(
        task_id=task_id,
        source="real_task_injection",
        requester_id="admin_test",
        description=input_text,
        meta_json=meta
    )
    
    # 2. Enqueue in the real system
    DB.create_task(task_payload)
    
    # 3. Trigger native runtime processing
    worker = TaskWorker()
    try:
        # Expected new return signature from Phase 16.3: result, cost, execution_trace
        result_summary, cost_json, execution_trace = worker.run_task(task_id)
        
        # 4. Sandbox validation (post-run validation rule)
        sandbox_violations = []
        for path in execution_trace.get("sandbox_write_paths", []):
            if "../" in path or path.startswith("/root/") or not path.startswith("sandbox/"):
                sandbox_violations.append(path)
                
        if sandbox_violations:
            execution_trace["final_status"] = "FAILED"
            execution_trace["error"] = f"SANDBOX_VIOLATION: Unsafe paths written: {sandbox_violations}"
            print(f"[REAL_TASK_FAILED] test_case={test_case} task_id={task_id}")
        else:
            if execution_trace.get("final_status") == "SUCCESS":
                print(f"[REAL_TASK_SUCCESS] test_case={test_case} task_id={task_id}")
            else:
                print(f"[REAL_TASK_FAILED] test_case={test_case} task_id={task_id}")
                
        # Final JSON dump
        print("\n[REAL_TASK_TRACE]")
        print(json.dumps(execution_trace, indent=2))
        
        return execution_trace
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[REAL_TASK_FAILED] test_case={test_case} task_id={task_id}")
        print(f"Exception escaped pipeline: {e}")
        return {"error": str(e), "final_status": "FAILED"}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-case", required=True, choices=["fibonacci_success", "review_fail_then_heal", "tool_failure_test"])
    args = parser.parse_args()
    
    if args.test_case == "fibonacci_success":
        inject_task(
            "fibonacci_success", 
            "code_generation", 
            "Write a Python script that calculates the Fibonacci sequence up to 10 terms and save it to sandbox/fib.py"
        )
    elif args.test_case == "review_fail_then_heal":
        inject_task(
            "review_fail_then_heal", 
            "code_generation", 
            "Write fibonacci using recursion AND handle n > 10^6 efficiently AND support negative inputs. Save it to sandbox/fib_broken.py"
        )
    elif args.test_case == "tool_failure_test":
        inject_task(
            "tool_failure_test", 
            "code_generation", 
            "Generate a fibonacci sequence and strictly save it to ../outside.py"
        )
