import logging

def build_auto_fix_context(incident: dict, repo_adapter=None) -> dict:
    error_text = str(incident.get("error", ""))
    incident_hash = incident.get("incident_hash", "")
    
    # Very rudimentary parsing to find target_file if it's explicitly in the error
    # Or rely on incident hints
    target_file = None
    dependency_file = None
    
    # Ideally, failure_type or error includes a path
    # Here we simulate extracting a python file from typical stack trace lines
    # If using repo_adapter, we might query it for matching files
    import re
    matches = re.findall(r'File "([^"]+\.py)"', error_text)
    if not matches:
        matches = re.findall(r'([^/\s]+\.py)', error_text)
    
    if matches:
        target_file = matches[-1] # Usually the last one in traceback is the actual failure
    
    if not target_file:
        return {
            "status": "BLOCKED",
            "reason": "missing_target_file"
        }
        
    allowed_files = [target_file]
    if len(matches) > 1:
        dependency_file = matches[-2]
        if dependency_file != target_file:
            allowed_files.append(dependency_file)
            
    return {
        "status": "READY",
        "incident_hash": incident_hash,
        "failure_type": incident.get("failure_type", "unknown"),
        "severity": incident.get("severity", "unknown"),
        "pipeline": incident.get("pipeline", "unknown"),
        "target_file": target_file,
        "target_function": None,
        "dependency_file": dependency_file if dependency_file != target_file else None,
        "error_summary": error_text[:500],  # Minimal payload
        "allowed_files": allowed_files
    }
