import logging
from workflows.strategy.auto_fix_orchestrator import run_auto_fix_for_incident
from workflows.strategy.adaptive_strategy import decide_retry_strategy

class RetryLLMWrapper:
    """Wraps the LLM client to inject the correction prompt into the next request."""
    def __init__(self, base_client, correction_prompt):
        self.base_client = base_client
        self.correction_prompt = correction_prompt
        
    def complete(self, prompt, **kwargs):
        new_prompt = f"{prompt}\n\n[SELF-HEALING CORRECTION INSTRUCTIONS]\n{self.correction_prompt}"
        if self.base_client and hasattr(self.base_client, "complete"):
            return self.base_client.complete(new_prompt, **kwargs)
        
class ErrorFeedbackBuilder:
    @staticmethod
    def build(failure_type: str, error_message: str, raw_output: str, context: dict) -> tuple[str, str]:
        if failure_type in ["invalid_llm_output", "json_parse_error"]:
            template_used = "JSON_FORMAT_ERROR"
            feedback = f"""=== RETRY FEEDBACK ===
Failure Type: JSON_FORMAT_ERROR
Error: {error_message}

Instructions:
- Return ONLY valid JSON
- Ensure all required keys exist: status, reason, target_files, estimated_changed_files, estimated_diff_lines, diff, summary

DO NOT change your original fix strategy.
DO NOT expand scope.
DO NOT modify additional files.
ONLY fix the specific error mentioned.
=== END ==="""

        elif failure_type in ["schema_invalid"]:
            template_used = "SCHEMA_VALIDATION_ERROR"
            feedback = f"""=== RETRY FEEDBACK ===
Failure Type: SCHEMA_VALIDATION_ERROR
Error: {error_message}

Instructions:
- Ensure all required keys are present
- Ensure correct data types for all fields

DO NOT change your original fix strategy.
DO NOT expand scope.
DO NOT modify additional files.
ONLY fix the specific error mentioned.
=== END ==="""

        elif failure_type in ["git_apply_check_failed", "patch_invalid"]:
            template_used = "DIFF_FORMAT_ERROR"
            feedback = f"""=== RETRY FEEDBACK ===
Failure Type: DIFF_FORMAT_ERROR
Error: {error_message}

Instructions:
- Use standard unified diff format
- Ensure @@ hunk headers and line numbers are correct

DO NOT change your original fix strategy.
DO NOT expand scope.
DO NOT modify additional files.
ONLY fix the specific error mentioned.
=== END ==="""

        else:
            template_used = "GENERAL_RETRY"
            feedback = f"""=== RETRY FEEDBACK ===
Failure Type: GENERAL_RETRY
Error: {error_message}

DO NOT change your original fix strategy.
DO NOT expand scope.
DO NOT modify additional files.
ONLY fix the specific error mentioned.
=== END ==="""

        logging.info("[SELF_HEAL_FEEDBACK_TYPE]", extra={
            "failure_type": failure_type,
            "template_used": template_used
        })
        return feedback, template_used

def self_healing_execute(incident: dict, repo_adapter, llm_client, repo_path: str) -> dict:
    """
    Wraps Auto-Fix execution with a STRICT 1-retry loop and failure pattern funnel.
    """
    incident_id = incident.get("incident_hash", "unknown")
    initial_failure_type = "unknown"
    template_used = "NONE"
    retry_triggered = False
    retry_success = False
    final_status = "BLOCKED"
    final_failure_type = "unknown"
    result_to_return = None
    
    try:
        # 1. Initial Run
        result_v1 = run_auto_fix_for_incident(incident, repo_adapter, llm_client, repo_path)
        
        status = result_v1.get("status")
        reason = result_v1.get("reason", "")
        
        if status in ["PR_READY", "DRAFT_PR_READY", "PATCH_READY"]:
            initial_failure_type = "NONE"
            final_status = status
            final_failure_type = "NONE"
            result_to_return = result_v1
            return result_to_return
            
        initial_failure_type = reason
        
        # Strictly retry only for these allowed reasons
        eligible_reasons = ["invalid_llm_output", "patch_invalid", "json_parse_error", "schema_invalid", "git_apply_check_failed"]
        is_eligible = any(r in reason for r in eligible_reasons) or reason in eligible_reasons
        
        if (status == "BLOCKED" or status == "FAILED") and is_eligible:
            decision = decide_retry_strategy(initial_failure_type)
            logging.info("[ADAPTIVE_STRATEGY_DECISION]", extra={
                "failure_type": initial_failure_type,
                "should_retry": decision["should_retry"],
                "reason": decision["reason"],
                "template_override": decision["template_override"]
            })
            
            if not decision["should_retry"]:
                # FAIL-FAST: Skip retry
                result_v1["status"] = "BLOCKED"
                final_status = "BLOCKED"
                final_failure_type = initial_failure_type
                logging.info("[SELF_HEAL_RESULT]", extra={"final_status": final_status, "retries_used": 0})
                result_to_return = result_v1
                return result_to_return
                
            retry_triggered = True
            logging.info("[SELF_HEAL_TRIGGER]", extra={"incident_id": incident_id, "failure_type": initial_failure_type})
            
            error_details = "The patch generated was either invalid JSON, broke schema constraints, or failed to apply cleanly."
            raw_output_str = "[See previous run logs]"
            
            correction_prompt, built_template = ErrorFeedbackBuilder.build(
                failure_type=initial_failure_type,
                error_message=error_details,
                raw_output=raw_output_str,
                context=incident
            )
            
            if decision.get("template_override"):
                template_used = decision["template_override"]
            else:
                template_used = built_template
            
            retry_llm = RetryLLMWrapper(llm_client, correction_prompt)
            
            # Bypass cooldown for the immediate retry
            if "auto_fix_last_attempt_ts" in incident:
                del incident["auto_fix_last_attempt_ts"]
                
            logging.info("[SELF_HEAL_RETRY]", extra={"retry_count": 1, "failure_type": initial_failure_type})
            
            # 2. Retry Run
            result_v2 = run_auto_fix_for_incident(incident, repo_adapter, retry_llm, repo_path)
            
            final_status_raw = result_v2.get("status")
            final_failure_type = result_v2.get("reason", "unknown") if final_status_raw not in ["PR_READY", "DRAFT_PR_READY", "PATCH_READY"] else "NONE"
            
            if final_status_raw not in ["PR_READY", "DRAFT_PR_READY", "PATCH_READY"]:
                final_status = "BLOCKED"
                result_v2["status"] = "BLOCKED"
                retry_success = False
            else:
                final_status = final_status_raw
                retry_success = True
            
            logging.info("[SELF_HEAL_RESULT]", extra={"final_status": final_status, "retries_used": 1})
            result_to_return = result_v2
            return result_to_return
            
        # If not eligible:
        if status not in ["PR_READY", "DRAFT_PR_READY", "PATCH_READY"]:
            result_v1["status"] = "BLOCKED"
            final_status = "BLOCKED"
            final_failure_type = initial_failure_type
        else:
            final_status = status
            final_failure_type = "NONE"
            
        logging.info("[SELF_HEAL_RESULT]", extra={"final_status": final_status, "retries_used": 0})
        result_to_return = result_v1
        return result_to_return
        
    finally:
        event = {
            "incident_id": incident_id,
            "initial_failure_type": initial_failure_type,
            "template_used": template_used,
            "retry_triggered": retry_triggered,
            "retry_count_used": 1 if retry_triggered else 0,
            "retry_success": retry_success,
            "final_status": final_status,
            "final_failure_type": final_failure_type
        }
        try:
            from workflows.strategy.failure_pattern_tracker import record_failure_event
            record_failure_event(event)
            logging.info("[SELF_HEAL_PATTERN_TRACKED]", extra=event)
        except Exception as e:
            logging.error("[SELF_HEAL_TRACKING_ERROR]", extra={"error": str(e)})
