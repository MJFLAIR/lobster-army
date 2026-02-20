import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_task_factory():
    def _factory(**kwargs):
        task = MagicMock()
        # Required fields default values
        task.task_id = kwargs.get("task_id", 1)
        task.source = kwargs.get("source", "test_source")
        task.requester_id = kwargs.get("requester_id", "test_user")
        
        # Optional fields default values
        task.channel_id = kwargs.get("channel_id", "test_channel")
        task.description = kwargs.get("description", "test_description")
        task.status = kwargs.get("status", "PENDING")
        task.branch_name = kwargs.get("branch_name", f"task/{task.task_id}")
        task.plan_json = kwargs.get("plan_json", {})
        task.result_summary = kwargs.get("result_summary", None)
        task.cost_json = kwargs.get("cost_json", {"tokens": 0})
        
        # Datetime fields (mocked as strings or objects if needed, but simple attribute is enough for now)
        task.created_at = kwargs.get("created_at", "2024-01-01T00:00:00Z")
        task.updated_at = kwargs.get("updated_at", "2024-01-01T00:00:00Z")
        
        return task
    return _factory
