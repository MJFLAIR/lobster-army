import os
import pytest
from unittest.mock import patch, MagicMock

import scripts.inject_real_task as irt
from workflows.storage.db import DB

# 嘗試載入 Phase 1 升級的 Task Dataclass
try:
    from workflows.models.task import Task
except ImportError:
    Task = None

# 🛡️ 龍蝦軍團專屬：虛擬記憶體資料庫 (攔截所有 I/O 但保留完整 Context)
_MOCK_FIRESTORE_DB = {}

def mock_create_task(payload, *args, **kwargs):
    """攔截建立任務，將真實的 prompt 存入虛擬 DB"""
    task_id = payload.get("task_id") if isinstance(payload, dict) else getattr(payload, "task_id", "test_id")
    _MOCK_FIRESTORE_DB[task_id] = payload

def mock_get_task(task_id, *args, **kwargs):
    """攔截讀取任務，根據 Phase 1 規格回傳 Task 物件，而非 dict"""
    data = _MOCK_FIRESTORE_DB.get(task_id, {})
    if Task and isinstance(data, dict):
        return Task(**data)  # 完美轉換為 Dataclass，防止 AttributeError
    else:
        # Fallback: 如果沒有 Task class，用 MagicMock 模擬 Object attribute access
        mock_obj = MagicMock()
        import dataclasses
        iterable_data = dataclasses.asdict(data) if dataclasses.is_dataclass(data) else data
        for k, v in iterable_data.items():
            setattr(mock_obj, k, v)
        return mock_obj

@pytest.fixture(autouse=True)
def seal_sandbox_and_force_mock():
    original_llm_mode = os.environ.get("LLM_MODE")
    os.environ["LLM_MODE"] = "mock"
    
    _MOCK_FIRESTORE_DB.clear()  # 每次測試前清理戰場

    # 🔥 神級精準打擊：使用 side_effect 動態處理 I/O
    with patch.object(irt.DB, "create_task", side_effect=mock_create_task), \
         patch.object(DB, "create_task", side_effect=mock_create_task), \
         patch.object(DB, "get_task", side_effect=mock_get_task), \
         patch.object(DB, "emit_event", return_value=None), \
         patch.object(DB, "mark_task_completed", return_value=None, create=True), \
         patch.object(DB, "mark_task_failed", return_value=None, create=True):
        yield

    # 🧹 清理戰場
    if original_llm_mode is None:
        os.environ.pop("LLM_MODE", None)
    else:
        os.environ["LLM_MODE"] = original_llm_mode


@pytest.mark.integration
def test_real_task_case_a_success():
    trace = irt.inject_task(
        "fibonacci_success",
        "code_generation",
        "Write a Python script that calculates the Fibonacci sequence up to 10 terms and save it to sandbox/fib.py"
    )

    assert trace["final_status"] == "SUCCESS"
    assert "PMAgent" in trace["steps"]
    assert "Feature_Coder" in trace["steps"]
    assert "Reviewer" in trace["steps"]
    assert trace["self_healing_triggered"] is False
    assert any(
        action.get("tool_name") == "write_file" and action.get("status") == "success"
        for action in trace.get("tool_actions", [])
    )
    assert len(trace["sandbox_write_paths"]) > 0


@pytest.mark.integration
def test_real_task_case_b_heal():
    trace = irt.inject_task(
        "review_fail_then_heal",
        "code_generation",
        "Write fibonacci using recursion AND handle n > 10^6 efficiently without increasing recusion limit AND support imaginary negative inputs. Save it to sandbox/fib_broken.py"
    )

    assert "Reviewer" in trace["steps"]
    assert trace["self_healing_triggered"] is True
    assert "AutoFix_Medic" in trace["steps"]


@pytest.mark.integration
def test_real_task_case_c_sandbox_violation():
    trace = irt.inject_task(
        "tool_failure_test",
        "code_generation",
        "Generate a fibonacci sequence and strictly save it to ../outside.py"
    )

    assert trace["final_status"] == "FAILED"
    assert "error" in trace
    assert "SANDBOX_VIOLATION" in trace["error"]
    assert any("../" in p for p in trace["sandbox_write_paths"])