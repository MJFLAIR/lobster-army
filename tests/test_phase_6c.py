import pytest
import os
import subprocess
from tools.git_client import GitClient
from tools.tool_gate import SecurityError
import tempfile

@pytest.fixture
def temp_git_repo():
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Initialize bare-bones git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_dir, check=True)
        
        # Configure user for commit
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=tmp_dir, check=True)
        
        # Initial commit so we have a valid HEAD
        with open(os.path.join(tmp_dir, "readme.md"), "w") as f:
            f.write("# Test")
        subprocess.run(["git", "add", "."], cwd=tmp_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_dir, check=True)
        
        yield tmp_dir

def test_create_branch_and_switch(temp_git_repo):
    client = GitClient(temp_git_repo)
    
    # Action
    client.create_branch(123)
    
    # Verification
    # Check current branch
    assert client.get_current_branch() == "task/123"

def test_commit_changes_on_task_branch(temp_git_repo):
    client = GitClient(temp_git_repo)
    client.create_branch(456)
    
    # Modify file
    new_file = os.path.join(temp_git_repo, "new_feature.py")
    with open(new_file, "w") as f:
        f.write("print('hello')")
        
    # Action
    client.commit_changes("feat: add login")
    
    # Verify commit exists
    log = subprocess.run(["git", "log", "--oneline"], cwd=temp_git_repo, capture_output=True, text=True).stdout
    assert "feat: add login" in log

def test_forbidden_operations(temp_git_repo):
    client = GitClient(temp_git_repo)
    
    # 1. Block access to main (modification)
    # We are on main by default
    assert client.get_current_branch() == "main"
    
    with open(os.path.join(temp_git_repo, "bad.txt"), "w") as f:
        f.write("bad")
        
    with pytest.raises(SecurityError, match="Cannot modify main"):
         client.commit_changes("bad commit")
         
    # 2. Block Push (via internal run_command access if tried)
    # We must construct a VALID push command for ToolGate to pass it, 
    # so GitClient can catch "Remote operations forbidden".
    # ToolGate: git push origin <ref>
    with pytest.raises(SecurityError, match="Remote operations forbidden"):
        client._run_command(["git", "push", "origin", "task/123"])
        
    # 3. Block Merge
    with pytest.raises(SecurityError, match="Merging forbidden"):
        client._run_command(["git", "merge", "--no-ff", "task/123"]) # Valid ToolGate syntax

def test_tool_gate_integration(temp_git_repo):
    client = GitClient(temp_git_repo)
    
    # ToolGate blocks 'git config' by default (not in allowed list)
    # Error message: "Forbidden git subcommand: config" (because it IS in FORBIDDEN list)
    with pytest.raises(SecurityError, match="Forbidden git subcommand: config"):
        client._run_command(["git", "config", "--list"])

def test_get_current_branch_parsing(temp_git_repo):
    client = GitClient(temp_git_repo)
    assert client.get_current_branch() == "main"
    
    subprocess.run(["git", "switch", "-c", "test-branch"], cwd=temp_git_repo, check=True)
    assert client.get_current_branch() == "test-branch"
