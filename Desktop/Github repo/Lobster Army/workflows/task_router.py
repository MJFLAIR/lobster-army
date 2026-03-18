import logging

log = logging.getLogger(__name__)

def is_doc_or_test_file(filename: str) -> bool:
    """Check if the given filename is a documentation, text, configuration, or test file."""
    f = filename.lower()
    
    if f.endswith(('.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf')):
        return True
    
    if 'docs/' in f or 'test/' in f or 'tests/' in f or 'test_' in f or '_test' in f:
        return True
        
    return False

def select_pipeline(meta: dict) -> dict:
    """
    Selects the processing pipeline based on PR metadata without using any external APIs or Mutating states.
    
    Rules:
      - if changed files are only docs/txt/config/test -> review_only
      - elif branch starts with 'fix/' or 'bugfix/' -> code_pipeline
      - elif labels contain 'task' or 'automation' -> planning_pipeline
      - else -> review_only
    """
    pr = meta.get("pull_request") or (meta.get("event") or {}).get("pull_request") or {}
    if not isinstance(pr, dict):
        pr = {}
        
    changed_files = meta.get("changed_files", [])
    
    head = pr.get("head") or {}
    branch = head.get("ref", "")
    if not isinstance(branch, str):
        branch = ""
        
    labels_data = pr.get("labels", [])
    labels = []
    if isinstance(labels_data, list):
        for l in labels_data:
            if isinstance(l, dict):
                labels.append(l.get("name", "").lower())
            elif isinstance(l, str):
                labels.append(l.lower())
                
    # 1. if changed files are ONLY docs / txt / config / test related: review_only
    if isinstance(changed_files, list) and len(changed_files) > 0:
        all_doc_or_test = all(isinstance(f, str) and is_doc_or_test_file(f) for f in changed_files)
        if all_doc_or_test:
            return {"pipeline": "review_only"}

    # 2. elif branch starts with "fix/" or "bugfix/": code_pipeline
    if branch.startswith("fix/") or branch.startswith("bugfix/"):
        return {"pipeline": "code_pipeline"}

    # 3. elif labels contain "task" or "automation": planning_pipeline
    if any("task" in lbl or "automation" in lbl for lbl in labels):
        return {"pipeline": "planning_pipeline"}

    # 4. else: review_only
    return {"pipeline": "review_only"}
