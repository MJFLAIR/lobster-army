from __future__ import annotations
print("DB FILE LOADED:", __file__)

import logging
import uuid
from typing import Optional, Dict, Any

from google.cloud import firestore
from workflows.models.task import Task


# -------------------------
# Status constants (single source)
# -------------------------
TASK_PENDING = "PENDING"
TASK_RUNNING = "RUNNING"
TASK_DONE = "DONE"
TASK_FAILED = "FAILED"


class Config:
    """Minimal definition to restore compatibility for legacy imports."""
    @staticmethod
    def load(filepath: str) -> Dict[str, Any]:
        return {}


class Secrets:
    """Minimal definition to restore compatibility for legacy imports."""
    @staticmethod
    def get_secret_by_alias(alias: str) -> Optional[str]:
        return None


class DB:
    _client: Optional[firestore.Client] = None

    @staticmethod
    def get_client() -> firestore.Client:
        import os
        if DB._client is None:
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
            db_name = os.environ.get("FIRESTORE_DB_NAME", "lobster-main")
            DB._client = firestore.Client(project=project_id, database=db_name)
        return DB._client

    # ------------------------------------------------------------------
    # Get Task
    # ------------------------------------------------------------------

    @staticmethod
    def get_task(task_id: int) -> Optional[Task]:
        db = DB.get_client()
        task_id_str = str(task_id)
        doc = db.collection("tasks").document(task_id_str).get()
        if not doc.exists:
            return None

        data = doc.to_dict() or {}
        return Task(**data)

    # ------------------------------------------------------------------
    # Task Creation
    # ------------------------------------------------------------------
    @staticmethod
    def create_task(task: Task) -> None:
        """
        Create task + queue docs.
        Engineering rule: any new task enters the system as PENDING.
        """
        db = DB.get_client()
        task_id = str(task.task_id)

        now = firestore.SERVER_TIMESTAMP

        db.collection("tasks").document(task_id).set({
            "task_id": task.task_id,
            "source": task.source,
            "requester_id": task.requester_id,
            "channel_id": task.channel_id,
            "description": task.description,

            # Force PENDING on ingestion
            "status": TASK_PENDING,

            "branch_name": task.branch_name,
            "plan_json": task.plan_json,
            "result_summary": task.result_summary,
            "cost_json": task.cost_json,
            "meta_json": getattr(task, "meta_json", None),

            "created_at": now,
            "updated_at": now,
        })

        db.collection("command_queue").document(task_id).set({
            "task_id": task.task_id,
            "status": TASK_PENDING,
            "created_at": now,
            "locked_by": None,
            "locked_at": None,
            "attempts": 0,
            "retryable": False,
        })

        DB.emit_event(int(task.task_id), "TASK_CREATED", {"task_id": int(task.task_id)})

    @staticmethod
    def create_task_from_command(cmd: dict, source: str) -> int:
        """
        Legacy wrapper for Discord gateways or older entry points.
        Internally calls create_task.
        """
        import time
        import random
        # Generates a randomized integer ID to simulate auto-increment / numeric primary keys
        task_id = int(time.time() * 1000) % 1000000000 + random.randint(0, 999)
        from workflows.models.task import Task
        task = Task(
            task_id=task_id,
            source=source,
            requester_id=cmd.get("requester_id", "unknown"),
            channel_id=cmd.get("channel_id", "unknown"),
            description=cmd.get("description", "No description provided")
        )
        DB.create_task(task)
        return task_id

    # ------------------------------------------------------------------
    # Lock Next Pending Task (Atomic)
    # ------------------------------------------------------------------
    
    @staticmethod
    def lock_next_pending_task(lock_owner: str) -> Optional[Dict[str, Any]]:
        """
        Two-step lock pattern:
        1) Query outside transaction to pick a candidate doc (FIFO by created_at).
        2) Transaction locks ONLY the specific document (point read + update).
        Also updates tasks/{task_id} status in the SAME transaction for consistency.
        """

        db = DB.get_client()
        queue_ref = db.collection("command_queue")

        # Step 1: read-only query OUTSIDE transaction (FIFO)
        docs = list(
            queue_ref
            .where("status", "==", "PENDING")
            .order_by("created_at")
            .limit(1)
            .stream()
        )
        if not docs:
            return None

        target_doc = docs[0]
        target_ref = target_doc.reference
        task_id_str = target_doc.id

        transaction = db.transaction()

        @firestore.transactional
        def txn(transaction):
            snap = target_ref.get(transaction=transaction)
            if not snap.exists:
                return None

            data = snap.to_dict() or {}
            if data.get("status") != "PENDING":
                # someone else took it
                return None

            current_attempts = int(data.get("attempts") or 0)

            now = firestore.SERVER_TIMESTAMP

            # Update command_queue atomically
            transaction.update(target_ref, {
                "status": "RUNNING",
                "locked_by": lock_owner,
                "locked_at": now,
                "attempts": current_attempts + 1,
            })

            # Update tasks status in SAME transaction (strong consistency)
            task_ref = db.collection("tasks").document(task_id_str)
            transaction.update(task_ref, {
                "status": "RUNNING",
                "updated_at": now,
            })

            # Emit event (optional; best-effort inside transaction is OK if your emit_event writes elsewhere)
            # If your emit_event writes to Firestore, DO NOT call it here.
            return {"task_id": int(task_id_str)}

        try:
            return txn(transaction)
        except Exception as e:
            logging.error(f"Two-step lock transaction failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Settlement: COMPLETED (Atomic)
    # ------------------------------------------------------------------
    @staticmethod
    def mark_task_completed(task_id: int, result_summary: Dict[str, Any], cost_json: Dict[str, Any]) -> None:
        db = DB.get_client()
        task_id_str = str(task_id)

        task_ref = db.collection("tasks").document(task_id_str)
        queue_ref = db.collection("command_queue").document(task_id_str)
        events_ref = task_ref.collection("events")

        transaction = db.transaction()

        @firestore.transactional
        def txn(transaction: firestore.Transaction):
            task_doc = task_ref.get(transaction=transaction)
            queue_doc = queue_ref.get(transaction=transaction)

            if not task_doc.exists or not queue_doc.exists:
                raise RuntimeError("Task or command_queue doc missing")

            task_data = task_doc.to_dict() or {}
            if task_data.get("status") != TASK_RUNNING:
                raise RuntimeError(f"Invalid state transition: {task_data.get('status')} -> DONE")

            now = firestore.SERVER_TIMESTAMP

            transaction.update(task_ref, {
                "status": TASK_DONE,
                "result_summary": result_summary or {},
                "cost_json": cost_json or {},
                "updated_at": now,
            })

            transaction.update(queue_ref, {
                "status": TASK_DONE,
                "locked_by": None,
                "locked_at": None,
            })

            # Event (in same transaction for audit consistency)
            event_id = str(uuid.uuid4())
            transaction.set(events_ref.document(event_id), {
                "ts": now,
                "event_type": "TASK_COMPLETED",
                "payload_json": {
                    "result_summary": result_summary or {},
                    "cost_json": cost_json or {},
                },
            })

        txn(transaction)

    @staticmethod
    def mark_task_done(task_id: int) -> None:
        """
        Wrapper to match task_manager.py: DB.mark_task_done(task_id)
        """
        DB.mark_task_completed(task_id, result_summary={}, cost_json={})

    # ------------------------------------------------------------------
    # Settlement: FAILED (Atomic)
    # ------------------------------------------------------------------
    @staticmethod
    def mark_task_failed(
        task_id: int,
        error_context: Any,
        retryable: bool = False,
    ) -> None:
        db = DB.get_client()
        task_id_str = str(task_id)

        task_ref = db.collection("tasks").document(task_id_str)
        queue_ref = db.collection("command_queue").document(task_id_str)
        events_ref = task_ref.collection("events")

        transaction = db.transaction()

        @firestore.transactional
        def txn(transaction: firestore.Transaction):
            task_doc = task_ref.get(transaction=transaction)
            queue_doc = queue_ref.get(transaction=transaction)

            if not task_doc.exists or not queue_doc.exists:
                raise RuntimeError("Task or command_queue doc missing")

            task_data = task_doc.to_dict() or {}
            queue_data = queue_doc.to_dict() or {}

            if task_data.get("status") != TASK_RUNNING:
                raise RuntimeError(f"Invalid state transition: {task_data.get('status')} -> FAILED")

            attempts = int(queue_data.get("attempts") or 0)
            now = firestore.SERVER_TIMESTAMP

            transaction.update(task_ref, {
                "status": TASK_FAILED,
                "error_context": error_context or {},
                "updated_at": now,
            })

            transaction.update(queue_ref, {
                "status": TASK_FAILED,
                "locked_by": None,
                "locked_at": None,
                "retryable": bool(retryable),
                "attempts": attempts,  # attempts is incremented at lock time
            })

            event_id = str(uuid.uuid4())
            transaction.set(events_ref.document(event_id), {
                "ts": now,
                "event_type": "TASK_FAILED",
                "payload_json": {
                    "error_context": error_context or {},
                    "retryable": bool(retryable),
                    "attempts": attempts,
                },
            })

        txn(transaction)

    # ------------------------------------------------------------------
    # Event Logging (Best-effort)
    # ------------------------------------------------------------------
    @staticmethod
    def emit_event(task_id: int, event_type: str, payload_json: Dict[str, Any]) -> None:
        db = DB.get_client()
        task_id_str = str(task_id)

        task_ref = db.collection("tasks").document(task_id_str)
        events_ref = task_ref.collection("events")

        events_ref.document(str(uuid.uuid4())).set({
            "ts": firestore.SERVER_TIMESTAMP,
            "event_type": event_type,
            "payload_json": payload_json or {},
        })

    # ------------------------------------------------------------------
    # Stub: Update Task Cost (Mock Mode)
    # ------------------------------------------------------------------
    @staticmethod
    def update_task_cost(task_id: int, cost_json: dict) -> None:
        """
        Stub method for mock pipeline testing.
        In real mode this would update cost tracking.
        """
        return
