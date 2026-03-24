import logging

def apply_micro_fix(stage: dict, error: str) -> dict:
    error_lower = error.lower()
    
    result = {
        "status": "skipped",
        "action": "none",
        "detail": "no safe fix identified"
    }
    
    if "workflows." in error_lower and "no module named" in error_lower:
        result = {
            "status": "skipped",
            "action": "log_import_case_warning",
            "detail": "detected potential casing issue in imports (e.g. Workflows -> workflows)"
        }
    elif "no module named" in error_lower:
        result = {
            "status": "skipped",
            "action": "log_missing_module",
            "detail": "detected missing module. package installation required manually."
        }
    elif "unexpected indent" in error_lower or "syntaxerror" in error_lower:
        result = {
            "status": "skipped",
            "action": "log_syntax_warning",
            "detail": "detected syntax/indentation error. manual fix required."
        }
        
    logging.info("[MICRO_FIX_APPLIED]", extra=result)
    
    return result
