import time
import json
import os

_STATS_CACHE = None
_CACHE_TIMESTAMP = 0
CACHE_TTL = 30
LOG_PATH = "logs/failure_patterns.jsonl"
MIN_SAMPLES = 8
SUCCESS_THRESHOLD = 0.2

def get_failure_stats() -> dict:
    global _STATS_CACHE, _CACHE_TIMESTAMP
    now = time.time()
    if _STATS_CACHE is not None and (now - _CACHE_TIMESTAMP) < CACHE_TTL:
        return _STATS_CACHE

    stats = {}
    if not os.path.exists(LOG_PATH):
        _STATS_CACHE = stats
        _CACHE_TIMESTAMP = now
        return stats

    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    ftype = event.get("initial_failure_type")
                    if not ftype:
                        continue
                        
                    if ftype not in stats:
                        stats[ftype] = {"attempts": 0, "successes": 0}
                    
                    if event.get("retry_triggered"):
                        stats[ftype]["attempts"] += 1
                        if event.get("retry_success"):
                            stats[ftype]["successes"] += 1
                except json.JSONDecodeError:
                    pass
    except Exception:
        # Fallback to empty on missing file or read errors
        pass

    _STATS_CACHE = stats
    _CACHE_TIMESTAMP = now
    return stats

def decide_retry_strategy(failure_type: str) -> dict:
    """
    Determines whether a failure should be retried and which template to use.
    
    Returns:
        dict: {
            "should_retry": bool,
            "reason": str,
            "template_override": str | None
        }
    """
    template_map = {
        "json_parse_error": "JSON_FORMAT_ERROR",
        "invalid_llm_output": "JSON_FORMAT_ERROR",
        "schema_invalid": "SCHEMA_VALIDATION_ERROR",
        "git_apply_check_failed": "DIFF_FORMAT_ERROR",
        "patch_invalid": "DIFF_FORMAT_ERROR"
    }
    
    template = template_map.get(failure_type)
    
    # 1. FAIL-FAST RULE
    if failure_type in ["schema_invalid", "scope_violation"]:
        return {
            "should_retry": False,
            "reason": "Low recovery rate, high risk of constraint violation.",
            "template_override": template
        }
        
    # 2. DYNAMIC THRESHOLD LOGIC
    stats = get_failure_stats()
    f_stats = stats.get(failure_type)
    if f_stats:
        attempts = f_stats["attempts"]
        successes = f_stats["successes"]
        if attempts >= MIN_SAMPLES:
            if successes == 0:
                return {
                    "should_retry": False,
                    "reason": f"Zero successes after {attempts} attempts (threshold: >0).",
                    "template_override": template
                }
            
            success_rate = successes / attempts
            if success_rate < SUCCESS_THRESHOLD:
                return {
                    "should_retry": False,
                    "reason": f"Success rate {success_rate*100:.1f}% below threshold ({SUCCESS_THRESHOLD*100:.1f}%) after {attempts} attempts.",
                    "template_override": template
                }
    
    # 3. ALLOW RETRY (DEFAULT SAFE SET)
    if failure_type in ["json_parse_error", "invalid_llm_output", "patch_invalid", "git_apply_check_failed"]:
        return {
            "should_retry": True,
            "reason": "Retry allowed for recoverable failure type.",
            "template_override": template
        }
        
    # Default fallback
    return {
        "should_retry": False,
        "reason": "Failure type not eligible for retry.",
        "template_override": template
    }
