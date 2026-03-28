def classify_trend(delta: int) -> str:
    if delta >= 10:
        return "spiking"
    if delta >= 1:
        return "rising"
    return "stable"

def compute_system_status(summary: dict) -> str:
    try:
        top_incidents = summary.get("top_incidents", [])
        
        has_p1 = False
        has_spiking_p1 = False
        
        for inc in top_incidents:
            is_p1 = str(inc.get("priority_level", "")).upper() == "P1"
            is_spiking = str(inc.get("trend", "")).lower() == "spiking"
            
            if is_p1:
                has_p1 = True
                if is_spiking:
                    has_spiking_p1 = True
                    break
                    
        if has_spiking_p1:
            return "CRITICAL"
        if has_p1:
            return "DEGRADED"
        return "HEALTHY"
    except Exception:
        return "HEALTHY"
