import os
import shutil
import subprocess
import json
import logging
import sys

from workflows.strategy.auto_fix_orchestrator import run_auto_fix_for_incident

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s", stream=sys.stdout)

class MockLLMConfig:
    def __init__(self, target_files, diff_content):
        self.payload = {
            "status": "PATCH_READY",
            "diff": diff_content,
            "target_files": target_files,
            "summary": "Mock patch",
        }

    def complete(self, prompt, **kwargs):
        class Resp:
            content = json.dumps(self.payload)
        return Resp()

def setup_repo():
    test_dir = "/tmp/lobster_c11_acceptance_test"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@lobster.army"], cwd=test_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test Bot"], cwd=test_dir, check=True)
    
    file1 = "file1.py"
    file2 = "file2.py"
    with open(os.path.join(test_dir, file1), "w") as f:
        f.write('def func1():\\n    return "broken1"\\n')
    with open(os.path.join(test_dir, file2), "w") as f:
        f.write('def func2():\\n    return "broken2"\\n')
        
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=test_dir, check=True, capture_output=True)
    
    return test_dir, file1, file2

def get_repo_state(repo_path):
    branches = subprocess.run(["git", "branch"], cwd=repo_path, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "-s"], cwd=repo_path, capture_output=True, text=True).stdout.strip()
    return f"Branches:\\n{branches}\\nStatus (uncommitted):\\n{status if status else 'clean'}"

def run_scenarios():
    repo_path, file1, file2 = setup_repo()
    
    with open(os.path.join(repo_path, file1), "w") as f:
        f.write('def func1():\\n    return "fixed1"\\n')
    valid_diff = subprocess.run(["git", "diff"], cwd=repo_path, capture_output=True, text=True).stdout
    subprocess.run(["git", "checkout", "--", "."], cwd=repo_path, check=True)
    
    invalid_diff = "--- a/missing.py\\n+++ b/missing.py\\n@@ -1 +1 @@\\n-broken\\n+fixed\\n"

    print("\\n" + "="*50)
    print("SCENARIO 1: The Spam Attack (Cooldown)")
    print("="*50)
    incident_hash = "spam_test_1"
    mock_store = {"incidents": {incident_hash: {"incident_hash": incident_hash}}}
    with open(".incident_store.json", "w") as f: json.dump(mock_store, f)
    incident = {"incident_hash": incident_hash, "priority_level": "P1", "trend": "spiking", "confidence": "HIGH", "error": f"Error in {file1}"}
    
    print("\\n[Run 1]")
    res1 = run_auto_fix_for_incident(incident, None, MockLLMConfig([file1], valid_diff), repo_path)
    subprocess.run(["git", "checkout", "main"], cwd=repo_path, capture_output=True) # Reset to main for next step
    
    print("\\n[Run 2]")
    with open(".incident_store.json", "r") as f:
        data = json.load(f)
    incident_run_2 = incident.copy()
    incident_run_2["auto_fix_last_attempt_ts"] = data["incidents"][incident_hash].get("auto_fix_last_attempt_ts")
    res2 = run_auto_fix_for_incident(incident_run_2, None, MockLLMConfig([file1], valid_diff), repo_path)


    print("\\n" + "="*50)
    print("SCENARIO 2: The LLM Hallucination (Dry-Run)")
    print("="*50)
    incident_hash2 = "hal_test_2"
    mock_store["incidents"][incident_hash2] = {"incident_hash": incident_hash2}
    with open(".incident_store.json", "w") as f: json.dump(mock_store, f)
    incident2 = {"incident_hash": incident_hash2, "priority_level": "P1", "trend": "spiking", "confidence": "HIGH", "error": f"Error in {file1}"}
    
    print("Repo State Before:\\n", get_repo_state(repo_path))
    res3 = run_auto_fix_for_incident(incident2, None, MockLLMConfig([file1], invalid_diff), repo_path)
    print("\\nRepo State After:\\n", get_repo_state(repo_path))


    print("\\n" + "="*50)
    print("SCENARIO 3: The Architecture Rewrite (Scope Lock)")
    print("="*50)
    incident_hash3 = "scope_test_3"
    mock_store["incidents"][incident_hash3] = {"incident_hash": incident_hash3}
    with open(".incident_store.json", "w") as f: json.dump(mock_store, f)
    
    # 3 files trigger wide scope
    incident3 = {"incident_hash": incident_hash3, "priority_level": "P1", "trend": "spiking", "confidence": "HIGH", "error": f"Error in {file1} AND dependency a.py AND b.py"}
    res4 = run_auto_fix_for_incident(incident3, None, MockLLMConfig([file1, "a.py", "b.py"], valid_diff), repo_path)


    print("\\n" + "="*50)
    print("SCENARIO 4: The False Alarm (Trigger Gate)")
    print("="*50)
    incident_hash4 = "false_alarm_4"
    mock_store["incidents"][incident_hash4] = {"incident_hash": incident_hash4}
    with open(".incident_store.json", "w") as f: json.dump(mock_store, f)
    incident4 = {"incident_hash": incident_hash4, "priority_level": "P2", "trend": "spiking", "confidence": "HIGH", "error": f"Error in {file1}"}
    res5 = run_auto_fix_for_incident(incident4, None, MockLLMConfig([file1], valid_diff), repo_path)


    print("\\n" + "="*50)
    print("SCENARIO 5: The Silent Abort (No Side Effects)")
    print("="*50)
    print("Final Repo State:\\n", get_repo_state(repo_path))

if __name__ == "__main__":
    run_scenarios()
