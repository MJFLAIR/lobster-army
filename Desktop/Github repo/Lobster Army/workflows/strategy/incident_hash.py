import hashlib
import re
import logging

def normalize_error(error: str) -> str:
    norm = error.lower()
    norm = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '', norm)
    norm = re.sub(r'0x[0-9a-f]+', '', norm)
    norm = re.sub(r'\d+', '', norm)
    norm = re.sub(r'\s+', ' ', norm).strip()
    return norm

def generate_incident_hash(sitrep: dict) -> str:
    failure_type = sitrep.get("failure_type", "unknown")
    pipeline = sitrep.get("pipeline", "unknown")
    agent = sitrep.get("agent", "unknown")
    
    error_raw = sitrep.get("error", "")
    error_norm = normalize_error(error_raw)[:200]
    
    logging.debug("[INCIDENT_ERROR_NORMALIZED]", extra={
        "original": error_raw[:100],
        "normalized": error_norm[:100]
    })
    
    base_string = f"{failure_type}|{pipeline}|{agent}|{error_norm}"
    
    return hashlib.md5(base_string.encode('utf-8')).hexdigest()
