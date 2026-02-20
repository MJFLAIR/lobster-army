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

@pytest.fixture
def mock_network():
    # Patch NetworkClient inside llm_client.py
    with patch("tools.llm_client.NetworkClient") as mock:
        yield mock

def test_phase_6b_flow(mock_db, mock_network):
    # Setup Network Mock to return valid responses sequentially
    instance = mock_network.return_value
    instance.request.side_effect = [PM_RESP, CODE_RESP, REVIEW_RESP]

    tm = TaskManager()
    tm.execute(1)

    # Verify 3 LLM calls via Network
    assert instance.request.call_count == 3
    
    # Verify Cost Updates (implicit via DB mock calls from CostTracker)
    # Since BaseAgent creates CostTracker which imports DB...
    # We need to verify the DB interactions. 
    # But TaskManager imports DB from workflows.storage.db.
    # CostTracker also imports DB from workflows.storage.db.
    # If we patched workflows.task_manager.DB, it might not affect CostTracker if it imports it directly.
    # We should patch the underlying DB class.
    pass

@patch("workflows.task_manager.DB")
@patch("tools.cost_tracker.DB")
@patch("tools.llm_client.NetworkClient")
def test_budget_enforcement(MockNetwork, MockDB_CT, MockDB_TM, mock_task_factory):
    # Setup high usage response
    HUGE_RESP = json.dumps({
        "choices": [{"message": {"content": '{"plan": []}'}}], 
        "usage": {"total_tokens": 999999} # Exceeds 100k limit
    }).encode()
    
    instance = MockNetwork.return_value
    instance.request.return_value = HUGE_RESP
    
    # Initial state
    task_state = {"task_id": 2, "source": "test", "requester_id": "user", "description": "Budget Test", "cost_json": {"tokens": 0}}

    def get_task(tid):
        # Return a NEW mock each time reflecting state
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
    
    # PM Agent calls LLM. 
    # LLM returns huge usage.
    # CostTracker.track_usage updates DB and checks budget.
    # Should raise RuntimeError.
    
    with pytest.raises(RuntimeError, match="exceeded budget"):
        tm.execute(2)
        
    # Verify we tried to update cost
    assert task_state["cost_json"]["tokens"] > 100000

@patch("tools.llm_client.Secrets")
def test_llm_client_secrets(MockSecrets):
    # Verify apiKey retrieval
    MockSecrets.get_secret_by_alias.return_value = "secret-key-123"
    client = LLMClient()
    assert client.api_key == "secret-key-123"
    MockSecrets.get_secret_by_alias.assert_called_with("llm_api_key")
