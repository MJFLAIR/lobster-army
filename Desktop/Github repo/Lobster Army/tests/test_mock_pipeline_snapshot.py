import os
import pytest
from unittest.mock import patch
import uuid
from typing import Optional, Dict, Any

# Must use MOCK_MODE=mock as per prompt
os.environ["LLM_MODE"] = "mock"

from workflows.models.task import Task
from workflows.storage.db import DB
from runtime.task_worker import TaskWorker
from google.cloud import firestore

# --- Minimal Test Helper Functions (Fake Firestore Client) ---
class FakeDocSnap:
    def __init__(self, data=None, doc_id="mock_id"):
        self.exists = data is not None
        self._d = data or {}
        self._id = doc_id

    def to_dict(self):
        return self._d.copy()

    @property
    def id(self):
        return self._id

class FakeDocRef:
    def __init__(self, db, path):
        self.db = db
        self.path = path
        self.id = path.split("/")[-1]

    def set(self, data):
        self.db.data[self.path] = dict(data)

    def update(self, data):
        if self.path not in self.db.data:
            self.db.data[self.path] = {}
        for k, v in data.items():
            self.db.data[self.path][k] = v

    def get(self, transaction=None):
        return FakeDocSnap(self.db.data.get(self.path), doc_id=self.id)

    def collection(self, sub_name):
        return FakeCollection(self.db, f"{self.path}/{sub_name}")

class FakeCollection:
    def __init__(self, db, coll_path):
        self.db = db
        self.coll_path = coll_path

    def document(self, doc_id=None):
        if not doc_id:
            doc_id = str(uuid.uuid4())
        return FakeDocRef(self.db, f"{self.coll_path}/{doc_id}")

class FakeTransaction:
    def update(self, ref, data):
        ref.update(data)
    def set(self, ref, data):
        ref.set(data)

class FakeFirestoreClient:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        return FakeCollection(self, name)

    def transaction(self):
        return FakeTransaction()

# Remove the real @firestore.transactional decorator behavior to just call the function
def mock_transactional(txn_func):
    def wrapper(transaction, *args, **kwargs):
        return txn_func(transaction, *args, **kwargs)
    return wrapper

@pytest.fixture(autouse=True)
def mock_firestore():
    fake_client = FakeFirestoreClient()
    with patch("workflows.storage.db.DB.get_client", return_value=fake_client), \
         patch("google.cloud.firestore.transactional", mock_transactional):
        
        # We need to manually fix TASK_RUNNING if we don't start it that way
        # Actually lock_next_pending_task usually sets it to RUNNING. 
        # But here we bypass cron_tick, so TaskManager might expect TASK_RUNNING?
        # Let's see if TaskManager checks status. TaskManager just does:
        # task = DB.get_task(task_id); if not task: raise Error;
        # Then PM -> Code -> Review -> DB.mark_task_done.
        # Wait, DB.mark_task_done calls DB.mark_task_completed, which asserts task is RUNNING!
        # Oh, if it wasn't RUNNING, DB.mark_task_completed raises Invalid state transition!
        # So we MUST set it to RUNNING before calling TaskWorker.run_task or TaskManager.execute
        yield fake_client

# --- Test Case ---
def test_mock_pipeline_snapshot(mock_firestore):
    # STEP 1 & 2: Create Test Task
    task_id = 999
    now = "MOCK_TIMESTAMP"
    t = Task(
        task_id=task_id,
        source="test",
        requester_id="local",
        description="Write a hello world program in Python",
    )
    
    # Use real DB class to create, but with fake firestore
    DB.create_task(t)

    # Since we are bypassing `lock_next_pending_task` (which cron_tick calls), 
    # we need to manually set it to "RUNNING" because `DB.mark_task_done` requires state to be "RUNNING".
    mock_firestore.data[f"tasks/{task_id}"]["status"] = "RUNNING"
    mock_firestore.data[f"command_queue/{task_id}"]["status"] = "RUNNING"

    # Execute workflow (No HTTP, No Flask)
    # LLMClient in task_manager accesses self.mock_mode = True automatically internally
    worker = TaskWorker()
    worker.run_task(task_id)

    # STEP 3: Read back task and events
    task_doc = mock_firestore.data.get(f"tasks/{task_id}", {})
    cmd_doc = mock_firestore.data.get(f"command_queue/{task_id}", {})
    
    # Get events from fake DB dict keys that look like tasks/999/events/{uuid}
    events = [
        val for key, val in mock_firestore.data.items()
        if key.startswith(f"tasks/{task_id}/events/")
    ]

    # STEP 4: Assertions
    assert task_doc.get("status") == "DONE", "Task status should be DONE"
    assert cmd_doc.get("status") == "DONE", "Command Queue status should be DONE"
    
    has_completion_event = any(e.get("event_type") == "TASK_COMPLETED" for e in events)
    assert has_completion_event, "Should contain TASK_COMPLETED event"
