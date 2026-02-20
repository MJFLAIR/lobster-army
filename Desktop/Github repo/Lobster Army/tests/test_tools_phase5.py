import pytest
from tools.tool_gate import ToolGate, SecurityError
from tools.ref_sanitizer import RefSanitizer
from tools.ast_validator import ASTValidator
from tools.network_client import NetworkClient, NetworkPolicyError
from tools.git_client import GitClient
from unittest.mock import patch

# 1. ToolGate Tests
def test_tool_gate_allowed():
    # Valid commands
    ToolGate.validate_git_command(["git", "status"])
    ToolGate.validate_git_command(["git", "diff"])
    ToolGate.validate_git_command(["git", "fetch"])
    ToolGate.validate_git_command(["git", "switch", "-c", "task/123"])
    ToolGate.validate_git_command(["git", "checkout", "task/123"])
    ToolGate.validate_git_command(["git", "add", "."])
    ToolGate.validate_git_command(["git", "commit", "-m", "fix: bug"])
    ToolGate.validate_git_command(["git", "merge", "--no-ff", "task/123"])
    ToolGate.validate_git_command(["git", "tag", "lobster/task-123/complete"])
    ToolGate.validate_git_command(["git", "push", "origin", "task/123"])

def test_tool_gate_forbidden():
    # Invalid subcommands
    with pytest.raises(SecurityError, match="Forbidden git subcommand"):
        ToolGate.validate_git_command(["git", "config", "--list"])
    
    with pytest.raises(SecurityError, match="Forbidden git subcommand"):
        ToolGate.validate_git_command(["git", "remote", "-v"])
        
    # Forbidden flags
    with pytest.raises(SecurityError, match="Forbidden git flag"):
        ToolGate.validate_git_command(["git", "commit", "--amend", "-m", "bad"])
        
    # Invalid args format
    with pytest.raises(SecurityError, match="git switch must be"):
        ToolGate.validate_git_command(["git", "switch", "task/123"]) # Missing -c
        
    with pytest.raises(SecurityError, match="Invalid branch ref"):
        ToolGate.validate_git_command(["git", "switch", "-c", "feature/bad-name"])
        
    with pytest.raises(SecurityError, match="Invalid git checkout ref"):
        ToolGate.validate_git_command(["git", "checkout", "dev"]) # Only task/ID allowed
        
    with pytest.raises(SecurityError, match="git merge must be"):
        ToolGate.validate_git_command(["git", "merge", "task/123"]) # Missing --no-ff
        
    with pytest.raises(SecurityError, match="Commit message invalid"):
        ToolGate.validate_git_command(["git", "commit", "-m", "multi\nline"])

# 2. RefSanitizer Tests
def test_ref_sanitizer():
    assert RefSanitizer.validate("task/1", "checkout")
    assert RefSanitizer.validate("task/999", "checkout")
    assert not RefSanitizer.validate("task/abc", "checkout")
    assert not RefSanitizer.validate("feature/123", "checkout")
    
    assert RefSanitizer.validate("task/123", "merge")
    assert not RefSanitizer.validate("main", "merge") # Only merge task branches
    
    assert RefSanitizer.validate("lobster/task-123/complete", "tag")
    assert not RefSanitizer.validate("v1.0", "tag")

# 3. AST Validator Tests
def test_ast_validator(tmp_path):
    # Good file
    good_file = tmp_path / "good.py"
    good_file.write_text("import json\nprint('hello')")
    assert not ASTValidator.scan_file(good_file)
    
    # Bad import
    bad_import = tmp_path / "bad_import.py"
    bad_import.write_text("import subprocess\nsubprocess.run('ls')")
    violations = ASTValidator.scan_file(bad_import)
    assert len(violations) > 0
    assert "Forbidden import: subprocess" in violations[0]
    
    # Bad call
    bad_call = tmp_path / "bad_call.py"
    bad_call.write_text("import os\nos.system('rm -rf /')")
    violations = ASTValidator.scan_file(bad_call)
    assert len(violations) > 0
    assert "Forbidden call: os.system" in violations[0]
    
    # Bad import from
    bad_from = tmp_path / "bad_from.py"
    bad_from.write_text("from socket import socket")
    violations = ASTValidator.scan_file(bad_from)
    assert "Forbidden import-from" in violations[0]

# 4. Network Client Tests
@patch("urllib.request.urlopen")
def test_network_client(mock_urlopen):
    # Setup mock config via DB/Config patch? 
    # NetworkClient loads from Config.load.
    # We can patch Config.load
    with patch("workflows.storage.db.Config.load") as mock_conf:
        mock_conf.return_value = {
            "network": {
                "mode": "deny_by_default", 
                "allowlist_domains": ["api.openai.com"]
            }
        }
        
        client = NetworkClient()
        
        # Allowed
        mock_urlopen.return_value.__enter__.return_value.read.return_value = b"OK"
        resp = client.request("GET", "https://api.openai.com/v1/models")
        assert resp == b"OK"
        
        # Blocked
        with pytest.raises(NetworkPolicyError):
            client.request("GET", "https://google.com")
            
        # Blocked (subdomain not strictly allowed by exact match in simple logic, 
        # normally need wildcard support, but current impl checks exact hostname match against set)
        # implementation says: host in self.allow.
        with pytest.raises(NetworkPolicyError):
            client.request("GET", "https://www.openai.com")

def test_git_client():
    gc = GitClient()
    # Should pass validation
    res = gc.run(["git", "status"])
    assert "MOCKED" in res
    
    # Should raise error from ToolGate
    with pytest.raises(SecurityError):
        gc.run(["git", "remote"])
