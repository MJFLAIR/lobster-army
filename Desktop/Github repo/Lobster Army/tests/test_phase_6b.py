import pytest
import json
from unittest.mock import patch
from workflows.task_manager import TaskManager
from tools.llm_client import LLMClient

# Test Data
PM_RESP = json.dumps({"choices": [{"message": {"content": '{"plan": []}'}}], "usage": {"total_tokens": 100}}).encode()
CODE_RESP = json.dumps({"choices": [{"message": {"content": '{"diff": "...", "commits": []}'}}], "usage": {"total_tokens": 200}}).encode()
REVIEW_RESP = json.dumps({"choices": [{"message": {"content": '{"status": "PASS", "score": 100}'}}], "usage": {"total_tokens": 50}}).encode()

@pytest.fixture
def mock_db(mock_task_factory):
     with patch("workflows.task_manager.DB") as mock_tm, \
          patch("tools.cost_tracker.DB") as mock_ct:
        mock_task = mock_task_factory(task_id=1, description="Phase 6B", cost_json={"tokens": 0})
        
        mock_tm.get_task.return_value = mock_task
        mock_ct.get_task.return_value = mock_task
        yield mock_tm

@patch.object(LLMClient, "complete")
def test_phase_6b_flow(mock_complete, mock_db):
    mock_complete.side_effect = [
        {"content": '{"plan": []}', "usage": {"total_tokens": 100}},
        {"content": '{"diff": "..."}', "usage": {"total_tokens": 200}},
        {"content": '{"status": "PASS", "score": 100}', "usage": {"total_tokens": 50}}
    ]

    tm = TaskManager()
    tm.execute(1)

    assert mock_complete.call_count == 3

@patch("workflows.task_manager.DB")
@patch("tools.cost_tracker.DB")
@patch.object(LLMClient, "complete")
def test_budget_enforcement(mock_complete, MockDB_CT, MockDB_TM, mock_task_factory):
    mock_complete.return_value = {
        "content": '{"plan": []}', 
        "usage": {"total_tokens": 999999}
    }
    
    # Initial state
    task_state = {"task_id": 2, "source": "test", "requester_id": "user", "description": "Budget Test", "cost_json": {"tokens": 0}}

    def get_task(tid):
        return mock_task_factory(
            task_id=task_state["task_id"], 
            description=task_state["description"], 
            cost_json=task_state["cost_json"],
            source=task_state["source"],
            requester_id=task_state["requester_id"]
        )
    
    def update_cost(tid, cost):
        task_state["cost_json"] = cost
        
    MockDB_TM.get_task.side_effect = get_task
    MockDB_CT.get_task.side_effect = get_task
    MockDB_CT.update_task_cost.side_effect = update_cost
    
    tm = TaskManager()
    
    with pytest.raises(RuntimeError, match="exceeded budget"):
        tm.execute(2)
        
    assert task_state["cost_json"]["tokens"] > 100000
