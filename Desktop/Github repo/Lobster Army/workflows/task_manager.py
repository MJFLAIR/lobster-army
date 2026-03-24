from workflows.storage.db import DB
from tools.llm_client import LLMClient
from workflows.agents.pm_agent import PMAgent
from workflows.agents.code_agent import CodeAgent
from workflows.agents.review_agent import ReviewAgent
import logging

def is_review_passed(review_result: dict) -> bool:
    if review_result.get("approved") is True:
        return True
    if review_result.get("status") == "PASS":
        return True
    return False

class TaskManager:
    def execute(self, task_id: int, context: dict = None) -> None:
        """
        Orchestrates the PM -> Code -> Review loop using Real Agents + Real LLMClient (with NetworkClient).
        """
        task = DB.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        print("DEBUG execute context:", context)
        logging.info(f"Starting execution for task {task_id}")
        
        tracer = None
        if isinstance(context, dict):
            tracer = context.get("execution_tracer")
        
        from llm.factory import get_llm_for_role

        try:
            # 1. PM Step
            DB.emit_event(task_id, "STEP_START", {"step": "PM"})
            
            context = context or {}
            router_decision = context.get("router_decision", {})
            print("DEBUG router_decision:", router_decision)
            if router_decision.get("pipeline") == "review_only":
                logging.info(f"Task {task_id}: Skipping PM step (review_only pipeline)")
                pm_result = {"plan": {"skipped": True, "reason": "review_only"}}
            else:
                llm_pm = get_llm_for_role("pm")
                pm_agent = PMAgent(llm_pm, task_id)
                pm_result = pm_agent.run({"description": task.description})
            DB.emit_event(task_id, "STEP_DONE", {"step": "PM", "result": pm_result})
            
            if tracer:
                tracer.record_step("PMAgent", "success", pm_result)

            # 2. Code <-> Review Loop
            MAX_CYCLES = 3
            cycle = 0
            task_status = "FAILED" # Default until passing
            
            current_plan = pm_result.get("plan", {})
            feedback = ""
            review_result = {}

            while cycle < MAX_CYCLES:
                cycle += 1
                logging.info(f"Task {task_id}: Cycle {cycle}/{MAX_CYCLES}")
                DB.emit_event(task_id, "CYCLE_START", {"cycle": cycle})

                # Code Step or AutoFix_Medic Step
                if cycle > 1:
                    DB.emit_event(task_id, "STEP_START", {"step": "AutoFix_Medic", "cycle": cycle})
                    llm_code = get_llm_for_role("code")
                    from workflows.agents.autofix_medic import AutoFixMedicAgent
                    medic = AutoFixMedicAgent(llm_code)
                    medic_input = f"Fix the following errors: {feedback}\nOriginal plan: {current_plan}"
                    code_result = medic.handle_autofix_medic(medic_input)
                    DB.emit_event(task_id, "STEP_DONE", {"step": "AutoFix_Medic", "result": code_result})
                    
                    if tracer:
                        tracer.record_step("AutoFix_Medic", code_result.get("status", "success"), code_result)
                        
                    if code_result.get("status") == "success" and code_result.get("target_file"):
                        from workflows.tools.write_file import write_file
                        write_result = write_file(path=code_result["target_file"], content=code_result["code"], overwrite=True)
                        if tracer:
                            tracer.record_tool("write_file", write_result["status"], code_result["target_file"])
                            
                else:
                    DB.emit_event(task_id, "STEP_START", {"step": "Code", "cycle": cycle})
                    
                    llm_code = get_llm_for_role("code")
                    code_agent = CodeAgent(llm_code, task_id)
                    
                    code_result = code_agent.run(current_plan) # Simplified for 6A
                    DB.emit_event(task_id, "STEP_DONE", {"step": "Code", "result": code_result})
                    
                    if tracer:
                        tracer.record_step("Feature_Coder", "success", code_result)

                # Review Step
                DB.emit_event(task_id, "STEP_START", {"step": "Review", "cycle": cycle})
                
                llm_review = get_llm_for_role("review")
                review_agent = ReviewAgent(llm_review, task_id)
                review_result = review_agent.run(code_result)
                DB.emit_event(task_id, "STEP_DONE", {"step": "Review", "result": review_result})

                if tracer:
                    status = "success" if is_review_passed(review_result) else "failed"
                    tracer.record_step("Reviewer", status, review_result)

                logging.info(f"[TASK_REVIEW_STATUS] result={review_result}")

                if is_review_passed(review_result):
                    task_status = "PASS"
                    logging.info(f"Task {task_id} passed review on cycle {cycle}")
                    break
                else:
                    feedback = review_result.get("comments", "Fix issues")
                    logging.info(f"Task {task_id} failed review on cycle {cycle}: {feedback}")

            if task_status != "PASS":
                error_msg = f"Escalation: Task failed after {MAX_CYCLES} cycles."
                logging.error(f"[TASK_ESCALATION_REASON] Max cycles reached with final review_result={review_result}")
                raise RuntimeError(error_msg)

            # Success path
            DB.mark_task_done(task_id) # Explicitly mark done if passed
            logging.info(f"Task {task_id} completed successfully")
            
            # Post-settlement hook for PRs
            if getattr(task, "source", None) == "github_pr":
                try:
                    from tools.github_reporter import GitHubReporter
                    GitHubReporter().run_hook(task, review_result)
                except Exception as e:
                    logging.error(f"GitHubReporter hook failed: {e}")
                
                try:
                    from tools.github_pr_labeler import GitHubPRLabeler
                    GitHubPRLabeler().run_hook(task, review_result)
                except Exception as e:
                    logging.error(f"GitHubPRLabeler hook failed: {e}")
                    
                try:
                    from tools.github_pr_gate import GitHubPRGate
                    GitHubPRGate().run_hook(task, review_result)
                except Exception as e:
                    logging.error(f"GitHubPRGate hook failed: {e}")
                    
                try:
                    from tools.github_pr_merge_proposal import GitHubPRMergeProposal
                    GitHubPRMergeProposal().run_hook(task, review_result)
                except Exception as e:
                    logging.error(f"GitHubPRMergeProposal hook failed: {e}")
            
        except Exception as e:
            logging.error(f"Task execution failed: {e}")
            raise
