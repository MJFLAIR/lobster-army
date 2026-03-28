from datetime import datetime
from workflows.storage.db import DB
from workflows.models.task import Task

task = Task(
    task_id=1016,
    source="debug",
    requester_id="local",
    channel_id="local",
    description="test execution",
    status="PENDING",
    branch_name=None,
    plan_json=None,
    result_summary=None,
    cost_json=None,
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
)

DB.create_task(task)

print("Task 1016 created.")