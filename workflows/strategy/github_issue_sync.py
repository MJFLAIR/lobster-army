import os
import requests
import logging

def get_issue_state(repo: str, issue_number: int, token: str) -> str:
    try:
        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("state", "unknown")
        return "unknown"
    except Exception as e:
        logging.warning("[GITHUB_STATE_FAIL]", extra={"error": str(e)})
        return "unknown"

def reopen_issue(repo: str, issue_number: int, token: str) -> bool:
    try:
        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        payload = {"state": "open"}
        resp = requests.patch(url, headers=headers, json=payload, timeout=5)
        if resp.status_code == 200:
            logging.info("[GITHUB_ISSUE_REOPENED]", extra={"issue": issue_number})
            return True
        return False
    except Exception as e:
        logging.warning("[GITHUB_REOPEN_FAIL]", extra={"error": str(e)})
        return False

def add_issue_comment(repo: str, issue_number: int, body: str, token: str) -> bool:
    try:
        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        payload = {"body": body}
        resp = requests.post(url, headers=headers, json=payload, timeout=5)
        if resp.status_code == 201:
            logging.info("[GITHUB_COMMENT_ADDED]", extra={"issue": issue_number})
            return True
        return False
    except Exception as e:
        logging.warning("[GITHUB_COMMENT_FAIL]", extra={"error": str(e)})
        return False

def build_sync_comment(incident: dict) -> str:
    error_raw = incident.get("error", "") or ""
    error = error_raw[:200]
    
    return f"""🚨 **Incident Update**

- **Hash:** {incident.get("incident_hash", "unknown")}
- **Occurrence Count:** {incident.get("occurrence_count", 0)}
- **Severity:** {incident.get("severity", "LOW").upper()}
- **Failure Type:** {incident.get("failure_type")}
- **Pipeline:** {incident.get("pipeline")}
- **Agent:** {incident.get("agent")}

**Error Snapshot:**
```
{error}
```

This incident has re-occurred and is still active.
"""
