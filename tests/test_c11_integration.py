import os
import time
import subprocess
import shutil
import json

from workflows.strategy.auto_fix_orchestrator import run_auto_fix_for_incident
from workflows.strategy.incident_store import load_store, save_store

class MockLLMConfig:
    def __init__(self, target_file, diff):
        self.payload = {
            "status": "PATCH_READY",
            "diff": diff,
            "target_files": [target_file],
            "summary": "Fixed dummy function",
        }

    def complete(self, prompt, **kwargs):
        class Resp:
            content = json.dumps(self.payload)
        return Resp()

def setup_repo():
    # Because we are running git commands, let's just create a temporary git repo to ensure isolation
    test_dir = "/tmp/lobster_c11_integration_test"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    subprocess.run(["git", "init"], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@lobster.army"], cwd=test_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test Bot"], cwd=test_dir, check=True)
    
    target_file = "tests/test_c11_dummy.py"
    os.makedirs(os.path.join(test_dir, "tests"), exist_ok=True)
    
    file_path = os.path.join(test_dir, target_file)
    with open(file_path, "w") as f:
        f.write('def dummy():\\n    return "broken"\\n')
        
    subprocess.run(["git", "add", "."], cwd=test_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=test_dir, check=True, capture_output=True)
    
    return test_dir, target_file

def run_integration_test():
    repo_path, target_file = setup_repo()
    
    incident_hash = "c11_integ_hash_001"
    
    mock_store = {
        "incidents": {
            incident_hash: {
                "incident_hash": incident_hash,
                "priority_level": "P1",
                "trend": "spiking",
                "confidence": "HIGH",
            }
        }
    }
    
    # Temporarily override store path or rely on cwd (incident_store loads from `.incident_store.json` in cwd)
    # We will write it to the actual execution dir so orchestrated logic can pick it up
    with open(".incident_store.json", "w") as f:
        json.dump(mock_store, f)
        
    incident = {
        "incident_hash": "c11_integ_hash_001",
        "priority_level": "P1",
        "trend": "spiking",
        "confidence": "HIGH",
        "error": f'Error in File "{target_file}", near dummy()'
    }
    
    print("Running integration test for C11 Autopatch with Dry-Run...")
    
    file_path = os.path.join(repo_path, target_file)
    with open(file_path, "w") as f:
        f.write('def dummy():\n    return "fixed"\n')
    
    diff_output = subprocess.run(["git", "diff"], cwd=repo_path, capture_output=True, text=True).stdout
    
    subprocess.run(["git", "checkout", "--", "."], cwd=repo_path, check=True)
    
    llm = MockLLMConfig(target_file, diff_output)
    result = run_auto_fix_for_incident(incident, None, llm, repo_path)
    
    print("Result:", result)
    
    assert result["status"] == "PR_READY"
    assert "branch_name" in result
    
    print("Success: Pipeline ran, branch created, patch validated and applied.")
    
if __name__ == "__main__":
    run_integration_test()
