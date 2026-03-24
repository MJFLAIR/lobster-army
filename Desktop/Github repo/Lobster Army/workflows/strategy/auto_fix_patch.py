import json
import logging

def generate_patch_proposal(context: dict, llm_client) -> dict:
    if context.get("status") == "BLOCKED":
        return {
            "status": "BLOCKED",
            "reason": context.get("reason", "invalid_context")
        }

    target_files = context.get("allowed_files", [])
    if len(target_files) > 2:
        return {
            "status": "BLOCKED",
            "reason": "scope_too_wide"
        }

    from llm.prompt_loader import load_prompt
    prompt_template = load_prompt("auto_fix_agent_v1")
    
    logging.info("[AUTO_FIX_PROMPT_VERSION]", extra={
        "prompt": "auto_fix_agent_v1"
    })
    
    sitrep = f"Incident Hash: {context.get('incident_hash')}\nFailure Type: {context.get('failure_type')}\nSeverity: {context.get('severity')}"
    
    target_file = context.get('target_file', '')
    dependency_section = ""
    if context.get('dependency_file'):
        dependency_section = f"[DEPENDENCY_FILE: {context.get('dependency_file')}]\n```python\n{context.get('dependency_content', '')}\n```\n"
        
    prompt = prompt_template.replace("{sitrep}", sitrep)
    prompt = prompt.replace("{error_message}", str(context.get('error_summary', '')))
    prompt = prompt.replace("{allowed_files}", json.dumps(target_files))
    prompt = prompt.replace("{target_file}", target_file)
    prompt = prompt.replace("{file_content}", str(context.get('file_content', '')))
    prompt = prompt.replace("{dependency_section}", dependency_section)

    try:
        if hasattr(llm_client, "complete"):
            # Depending on how the llm_client expects kwargs
            response = llm_client.complete(
                prompt=prompt,
                response_format={"type": "json_object"}
            )
        else:
            # Fallback mock for testing if no real client provided
            response = '{"diff": "--- a/test.py\\n+++ b/test.py\\n@@ -1 +1 @@\\n-fail\\n+pass\\n", "status": "PATCH_READY", "target_files": %s, "summary": "mock fix", "estimated_changed_files": 1, "estimated_diff_lines": 2}' % json.dumps(target_files)

        if hasattr(response, "content"):
            content = response.content
        elif isinstance(response, dict) and "content" in response:
            content = response.get("content", "{}")
        else:
            content = response
            
        if isinstance(content, dict):
            data = content
        else:
            try:
                data = json.loads(str(content))
            except Exception as e:
                logging.error("[AUTO_FIX_INVALID_JSON]", extra={
                    "error": str(e),
                    "raw_output": str(content)[:1000]
                })
                return {
                    "status": "BLOCKED",
                    "reason": "invalid_llm_output",
                    "target_files": [],
                    "estimated_changed_files": 0,
                    "estimated_diff_lines": 0,
                    "diff": "",
                    "summary": "LLM output was not valid JSON"
                }

        REQUIRED_KEYS = [
            "status",
            "reason",
            "target_files",
            "estimated_changed_files",
            "estimated_diff_lines",
            "diff",
            "summary"
        ]
        
        missing_keys = [k for k in REQUIRED_KEYS if k not in data]
        if missing_keys:
            logging.warning("[AUTO_FIX_SCHEMA_INVALID]", extra={
                "missing_keys": missing_keys
            })
            return {
                "status": "BLOCKED",
                "reason": "invalid_llm_output",
                "target_files": [],
                "estimated_changed_files": 0,
                "estimated_diff_lines": 0,
                "diff": "",
                "summary": "LLM output was not valid JSON"
            }
            
        status = data.get("status")
        if status not in ["PATCH_READY", "BLOCKED"]:
            return {
                "status": "BLOCKED",
                "reason": "invalid_llm_output",
                "target_files": [],
                "estimated_changed_files": 0,
                "estimated_diff_lines": 0,
                "diff": "",
                "summary": "LLM output was not valid JSON"
            }
        diff = data.get("diff", "")
        changed_files = data.get("target_files", [])
        
        # Verify scope lock
        if len(changed_files) > 2:
            return {"status": "BLOCKED", "reason": "scope_too_wide_files"}
            
        diff_lines = len(diff.splitlines())
        if diff_lines > 80:
            return {"status": "BLOCKED", "reason": "scope_too_wide_diff"}
            
        # Ensure we only touch allowed files
        # A simple check: if any changed_file not in target_files -> blocked
        for file in changed_files:
            if file not in target_files and not any(file.endswith(tf) for tf in target_files):
                return {"status": "BLOCKED", "reason": "touched_unauthorized_files"}

        return {
            "status": status,
            "reason": data.get("reason", ""),
            "target_files": changed_files,
            "diff": diff,
            "summary": data.get("summary", "Auto-fix proposal"),
            "estimated_changed_files": len(changed_files),
            "estimated_diff_lines": diff_lines
        }

    except Exception as e:
        logging.error(f"[AUTO_FIX_PATCH_FAILED] {e}")
        return {
            "status": "FAILED",
            "reason": f"model_error: {str(e)}"
        }
