from workflows.task_manager import TaskManager
from workflows.storage.db import DB

class TaskWorker:
    def run_task(self, task_id: int) -> None:
        DB.emit_event(task_id, "TASK_START", {"task_id": task_id})
        try:
            TaskManager().execute(task_id)
            DB.mark_task_done(task_id)
            DB.emit_event(task_id, "TASK_DONE", {"task_id": task_id})
        except Exception as e:
            DB.mark_task_failed(task_id, str(e))
            DB.emit_event(task_id, "TASK_FAILED", {"error": str(e)})
