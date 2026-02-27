from workflows.task_manager import TaskManager
from workflows.storage.db import DB

class TaskWorker:
    def run_task(self, task_id: int):
        # 事件可以保留（可審計）
        DB.emit_event(task_id, "EXECUTION_STARTED", {"task_id": task_id})

        # 執行：建議讓 TaskManager.execute 回傳 result_summary / cost_json
        # 如果目前 execute 沒回傳，就先用 mock，至少先跑通閉環
        result = TaskManager().execute(task_id)

        # 若 TaskManager.execute 目前回傳 None，就先包成可存的結構
        if result is None:
            result_summary = {"message": "execution finished", "task_id": task_id}
            cost_json = {"model": "none", "input_tokens": 0, "output_tokens": 0, "estimated_usd": 0}
        else:
            # 若你之後讓 execute 回傳 dict（含 result/cost），就改用這裡接
            # 例如 result = {"result_summary": {...}, "cost_json": {...}}
            result_summary = result.get("result_summary", {"task_id": task_id})
            cost_json = result.get("cost_json", {"model": "unknown"})

        DB.emit_event(task_id, "EXECUTION_FINISHED", {"task_id": task_id})
        return result_summary, cost_json