import os
import requests
import logging

def fetch_changed_files(repo: str, event_type: str, identifier: str) -> list[str]:
    """
    Fetch changed files from GitHub.
    repo: "owner/repo"
    event_type: "pull_request" or "push"
    identifier: PR number (str/int) or commit SHA (str)
    """
    try:
        token = os.environ.get("GITHUB_TOKEN")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "lobster-army-enricher"
        }
        if token:
            headers["Authorization"] = f"token {token}"
            
        if event_type == "pull_request":
            url = f"https://api.github.com/repos/{repo}/pulls/{identifier}/files"
        elif event_type == "push":
            url = f"https://api.github.com/repos/{repo}/commits/{identifier}"
        else:
            return []

        logging.info("[CHANGED_FILES_FETCH_START]", extra={
            "repo": repo,
            "identifier": identifier,
            "event_type": event_type
        })

        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            changed_files = []
            
            if event_type == "pull_request":
                if isinstance(data, list):
                    for f in data:
                        if isinstance(f, dict):
                            fname = f.get("filename")
                            if isinstance(fname, str):
                                changed_files.append(fname)
            elif event_type == "push":
                if isinstance(data, dict):
                    files = data.get("files")
                    if isinstance(files, list):
                        for f in files:
                            if isinstance(f, dict):
                                fname = f.get("filename")
                                if isinstance(fname, str):
                                    changed_files.append(fname)

            logging.info("[CHANGED_FILES_FETCH_SUCCESS]", extra={
                "repo": repo,
                "identifier": identifier,
                "file_count": len(changed_files)
            })
            return changed_files
        else:
            logging.error("[CHANGED_FILES_FETCH_ERROR]", extra={
                "repo": repo,
                "identifier": identifier,
                "status": r.status_code
            })
            return []
            
    except Exception as e:
        logging.error("[CHANGED_FILES_FETCH_ERROR]", extra={
            "repo": repo,
            "identifier": identifier,
            "error": str(e)
        })
        return []
