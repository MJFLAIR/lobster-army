import subprocess
import logging
import os
from typing import List
from tools.tool_gate import ToolGate, SecurityError

class GitClient:
    def __init__(self, repo_path: str = "."):
        self.repo_path = os.path.abspath(repo_path)
        self.logger = logging.getLogger("GitClient")

    def create_branch(self, task_id: int) -> None:
        """
        Creates and switches to a new branch for the task.
        Format: task/<id>
        """
        branch_name = f"task/{task_id}"
        # Validate branch name logic is actually covered by ToolGate which checks specific commands, 
        # but here we construct it safely.
        
        # Security: Check we are not dirty? (Optional, skipped for simplicity in 6C)
        
        cmd = ["git", "switch", "-c", branch_name]
        self._run_command(cmd)
        self.logger.info(f"Switched to new branch: {branch_name}")

    def commit_changes(self, message: str) -> None:
        """
        Stages all changes and commits them.
        """
        # 1. Add all
        self._run_command(["git", "add", "."])
        
        # 2. Commit
        # ToolGate validates 'git commit -m "msg"' format
        cmd = ["git", "commit", "-m", message]
        self._run_command(cmd)
        self.logger.info(f"Committed changes: {message}")

    def get_current_branch(self) -> str:
        try:
            # git symbolic-ref --short HEAD
            # This logic is safe to run without strict toolgate check or can be allowed.
            # But let's use a lower level command that might not need ToolGate if we trust it,
            # OR better, run it through _run_command but we need to allow 'symbolic-ref' or 'rev-parse'.
            # Phase 5 ToolGate allowed: status, diff, fetch, switch, checkout, add, commit, merge, tag, push.
            # It did NOT allow 'rev-parse' or 'symbolic-ref'.
            # So we must use 'git status' or update ToolGate.
            # 'git status -b --porcelain' gives branch info.
            
            # Let's use 'git branch --show-current' (modern git)
            # We need to add 'branch' to allowed commands in ToolGate if not present.
            # Checking ToolGate: allowed_subcmds = {"status", "diff", "fetch", "switch", "checkout", "add", "commit", "merge", "tag", "push"}
            # 'branch' is MISSING.
            # We can use 'git status' which is allowed.
            
            output = self._run_command(["git", "status", "--porcelain", "-b"])
            # Output line 1: ## branchname... or ## branchname
            first_line = output.splitlines()[0]
            if "..." in first_line:
                branch = first_line.split("...")[0].split("## ")[1]
            else:
                branch = first_line.split("## ")[1]
            return branch.strip()
        except Exception:
            return "unknown"

    def _run_command(self, cmd: List[str], timeout: int = 10) -> str:
        """
        Executes git command using subprocess with strict safety checks.
        """
        # 1. Validate Command via ToolGate
        ToolGate.validate_git_command(cmd)

        # 2. Strict Safety Checks (Phase 6C specific)
        if cmd[1] in ["push", "fetch", "pull", "remote"]:
             raise SecurityError(f"Remote operations forbidden in Phase 6C: {cmd[1]}")
             
        if cmd[1] == "merge":
             raise SecurityError("Merging forbidden in Phase 6C")

        # 3. Branch Restriction
        # If we are modifying (add, commit), ensure we are NOT on main
        if cmd[1] in ["add", "commit"]:
            current_branch = self.get_current_branch()
            if current_branch in ["main", "master"]:
                raise SecurityError(f"Cannot modify {current_branch} directly. Switch to a task branch.")

        # 4. Execute
        try:
            self.logger.debug(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            self.logger.error("Git command timed out")
            raise RuntimeError("Git command timed out")
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() or e.stdout.strip()
            self.logger.error(f"Git command failed: {err_msg}")
            raise RuntimeError(f"Git failed: {err_msg}")
