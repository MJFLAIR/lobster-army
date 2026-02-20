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
        
        instance.execute.assert_called_once_with(123)
        mock_db.mark_task_done.assert_called_once_with(123)
        mock_db.emit_event.assert_any_call(123, "TASK_START", {"task_id": 123})
        mock_db.emit_event.assert_any_call(123, "TASK_DONE", {"task_id": 123})

def test_task_worker_failure(mock_db):
    worker = TaskWorker()
    with patch("runtime.task_worker.TaskManager") as MockTM:
        instance = MockTM.return_value
        instance.execute.side_effect = Exception("Boom")
        
        worker.run_task(123)
        
        mock_db.mark_task_failed.assert_called_once_with(123, "Boom")
        mock_db.emit_event.assert_any_call(123, "TASK_FAILED", {"error": "Boom"})

def test_task_manager_flow(mock_db_manager):
    tm = TaskManager()
    mock_db_manager.get_task.return_value = {"id": 1, "status": "PENDING"}
    
    tm.execute(1)
    
    # Check events for PM, Code, Review
    calls = mock_db_manager.emit_event.call_args_list
    steps = [c[0][2]["step"] for c in calls if "step" in c[0][2]]
    assert "PM" in steps
    assert "Code" in steps
    assert "Review" in steps

def test_cron_tick_picks_task(mock_db_cron):
    mock_db_cron.lock_next_pending_task.return_value = {"task_id": 999}
    
    with patch("runtime.cron_tick.TaskWorker") as MockWorker:
        app = Flask(__name__)
        with app.app_context():
            resp = handle_tick()
            
            assert resp.json["picked"] == 1
            assert resp.json["task_id"] == 999
            MockWorker.return_value.run_task.assert_called_once_with(999)

def test_cron_tick_no_task(mock_db_cron):
    mock_db_cron.lock_next_pending_task.return_value = None
    
    with patch("runtime.cron_tick.TaskWorker") as MockWorker:
        app = Flask(__name__)
        with app.app_context():
            resp = handle_tick()
            
            assert resp.json["picked"] == 0
            MockWorker.return_value.run_task.assert_not_called()
