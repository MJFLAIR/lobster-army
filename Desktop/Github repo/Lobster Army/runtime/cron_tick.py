import logging
from flask import jsonify
from workflows.storage.db import DB
from runtime.task_worker import TaskWorker

def handle_tick():
    try:
        task = DB.lock_next_pending_task(lock_owner="runtime")
        if not task:
            return jsonify({"ok": True, "picked": 0}), 200

        task_id = task["task_id"]

        try:
            # Setting task status, result summary, cost, events, etc is responsibility of TaskManager / Worker workflows 
            TaskWorker().run_task(task_id)

            # Read back state to return
            task = DB.get_task(task_id)
            final_status = getattr(task, "status", "UNKNOWN")

            return jsonify({"ok": True, "picked": 1, "task_id": task_id, "status": final_status}), 200

        except Exception as e:
            logging.exception(f"Task failed: {task_id}")

            # Post-DONE error guard
            current_status = "UNKNOWN"
            try:
                task_data = DB.get_task(task_id)
                if task_data:
                    current_status = task_data.status
            except Exception:
                pass

            if str(current_status).upper() == "DONE":
                DB.emit_event(task_id, "TASK_ERROR_AFTER_DONE", {
                    "error_message": str(e),
                    "where": "cron_tick.handle_tick"
                })
                # Skip mark_task_failed, state is already DONE
                return jsonify({"ok": True, "picked": 1, "task_id": task_id, "status": "DONE"}), 200

            DB.mark_task_failed(
                task_id=task_id,
                error_context={
                    "error_message": str(e),
                    "error_type": "LOGIC",   # 之後再做規則分類
                },
                retryable=False
            )

            return jsonify({"ok": True, "picked": 1, "task_id": task_id, "status": "FAILED"}), 200

    except Exception as e:
        logging.exception("System error in handle_tick")
        return jsonify({"ok": False, "error": str(e)}), 500