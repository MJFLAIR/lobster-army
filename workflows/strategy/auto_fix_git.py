import subprocess
import logging
import os
import tempfile

def create_fix_branch_name(incident: dict) -> str:
    h = incident.get("incident_hash", "unknown")[:8]
    return f"fix/incident-{h}"

def write_patch_to_tmp(patch: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".patch", prefix="c11_")
    with os.fdopen(fd, 'w') as f:
        f.write(patch)
    return path

def validate_patch_applicability(repo_path: str, patch: str) -> dict:
    patch_path = write_patch_to_tmp(patch)
    try:
        cmd = ["git", "apply", "--check", patch_path]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
        if result.returncode == 0:
            logging.info("[AUTO_FIX_PATCH_DRYRUN_PASS]")
            return {"status": "PASS", "reason": ""}
        else:
            logging.warning("[AUTO_FIX_PATCH_DRYRUN_FAIL]", extra={"error": result.stderr})
            return {"status": "FAIL", "reason": result.stderr}
    except Exception as e:
        logging.warning("[AUTO_FIX_PATCH_DRYRUN_FAIL]", extra={"error": str(e)})
        return {"status": "FAIL", "reason": str(e)}
    finally:
        try:
            os.remove(patch_path)
        except OSError:
            pass

def apply_patch_in_sandbox(repo_path: str, patch: str) -> dict:
    patch_path = write_patch_to_tmp(patch)
    try:
        cmd = ["git", "apply", patch_path]
        result = subprocess.run(cmd, cwd=repo_path, capture_output=True, text=True)
        if result.returncode == 0:
            logging.info("[AUTO_FIX_PATCH_APPLIED]")
            return {"status": "PASS"}
        else:
            logging.error("[AUTO_FIX_PATCH_FAILED]", extra={"error": result.stderr})
            return {"status": "FAIL", "reason": result.stderr}
    except Exception as e:
        logging.error("[AUTO_FIX_PATCH_FAILED]", extra={"error": str(e)})
        return {"status": "FAIL", "reason": str(e)}
    finally:
        try:
            os.remove(patch_path)
        except OSError:
            pass

def commit_sandbox_fix(repo_path: str, branch_name: str, summary: str) -> dict:
    try:
        # Create branch
        subprocess.run(["git", "switch", "-c", branch_name], cwd=repo_path, check=True, capture_output=True)
        logging.info("[AUTO_FIX_GIT_BRANCH_CREATED]", extra={"branch_name": branch_name})
        
        # Add changes
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        
        # Commit
        msg = f"AutoFix: {summary}"
        subprocess.run(["git", "commit", "-m", msg], cwd=repo_path, check=True, capture_output=True)
        return {"status": "PASS", "branch_name": branch_name}
    except subprocess.CalledProcessError as e:
        logging.error(f"[AUTO_FIX_COMMIT_FAIL] {e.stderr}")
        return {"status": "FAIL", "reason": str(e.stderr) or str(e)}
    except Exception as e:
        return {"status": "FAIL", "reason": str(e)}
