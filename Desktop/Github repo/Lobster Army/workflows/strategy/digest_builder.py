import logging
from workflows.strategy.dashboard_builder import build_dashboard_snapshot

def build_daily_digest(limit: int = 5) -> dict:
    try:
        snapshot = build_dashboard_snapshot(limit)
        
        total = snapshot.get("total_open_incidents", 0)
        p1 = snapshot.get("p1", 0)
        p2 = snapshot.get("p2", 0)
        p3 = snapshot.get("p3", 0)
        p4 = snapshot.get("p4", 0)
        system_status = snapshot.get("system_status", "HEALTHY")
        
        lines = [
            f"⚠️ System Status: {system_status}",
            "",
            "🚨 Lobster Army Daily Incident Digest",
            "",
            f"Open Incidents: {total}",
            f"P1: {p1} | P2: {p2} | P3: {p3} | P4: {p4}",
            "",
            "Top Incidents:"
        ]
        
        top_incidents = snapshot.get("top_incidents", [])
        if not top_incidents:
            lines.append("No open incidents.")
        else:
            for i, inc in enumerate(top_incidents, 1):
                level = str(inc.get("priority_level", "P4")).upper()
                ftype = inc.get("failure_type", "unknown")
                pipeline = inc.get("pipeline", "unknown")
                count = inc.get("count", 1)
                
                trend = inc.get("trend", "stable")
                confidence = str(inc.get("confidence", "LOW")).upper()
                
                trend_marker = ""
                if trend == "spiking":
                    trend_marker = " | 🚨 spiking"
                elif trend == "rising":
                    trend_marker = " | ↑ rising"
                    
                conf_icon = "⚪"
                if confidence == "HIGH":
                    conf_icon = "🔴"
                elif confidence == "MEDIUM":
                    conf_icon = "🟡"
                    
                auto_fix_msg = ""
                af_status = inc.get("auto_fix_status")
                if af_status:
                    if af_status == "BLOCKED":
                        auto_fix_msg = f" | AutoFix: BLOCKED ({inc.get('auto_fix_reason', '')})"
                    else:
                        auto_fix_msg = f" | AutoFix: {af_status}"
                        
                lines.append(f"{i}. [{level}] {ftype} | {pipeline} | x{count}{trend_marker} | {confidence} {conf_icon}{auto_fix_msg}")
                
        summary_text = "\n".join(lines)
        
        digest = {
            "summary_text": summary_text,
            "top_incidents": top_incidents,
            "dashboard_snapshot": snapshot
        }
        
        logging.info("[DAILY_DIGEST_BUILT]", extra={
            "total_open_incidents": total,
            "top_incidents_included": len(top_incidents)
        })
        
        try:
            with open(".daily_digest.txt", "w") as f:
                f.write(summary_text)
        except Exception as e:
            logging.warning("[DAILY_DIGEST_WRITE_FAILED]", extra={"error": str(e)})
            
        return digest
    except Exception as e:
        logging.error("[DAILY_DIGEST_FAILED] build error", extra={"error": str(e)})
        return {
            "summary_text": "⚠️ System Status: HEALTHY\n\n🚨 Lobster Army Daily Incident Digest\n\nError generating digest.",
            "top_incidents": [],
            "dashboard_snapshot": {}
        }
