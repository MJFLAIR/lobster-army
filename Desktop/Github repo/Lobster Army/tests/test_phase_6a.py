import pytest
from unittest.mock import patch, MagicMock
from workflows.task_manager import TaskManager
from workflows.agents.pm_agent import PMAgent

@pytest.fixture
def mock_db_manager(mock_task_factory):
    # Patch DB in both modules
    with patch("workflows.task_manager.DB") as mock_db_tm, \
         patch("tools.cost_tracker.DB") as mock_db_ct:
        
        mock_task = mock_task_factory(task_id=1, description="test", cost_json={"tokens": 0})
        
        mock_db_tm.get_task.return_value = mock_task
        mock_db_ct.get_task.return_value = mock_task
        
        yield mock_db_tm

# Helper to mock LLMClient complete
@pytest.fixture
def mock_llm_client():
    with patch("workflows.task_manager.LLMClient") as mock:
        yield mock

def test_retry_logic(mock_db_manager):
    # Test BaseAgent retry
    # Mock LLM to fail twice (bad json), then succeed
    mock_llm = MagicMock()
    mock_llm.complete.side_effect = [
        {"content": "BAD_JSON"},
        {"content": '{"plan": []}'}, # Valid PM response
    ]
    
    # We use PMAgent to test BaseAgent logic
    agent = PMAgent(mock_llm, 123)
    
    # Run
    res = agent.run({"description": "test"})
    
    assert res["plan"] == []
    assert mock_llm.complete.call_count == 2 # 2 attempts

def test_schema_validation_failure(mock_db_manager):
    # Test BaseAgent gives up after retries if schema is always bad
    mock_llm = MagicMock()
    mock_llm.complete.return_value = {"content": '{"wrong_field": 1}'} # Valid JSON, Invalid Schema for PMAgent
    
    agent = PMAgent(mock_llm, 123)
    
    with pytest.raises(Exception, match="Schema Error"):
        agent.run({"description": "test"})
    
    # Should equal max_retries (default 3)
    assert mock_llm.complete.call_count == 3


@patch("workflows.task_manager.DB")
@patch("tools.cost_tracker.DB")
@patch("workflows.task_manager.LLMClient") # Patched for Phase 6B
def test_escalation_policy(MockLLMClass, MockDB_CT, MockDB_TM, mock_task_factory):
    # Test Max Cycles reached
    # Setup LLM to always return FAIL for Review
    instance = MockLLMClass.return_value
    
    # PM returns plan
    # Code returns diff
    # Review returns FAIL
    
    def side_effect(prompt, system=""):
        if "Product Manager" in system:
            return {"content": '{"plan": []}'}
        if "Senior Python Engineer" in system:
             return {"content": '{"diff": "...", "commits": []}'}
        if "Code Reviewer" in system:
             return {"content": '{"status": "FAIL", "score": 0, "comments": "Bad"}'}
        return {}

    instance.complete.side_effect = side_effect
    
    mock_task = mock_task_factory(task_id=1, description="test", cost_json={"tokens": 0})
    MockDB_TM.get_task.return_value = mock_task
    MockDB_CT.get_task.return_value = mock_task
    
    tm = TaskManager()
    
    with pytest.raises(RuntimeError, match="Escalation: Task failed after 3 cycles"):
        tm.execute(1)

    # Verify calls
    assert instance.complete.call_count >= 7
    MockDB_TM.mark_task_failed.assert_called()

@patch("workflows.task_manager.DB")
@patch("tools.cost_tracker.DB")
@patch("workflows.task_manager.LLMClient")
def test_successful_cycle(MockLLMClass, MockDB_CT, MockDB_TM, mock_task_factory):
    # Return PASS on first review
    instance = MockLLMClass.return_value
    
    def side_effect(prompt, system=""):
        if "Product Manager" in system:
            return {"content": '{"plan": []}'}
        if "Senior Python Engineer" in system:
             return {"content": '{"diff": "...", "commits": []}'}
        if "Code Reviewer" in system:
             return {"content": '{"status": "PASS", "score": 90}'}
        return {}

    instance.complete.side_effect = side_effect
    
    mock_task = mock_task_factory(task_id=1, description="test", cost_json={"tokens": 0})
    MockDB_TM.get_task.return_value = mock_task
    MockDB_CT.get_task.return_value = mock_task
    
    tm = TaskManager()
    tm.execute(1)
    
    MockDB_TM.mark_task_done.assert_called_with(1)
