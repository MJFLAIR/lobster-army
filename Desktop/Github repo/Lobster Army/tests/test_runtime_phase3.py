import pytest
from unittest.mock import patch
from runtime.task_worker import TaskWorker
from workflows.task_manager import TaskManager
from runtime.cron_tick import handle_tick
from flask import Flask

@pytest.fixture
def mock_db():
    # Patch the DB class imported in runtime.task_worker
    with patch("runtime.task_worker.DB") as mock:
        yield mock

@pytest.fixture
def mock_db_manager():
    # Patch the DB class imported in workflows.task_manager
    with patch("workflows.task_manager.DB") as mock:
        yield mock

@pytest.fixture
def mock_db_cron():
    # Patch the DB class imported in runtime.cron_tick
    with patch("runtime.cron_tick.DB") as mock:
        yield mock

def test_task_worker_success(mock_db):
    worker = TaskWorker()
    with patch("runtime.task_worker.TaskManager") as MockTM:
        instance = MockTM.return_value
        worker.run_task(123)
        
        instance.execute.assert_called_with(123)
        # Check that emit_event was called with TASK_START and TASK_DONE (or EXECUTION_STARTED/EXECUTION_FINISHED)
        emit_calls = [call[0][1] for call in mock_db.emit_event.call_args_list]
        assert "EXECUTION_STARTED" in emit_calls
        assert "EXECUTION_FINISHED" in emit_calls

def test_task_worker_failure(mock_db):
    worker = TaskWorker()
    with patch("runtime.task_worker.TaskManager") as MockTM:
        instance = MockTM.return_value
        instance.execute.side_effect = Exception("Boom")
        
        with pytest.raises(Exception, match="Boom"):
            worker.run_task(123)
        # Note: TaskWorker doesn't catch exceptions natively in run_task; it bubbles up to cron_tick

def test_task_manager_flow(mock_db_manager):
    tm = TaskManager()
    
    from workflows.models.task import Task
    mock_db_manager.get_task.return_value = Task(
        task_id=1,
        source="test",
        requester_id="user",
        description="test",
        status="PENDING",
        branch_name="test-branch"
    )
    
    with patch("tools.cost_tracker.DB") as mock_db_cost:
        mock_db_cost.get_task.return_value = mock_db_manager.get_task.return_value
        tm.execute(1)
    
    # Check events for PM, Code, Review
    calls = mock_db_manager.emit_event.call_args_list
    steps = [c[0][2]["step"] for c in calls if "step" in c[0][2]]
    assert "PM" in steps
    assert "Code" in steps
    assert "Review" in steps

def test_cron_tick_picks_task(mock_db_cron):
    mock_db_cron.lock_next_pending_task.return_value = {"task_id": 999, "status": "PENDING"}
    
    with patch("runtime.cron_tick.TaskWorker") as MockWorker:
        app = Flask(__name__)
        with app.app_context():
            resp = handle_tick()
            
            data = resp[0].get_json()
            assert data["picked"] == 1
            assert data["task_id"] == 999
            MockWorker.return_value.run_task.assert_called_once_with(999)

def test_cron_tick_no_task(mock_db_cron):
    mock_db_cron.lock_next_pending_task.return_value = None
    
    with patch("runtime.cron_tick.TaskWorker") as MockWorker:
        app = Flask(__name__)
        with app.app_context():
            resp = handle_tick()
            
            data = resp[0].get_json()
            assert data["picked"] == 0
            MockWorker.return_value.run_task.assert_not_called()
