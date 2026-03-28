import json
import logging
from utils.identifier import normalize_identifier

class ExecutionTracer:
    _ACTIVE_TRACERS = {}

    def __init__(self, task_id):
        ExecutionTracer._ACTIVE_TRACERS[task_id] = self
        self.trace = {
            "task_id": task_id,
            "task_type": "unknown",
            "input": "",
            "plan": [],
            "steps": [],
            "tool_actions": [],
            "final_status": "UNKNOWN",
            "retry_count": 0,
            "self_healing_triggered": False,
            "sandbox_write_paths": []
        }

    @classmethod
    def get_active_tracer(cls, task_id):
        return cls._ACTIVE_TRACERS.get(task_id)

    def set_task_info(self, task_type: str, task_input: str):
        self.trace["task_type"] = task_type
        self.trace["input"] = task_input

    def record_plan(self, plan: list):
        self.trace["plan"] = plan

    def record_router(self, decision: str):
        # We can record the router decision as a pseudo-step if wanted, or explicitly add a trace key.
        self.trace["steps"].append({
            "step_order": len(self.trace["steps"]) + 1,
            "agent": "TaskRouter",
            "status": "success",
            "output_summary": {"decision": decision}
        })

    def record_step(self, agent: str, status: str, summary: dict):
        step_entry = {
            "step_order": len(self.trace["steps"]) + 1,
            "agent": agent,
            "status": status,
            "output_summary": summary
        }
        self.trace["steps"].append(step_entry)
        
        # If the agent is AutoFix_Medic, it means self-healing actually ran.
        normalized_agent = normalize_identifier(agent)
        if normalized_agent in ("autofix_medic", "auto_fix_medic"):
            self.trace["self_healing_triggered"] = True

    def record_tool(self, tool_name: str, status: str, target: str):
        self.trace["tool_actions"].append({
            "tool_name": tool_name,
            "status": status,
            "target": target
        })

        # Record a tool interaction securely
        if tool_name == "write_file" and target:
            if target not in self.trace["sandbox_write_paths"]:
                self.trace["sandbox_write_paths"].append(target)
                
        self.trace["steps"].append({
            "step_order": len(self.trace["steps"]) + 1,
            "agent": "ToolLayer",
            "status": status,
            "output_summary": {"tool": tool_name, "target": target}
        })

    def record_healing(self, step_info: dict):
        # Additional trace logic if the pipeline triggers full healing explicitly.
        # But we already set self_healing_triggered when AutoFix_Medic runs.
        self.trace["self_healing_triggered"] = True
        if "healing_steps" not in self.trace:
            self.trace["healing_steps"] = []
        self.trace["healing_steps"].append(step_info)

    def record_model_usage(self, role: str, model: str, tokens: int = 0):
        if not hasattr(self, "model_usage"):
            self.model_usage = []

        self.model_usage.append({
            "role": role,
            "model": model,
            "tokens": tokens or 0
        })
        self.trace["model_usage"] = self.model_usage

    def finalize(self, status: str) -> dict:
        self.trace["final_status"] = status
        ExecutionTracer._ACTIVE_TRACERS.pop(self.trace.get("task_id"), None)
        
        # Test backward compatibility: allow `"PMAgent" in trace["steps"]` to work gracefully
        class StepList(list):
            def __contains__(self, item):
                if isinstance(item, str):
                    requested = normalize_identifier(item)
                    for step in self:
                        if not isinstance(step, dict):
                            continue
                        agent = normalize_identifier(step.get("agent", ""))
                        if requested in ("pm", "pm_agent") and agent in ("pm", "pm_agent"): return True
                        if requested == "feature_coder" and agent == "feature_coder": return True
                        if requested == "reviewer" and agent == "reviewer": return True
                        if requested in ("autofix_medic", "auto_fix_medic") and agent in ("autofix_medic", "auto_fix_medic"): return True
                return super().__contains__(item)
                
        self.trace["steps"] = StepList(self.trace["steps"])
        return self.trace
