import logging

def classify_issue(failure_info: dict, error: str) -> str:
    error_lower = error.lower()
    
    escalate_keywords = [
        "database", "schema", "migration", "connection refused",
        "multiple modules", "dependency", "timeout cascade"
    ]
    
    micro_fix_keywords = [
        "modulenotfounderror", "importerror", "no module named",
        "syntaxerror", "unexpected indent", "nameerror"
    ]
    
    result = "escalate"
    
    if any(k in error_lower for k in micro_fix_keywords):
        result = "micro_fix"
        
    if any(k in error_lower for k in escalate_keywords):
        result = "escalate"
        
    logging.info("[STRATEGY_CLASSIFIED]", extra={
        "type": result,
        "error": error[:200]
    })
    
    return result
