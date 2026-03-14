from workflows.storage.db import DB
from tools.llm_client import LLMClient
from workflows.agents.pm_agent import PMAgent
from workflows.agents.code_agent import CodeAgent
from workflows.agents.review_agent import ReviewAgent
import logging

class TaskManager:
    def execute(self, task_id: int) -> None:
        """
        Orchestrates the PM -> Code -> Review loop using Real Agents + Real LLMClient (with NetworkClient).
        """
        task = DB.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        logging.info(f"Starting execution for task {task_id}")
        
        from llm.role_config import get_role_config
        from llm.factory import create_llm

        try:
            # 1. PM Step
            DB.emit_event(task_id, "STEP_START", {"step": "PM"})
            
            cfg_pm = get_role_config("pm")
            llm_pm = create_llm(cfg_pm["provider"], cfg_pm["model"])
            logging.info(f"[PM_LLM_PROVIDER] {cfg_pm['provider']}")
            pm_agent = PMAgent(llm_pm, task_id)
            
            # Use attribute access for Dataclass
            pm_result = pm_agent.run({"description": task.description})
            DB.emit_event(task_id, "STEP_DONE", {"step": "PM", "result": pm_result})

            # 2. Code <-> Review Loop
            MAX_CYCLES = 3
            cycle = 0
            task_status = "FAILED" # Default until passing
            
            current_plan = pm_result.get("plan", {})
            feedback = ""

            while cycle < MAX_CYCLES:
                cycle += 1
                logging.info(f"Task {task_id}: Cycle {cycle}/{MAX_CYCLES}")
                DB.emit_event(task_id, "CYCLE_START", {"cycle": cycle})

                # Code Step
                DB.emit_event(task_id, "STEP_START", {"step": "Code", "cycle": cycle})
                
                cfg_code = get_role_config("code")
                llm_code = create_llm(cfg_code["provider"], cfg_code["model"])
                logging.info(f"[CODE_LLM_PROVIDER] {cfg_code['provider']}")
                code_agent = CodeAgent(llm_code, task_id)
                
                # In a real scenario, we'd pass feedback from previous review
                # coding_context = {"plan": current_plan, "feedback": feedback}
                code_result = code_agent.run(current_plan) # Simplified for 6A
                DB.emit_event(task_id, "STEP_DONE", {"step": "Code", "result": code_result})

                # Review Step
                DB.emit_event(task_id, "STEP_START", {"step": "Review", "cycle": cycle})
                
                cfg_review = get_role_config("review")
                llm_review = create_llm(cfg_review["provider"], cfg_review["model"])
                logging.info(f"[REVIEW_LLM_PROVIDER] {cfg_review['provider']}")
                review_agent = ReviewAgent(llm_review, task_id)
                review_result = review_agent.run(code_result)
                DB.emit_event(task_id, "STEP_DONE", {"step": "Review", "result": review_result})

                if review_result.get("status") == "PASS":
                    task_status = "PASS"
                    logging.info(f"Task {task_id} passed review on cycle {cycle}")
                    break
                else:
                    feedback = review_result.get("comments", "Fix issues")
                    logging.info(f"Task {task_id} failed review on cycle {cycle}: {feedback}")

            if task_status != "PASS":
                error_msg = f"Escalation: Task failed after {MAX_CYCLES} cycles."
                logging.error(error_msg)
                DB.mark_task_failed(task_id, error_msg)
                raise RuntimeError(error_msg)

            # Success path - In Phase 6B this would trigger Merge/Deploy
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
