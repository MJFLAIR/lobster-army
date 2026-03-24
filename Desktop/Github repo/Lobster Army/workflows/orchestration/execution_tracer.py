import json
import logging

class ExecutionTracer:
    def __init__(self, task_id):
        self.trace = {
            "task_id": task_id,
            "task_type": "unknown",
            "input": "",
            "plan": [],
            "steps": [],
            "final_status": "UNKNOWN",
            "retry_count": 0,
            "self_healing_triggered": False,
            "sandbox_write_paths": []
        }

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
        if agent == "AutoFix_Medic":
            self.trace["self_healing_triggered"] = True

    def record_tool(self, tool_name: str, status: str, target: str):
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

    def finalize(self, status: str) -> dict:
        self.trace["final_status"] = status
        return self.trace
