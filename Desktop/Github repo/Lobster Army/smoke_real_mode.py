import os

print("Starting smoke test...")

os.environ["LLM_MODE"] = "real"

from workflows.models.task import Task
from workflows.storage.db import DB
from runtime.task_worker import TaskWorker

TEST_TASK_ID = 9100

task = Task(
    task_id=TEST_TASK_ID,
    source="manual",
    requester_id="local",
    description="Plan steps to create a simple Python hello world script. Output JSON with key 'plan'."
)

print("Creating task...")
DB.create_task(task)

print("Locking task...")
DB.lock_next_pending_task(lock_owner="local-test")

print("Running worker...")
worker = TaskWorker()
worker.run_task(TEST_TASK_ID)

print("Done.")