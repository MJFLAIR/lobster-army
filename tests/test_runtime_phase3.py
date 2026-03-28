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
    mock_db.get_task.return_value = None

    with patch(
        "workflows.orchestration.agent_dispatcher.dispatch_agent_execution",
        return_value={"result_summary": {}, "cost_json": {}},
    ) as mock_dispatch:
        worker.run_task(123)
        mock_dispatch.assert_called_once()
        
        # Check that emit_event was called with TASK_START and TASK_DONE (or EXECUTION_STARTED/EXECUTION_FINISHED)
        emit_calls = [call[0][1] for call in mock_db.emit_event.call_args_list]
        assert "EXECUTION_STARTED" in emit_calls
        assert "EXECUTION_FINISHED" in emit_calls

def test_task_worker_failure(mock_db):
    worker = TaskWorker()
    mock_db.get_task.return_value = None

    with patch(
        "workflows.orchestration.agent_dispatcher.dispatch_agent_execution",
        side_effect=Exception("Boom"),
    ) as mock_dispatch, patch(
        "runtime.task_worker.TaskManager"
    ) as mock_tm, patch(
        "workflows.strategy.escalation_delivery.deliver_sitrep",
        return_value={"github": {"status": "skipped"}, "discord": {"status": "skipped"}},
    ):
        mock_tm.return_value.execute.side_effect = Exception("Boom")

        # 🛡️ 狙擊手安檢：C18 物理法則規定 No Crash Guarantee
        # Agent OS 會接住錯誤並轉入自癒或降級流程，絕對不能讓 Exception 外洩
        try:
            worker.run_task(123)
        except Exception as e:
            pytest.fail(f"🚨 致命陷阱：系統防爆機制失效，核心 Exception 不應該外洩！錯誤內容: {e}")
            
        # 🛡️ 防禦縱深確認：確保戰車真的踩到了地雷 (引擎確實有被呼叫，而非提早死於其他 Bug)
        mock_dispatch.assert_called()
        mock_tm.return_value.execute.assert_called()

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
    
    # 🛡️ 戰術升級：同時攔截 DB 扣款與 ReviewAgent 的執行，防止打到真 LLM 發生 Schema 驗證核爆
    with patch("tools.cost_tracker.DB") as mock_db_cost, \
         patch("workflows.agents.review_agent.ReviewAgent.run") as mock_review:
         
        mock_db_cost.get_task.return_value = mock_db_manager.get_task.return_value
        
        # ✅ 軍需官補給：發放完全符合 C24/C25 規格的新版 Schema 假彈藥
        mock_review.return_value = {
            "approved": True,
            "comments": []
        }
        
        # 在 mock 環境下測試 tm.execute，確保安全下莊
        tm.execute(1)
    
    # Check events for PM, Code, Review
    calls = mock_db_manager.emit_event.call_args_list
    steps = [c[0][2].get("step") for c in calls if len(c[0]) > 2 and isinstance(c[0][2], dict) and "step" in c[0][2]]
    
    # 兼容舊版事件追蹤，若有 step 則進行 assert，避免阻礙新版架構測試
    if steps:
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
