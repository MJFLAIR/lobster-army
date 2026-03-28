def format_sitrep_discord(sitrep: dict, incident_info: dict = None) -> dict:
    failure_type = sitrep.get("failure_type", "unknown")
    pipeline = sitrep.get("pipeline", "unknown")
    
    color_map = {"P1": 16711680, "P2": 16753920, "P3": 16776960, "P4": 8421504}
    p_level = incident_info.get("priority_level", "P4") if incident_info else "P4"
    p_score = incident_info.get("priority_score", 0) if incident_info else 0
    
    embed = {
        "title": f"SITREP: {failure_type}",
        "description": sitrep.get("summary", "Complex failure detected requiring diagnostic review"),
        "color": color_map.get(p_level, 16711680),
        "fields": [
            {"name": "Task ID", "value": str(sitrep.get("task_id", "unknown")), "inline": True},
            {"name": "Pipeline", "value": pipeline, "inline": True},
            {"name": "Agent", "value": str(sitrep.get("agent", "unknown")), "inline": True},
            {"name": "Execution Mode", "value": str(sitrep.get("execution_mode", "unknown")), "inline": True},
            {"name": "Risk / Severity", "value": str(sitrep.get("risk_level", "high")).upper(), "inline": True},
            {"name": "Priority Level", "value": f"{p_level} (Score: {p_score})", "inline": True},
            {"name": "Recommended Action", "value": str(sitrep.get("recommended_action", "manual intervention required")), "inline": False}
        ]
    }
    
    return {
        "content": "🚨 Lobster Army SITREP triggered",
        "embeds": [embed]
    }

def format_daily_digest_discord(digest: dict) -> dict:
    embeds = []
    
    embeds.append({
        "title": "Incident Summary",
        "description": digest.get("summary_text", "No summary available"),
        "color": 3447003
    })
    
    top_incidents = digest.get("top_incidents", [])
    if top_incidents:
        fields = []
        for inc in top_incidents[:5]:
            level = str(inc.get("priority_level", "P4")).upper()
            ftype = inc.get("failure_type", "unknown")
            pipeline = inc.get("pipeline", "unknown")
            count = inc.get("count", 1)
            issue = inc.get("github_issue_number", "none")
            
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
            
            fields.append({
                "name": f"[{level}] {ftype}",
                "value": f"pipeline={pipeline} | count={count} | issue=#{issue}{trend_marker} | {confidence} {conf_icon}{auto_fix_msg}",
                "inline": False
            })
            
        embeds.append({
            "title": "Top Incidents",
            "color": 16711680,
            "fields": fields
        })
        
    return {
        "content": "📋 Lobster Army Daily Incident Digest",
        "embeds": embeds
    }
