from google.cloud import firestore
from datetime import datetime
from typing import Optional, Dict, Any
import uuid
import logging
from workflows.storage.models import Task


class DB:
    _client: Optional[firestore.Client] = None

    @staticmethod
    def get_client() -> firestore.Client:
        if DB._client is None:
            DB._client = firestore.Client()
        return DB._client

    # ------------------------------------------------------------------
    # Task Creation
    # ------------------------------------------------------------------

    @staticmethod
    def create_task(task: Task) -> None:
        db = DB.get_client()

        task_id = str(task.task_id)

        db.collection("tasks").document(task_id).set({
            "task_id": task.task_id,
            "payload": task.payload,
            "status": "PENDING",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

        db.collection("command_queue").document(task_id).set({
            "status": "PENDING",
            "created_at": datetime.utcnow(),
            "locked_by": None,
            "locked_at": None,
            "attempts": 0
        })

    # ------------------------------------------------------------------
    # Lock Next Pending Task
    # ------------------------------------------------------------------

    @staticmethod
    def lock_next_pending_task(lock_owner: str) -> Optional[Dict[str, Any]]:
        """
        Atomically pick one PENDING task and mark it RUNNING.
        Uses Firestore transaction to avoid race condition.
        """

        db = DB.get_client()
        queue_ref = db.collection("command_queue")

        transaction = db.transaction()

        @firestore.transactional
        def txn(transaction):
            query = (
                queue_ref
                .where("status", "==", "PENDING")
                .order_by("created_at")
                .limit(1)
            )

            docs = list(transaction.get(query))

            if not docs:
                return None

            doc = docs[0]
            doc_ref = doc.reference

            # update queue
            transaction.update(doc_ref, {
                "status": "RUNNING",
                "locked_by": lock_owner,
                "locked_at": datetime.utcnow(),
                "attempts": doc.get("attempts", 0) + 1
            })

            # update task status
            task_ref = db.collection("tasks").document(doc.id)
            transaction.update(task_ref, {
                "status": "RUNNING",
                "updated_at": datetime.utcnow()
            })

            return {"task_id": int(doc.id)}

        try:
            return txn(transaction)
        except Exception as e:
            logging.error(f"Lock transaction failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Mark Task Completed
    # ------------------------------------------------------------------

    @staticmethod
    def mark_task_completed(task_id: int) -> None:
        db = DB.get_client()
        task_id_str = str(task_id)

        db.collection("tasks").document(task_id_str).update({
            "status": "COMPLETED",
            "updated_at": datetime.utcnow()
        })

        db.collection("command_queue").document(task_id_str).update({
            "status": "DONE"
        })

    # ------------------------------------------------------------------
    # Mark Task Failed
    # ------------------------------------------------------------------

    @staticmethod
    def mark_task_failed(task_id: int, error: str) -> None:
        db = DB.get_client()
        task_id_str = str(task_id)

        db.collection("tasks").document(task_id_str).update({
            "status": "FAILED",
            "error": error,
            "updated_at": datetime.utcnow()
        })

        db.collection("command_queue").document(task_id_str).update({
            "status": "FAILED"
        })

