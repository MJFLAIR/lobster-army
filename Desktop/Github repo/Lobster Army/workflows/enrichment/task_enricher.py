import logging
from workflows.enrichment.github_client import fetch_changed_files

def enrich_task(task: dict) -> dict:
    """
    Enrich task with external data exactly before router.
    Supports both PR and push events to attach file diffs to `changed_files`.
    """
    if not isinstance(task, dict):
        return task

    meta = task.get("meta")
    if not isinstance(meta, dict):
        meta = task.get("meta_json")
        
    if not isinstance(meta, dict):
        return task

    try:
        # Check if changed_files already exists and is unempty
        current_files = meta.get("changed_files")
        if isinstance(current_files, list) and len(current_files) > 0:
            return task
            
        if "changed_files" not in meta or not isinstance(meta["changed_files"], list):
            meta["changed_files"] = []

        # Safe extraction of repository
        repo = None
        event = meta.get("event") if isinstance(meta.get("event"), dict) else {}
        repo_val = meta.get("repository") or meta.get("repo") or event.get("repository")

        if isinstance(repo_val, dict):
            repo = repo_val.get("full_name")
            if not isinstance(repo, str):
                owner = repo_val.get("owner")
                if isinstance(owner, dict):
                    login = owner.get("login")
                    name = repo_val.get("name")
                    if isinstance(login, str) and isinstance(name, str):
                        repo = f"{login.strip()}/{name.strip()}".strip("/")
        elif isinstance(repo_val, str):
            repo = repo_val.strip()

        # Safe extraction of PR number
        pr_number = None
        pr_val = meta.get("pull_request") or event.get("pull_request")

        if isinstance(pr_val, dict):
            pr_number = pr_val.get("number")
            
        if pr_number is None:
            pr_number_raw = meta.get("pr_number") or meta.get("pull_request_number") or meta.get("number")
            if pr_number_raw is not None:
                try:
                    pr_number = int(str(pr_number_raw).strip())
                except Exception:
                    pass

        # Safe extraction of Commit SHA
        commit_sha = None
        head_commit = meta.get("head_commit")
        if isinstance(head_commit, dict):
            commit_sha = head_commit.get("id")
        if not isinstance(commit_sha, str):
            after_val = meta.get("after")
            if isinstance(after_val, str):
                commit_sha = after_val

        # Determine event type and identity
        event_type = None
        identifier = None
        if pr_number is not None:
            event_type = "pull_request"
            identifier = str(pr_number)
        elif commit_sha:
            event_type = "push"
            identifier = commit_sha

        if repo and event_type and identifier:
            fetched_files = fetch_changed_files(repo, event_type, identifier)
            if isinstance(fetched_files, list) and fetched_files:
                meta["changed_files"] = fetched_files

        changed_files = meta.get("changed_files", [])
        if not isinstance(changed_files, list):
            changed_files = []

        file_types = {
            "code": [],
            "test": [],
            "doc": [],
            "other": []
        }
        
        logging.info("[FILE_CLASSIFICATION_START]", extra={
            "repo": repo,
            "identifier": identifier,
            "event_type": event_type
        })
        
        for path in changed_files:
            if not isinstance(path, str):
                continue
                
            norm_path = path.strip().lower()
            
            if norm_path.startswith("tests/") or "test" in norm_path:
                file_types["test"].append(path)
            elif norm_path.endswith(".md") or "docs/" in norm_path:
                file_types["doc"].append(path)
            elif norm_path.startswith("src/") or norm_path.endswith(".py") or norm_path.endswith(".js") or norm_path.endswith(".ts"):
                file_types["code"].append(path)
            else:
                file_types["other"].append(path)
                
        meta["file_types"] = file_types
        
        logging.info("[FILE_CLASSIFICATION_SUCCESS]", extra={
            "total": len(changed_files),
            "code": len(file_types["code"]),
            "test": len(file_types["test"]),
            "doc": len(file_types["doc"]),
            "other": len(file_types["other"])
        })

    except Exception as e:
        logging.error(f"[TASK_ENRICHER_ERROR] Exception enriching task: {str(e)}")
        if "changed_files" not in meta or not isinstance(meta["changed_files"], list):
            meta["changed_files"] = []
        if "file_types" not in meta or not isinstance(meta["file_types"], dict):
            meta["file_types"] = {"code": [], "test": [], "doc": [], "other": []}

    return task
