from typing import Dict, Any
from workflows.storage.db import DB
import logging

class CostTracker:
    # Default budget in tokens or USD. Let's use tokens for simplicity in Phase 6B.
    DEFAULT_BUDGET_TOKENS = 100000 

    def __init__(self, task_id: int):
        self.task_id = task_id
        self.logger = logging.getLogger("CostTracker")

    def check_budget(self) -> None:
        """
        Checks if the task has exceeded its budget.
        Raises RuntimeError if exceeded.
        """
        task = DB.get_task(self.task_id)
        if not task:
            return
        
        # Use attribute access
        cost_json = task.cost_json or {}
        total_tokens = cost_json.get("tokens", 0)
        
        if total_tokens > self.DEFAULT_BUDGET_TOKENS:
            msg = f"Task {self.task_id} exceeded budget: {total_tokens}/{self.DEFAULT_BUDGET_TOKENS} tokens"
            self.logger.error(msg)
            # In real world, might mark task as failed/paused here
            raise RuntimeError(msg)

    def track_usage(self, usage: Dict[str, Any]) -> None:
        """
        Updates task cost and checks budget.
        usage: {"total_tokens": 123, ...}
        """
        if not usage:
            return

        # Update DB
        task = DB.get_task(self.task_id)
        current_cost = task.cost_json if task and task.cost_json else {}
        
        new_tokens = usage.get("total_tokens", 0)
        current_tokens = current_cost.get("tokens", 0)
        
        updated_cost = current_cost.copy()
        updated_cost["tokens"] = current_tokens + new_tokens
        
        DB.update_task_cost(self.task_id, updated_cost)
        DB.emit_event(self.task_id, "COST_UPDATE", {"tokens": new_tokens, "total": updated_cost["tokens"]})
        
        self.check_budget()
