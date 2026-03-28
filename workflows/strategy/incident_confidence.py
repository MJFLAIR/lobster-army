def classify_confidence(priority: str, trend: str) -> str:
    try:
        p = str(priority).upper()
        t = str(trend).lower()
        
        if p == "P1":
            if t == "spiking":
                return "HIGH"
            elif t in ["rising", "stable"]:
                return "MEDIUM"
                
        if p == "P2":
            if t == "spiking":
                return "MEDIUM"
            elif t in ["rising", "stable"]:
                return "LOW"
                
        return "LOW"
    except Exception:
        return "LOW"
