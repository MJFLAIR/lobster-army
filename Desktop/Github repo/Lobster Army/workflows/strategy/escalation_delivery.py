import os
import requests
import logging
from workflows.strategy.github_issue_formatter import format_sitrep_issue
from workflows.strategy.discord_formatter import format_sitrep_discord

def send_github_issue(issue_payload: dict) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    
    if not token or not repo:
        return {"status": "skipped", "channel": "github", "detail": "Missing GITHUB_TOKEN or GITHUB_REPO env var"}
        
    try:
        url = f"https://api.github.com/repos/{repo}/issues"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        }
        resp = requests.post(url, headers=headers, json=issue_payload, timeout=5)
        if resp.status_code == 201:
            issue_number = None
            try:
                resp_json = resp.json()
                issue_number = resp_json.get("number")
            except Exception:
                pass
            return {"status": "sent", "channel": "github", "detail": "GitHub issue created successfully", "issue_number": issue_number}
        else:
            return {"status": "failed", "channel": "github", "detail": f"API error: {resp.status_code} {resp.text}"}
    except Exception as e:
        return {"status": "failed", "channel": "github", "detail": f"Exception: {str(e)}"}

def send_discord_notification(discord_payload: dict) -> dict:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        return {"status": "skipped", "channel": "discord", "detail": "Missing DISCORD_WEBHOOK_URL env var"}
        
    try:
        resp = requests.post(webhook_url, json=discord_payload, timeout=5)
        if resp.status_code in [200, 204]:
            return {"status": "sent", "channel": "discord", "detail": "Discord notification sent successfully"}
        else:
            return {"status": "failed", "channel": "discord", "detail": f"Webhook error: {resp.status_code} {resp.text}"}
    except Exception as e:
        return {"status": "failed", "channel": "discord", "detail": f"Exception: {str(e)}"}

def deliver_sitrep(sitrep: dict) -> dict:
    logging.info("[ESCALATION_DELIVERY_START]", extra={
        "task_id": sitrep.get("task_id"),
        "failure_type": sitrep.get("failure_type")
    })
    
    result = {
        "github": {"status": "skipped", "channel": "github", "detail": "Not attempted"},
        "discord": {"status": "skipped", "channel": "discord", "detail": "Not attempted"}
    }
    
    incident = {}
    try:
        from workflows.strategy.incident_manager import process_incident
        incident = process_incident(sitrep)
        logging.info("[INCIDENT_PROCESSED]", extra=incident)
        
        # Phase C11 - Evaluate for AutoFix Option
        try:
            from workflows.strategy.self_healing_loop import self_healing_execute
            import os
            
            repo_path = os.getcwd()
            # Try to grab llm block if configured, else use placeholder mock object
            try:
                from tools.real_llm_client import RealLLMClient
                llm = RealLLMClient()
            except ImportError:
                llm = None
                
            c11_res = self_healing_execute(incident, None, llm, repo_path)
            logging.info(f"[AUTO_FIX_RUN_COMPLETE]", extra=c11_res)
        except Exception as c11_e:
            logging.warning("[AUTO_FIX_EVALUATION_FAILED]", extra={"error": str(c11_e)})
            
    except Exception as e:
        logging.warning("[INCIDENT_PROCESSING_FAIL]", extra={"error": str(e)})
        incident = {"is_new": True}
        
    try:
        if incident.get("is_new", True):
            gh_payload = format_sitrep_issue(sitrep, incident_info=incident)
            gh_result = send_github_issue(gh_payload)
            result["github"] = gh_result
            logging.info("[ESCALATION_GITHUB_RESULT]", extra=gh_result)
            
            issue_num = gh_result.get("issue_number")
            if issue_num:
                try:
                    from workflows.strategy.incident_manager import attach_github_issue, update_last_synced
                    attach_github_issue(incident["incident_hash"], issue_num)
                    update_last_synced(incident["incident_hash"], incident.get("occurrence_count", 1))
                except Exception:
                    pass
        else:
            issue_number = incident.get("existing_issue_number")
            count = incident.get("occurrence_count", 1)
            last_synced = incident.get("last_synced_count", 0)
            
            result["github"] = {
                "status": "skipped", 
                "channel": "github", 
                "detail": f"Incident already tracked, reused issue {issue_number}"
            }
            
            def should_sync(cnt: int) -> bool:
                return cnt in [2, 3, 5, 10] or cnt % 10 == 0
                
            if issue_number and count > 1 and count != last_synced and should_sync(count):
                try:
                    from workflows.strategy.github_issue_sync import (
                        add_issue_comment,
                        get_issue_state,
                        reopen_issue,
                        build_sync_comment
                    )
                    from workflows.strategy.incident_manager import update_last_synced
                    
                    repo = os.getenv("GITHUB_REPO")
                    token = os.getenv("GITHUB_TOKEN")
                    
                    if repo and token:
                        state = get_issue_state(repo, issue_number, token)
                        if state == "closed":
                            reopen_issue(repo, issue_number, token)
                            
                        comment_body = build_sync_comment(incident)
                        added = add_issue_comment(repo, issue_number, comment_body, token)
                        if added:
                            update_last_synced(incident["incident_hash"], count)
                            result["github"]["detail"] = f"Synced comment on issue {issue_number}"
                except Exception as e:
                    logging.warning("[GITHUB_SYNC_FAIL]", extra={"error": str(e)})

            logging.info("[ESCALATION_GITHUB_RESULT]", extra=result["github"])
    except Exception as e:
        logging.warning("[ESCALATION_GITHUB_FATAL]", extra={"error": str(e)})

    try:
        discord_payload = format_sitrep_discord(sitrep, incident_info=incident)
        discord_result = send_discord_notification(discord_payload)
        result["discord"] = discord_result
        logging.info("[ESCALATION_DISCORD_RESULT]", extra=discord_result)
    except Exception as e:
        logging.warning("[ESCALATION_DISCORD_FATAL]", extra={"error": str(e)})
        
    logging.info("[ESCALATION_DELIVERY_COMPLETE]", extra={
        "task_id": sitrep.get("task_id")
    })
    
    return result

def deliver_daily_digest(discord_payload: dict) -> dict:
    logging.info("[DELIVER_DAILY_DIGEST_START]")
    result = {"discord": {"status": "skipped", "channel": "discord", "detail": "Not attempted"}}
    try:
        discord_result = send_discord_notification(discord_payload)
        result["discord"] = discord_result
        logging.info("[DELIVER_DAILY_DIGEST_RESULT]", extra=discord_result)
    except Exception as e:
        logging.warning("[DELIVER_DAILY_DIGEST_FATAL]", extra={"error": str(e)})
        
    return result
