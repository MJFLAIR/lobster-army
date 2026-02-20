from flask import jsonify
from workflows.storage.db import DB
from runtime.task_worker import TaskWorker

def handle_tick():
    task = DB.lock_next_pending_task(lock_owner="runtime")
    if not task:
        return jsonify({"ok": True, "picked": 0})

    TaskWorker().run_task(task["task_id"])
    return jsonify({"ok": True, "picked": 1, "task_id": task["task_id"]})
