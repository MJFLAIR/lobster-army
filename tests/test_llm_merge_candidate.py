import pytest
from unittest.mock import patch, MagicMock
import json
from workflows.agents.llm_review_gate import run_llm_review

# 🛡️ 戰術後勤基地：標準化 LLM 彈藥庫 (支援自訂 Payload)
def setup_mock_llm(mock_llm_client, payload_dict):
    """集中管理 LLM 回傳的 Mock 結構，確保加上 "content" 裝甲與 json.dumps 實彈"""
    mock_instance = MagicMock()
    mock_llm_client.return_value = mock_instance
    mock_instance.complete.return_value = {
        "content": json.dumps(payload_dict)
    }
    return mock_instance

@patch("workflows.agents.llm_review_gate.merge_key_exists")
@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
@patch.dict('os.environ', {
    "GATE_SCORE_THRESHOLD": "0.75",
    "LLM_REVIEW_MODEL": "test-model",
    "LLM_REVIEW_PROVIDER": "test-provider"
})
def test_merge_candidate_emitted_on_approve(mock_emit, mock_llm_client, mock_merge_key_exists):
    mock_merge_key_exists.return_value = False
    
    # 🚀 裝載標準彈藥：高分通過 (Approve)
    setup_mock_llm(mock_llm_client, {"decision": "approve", "score": 0.9, "reason": "looks good"})

    # Run the function
    res = run_llm_review("123", {})

    # Verify result
    assert res["decision"] == "approve"
    assert res["score"] == 0.9

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    
    assert "PR_LLM_REVIEW" in events
    assert "PR_LLM_APPROVE" in events
    assert "MERGE_CANDIDATE" in events

    # Check MERGE_CANDIDATE payload
    merge_candidate_call = [c for c in calls if c[0][1] == "MERGE_CANDIDATE"][0]
    payload = merge_candidate_call[0][2]
    assert payload["score"] == 0.9
    assert "threshold" in payload
    assert payload["proposal"] == "deterministic_llm_pass"
    
    # Check policy snapshot
    snap = payload["policy_snapshot"]
    assert snap["policy_version"] == "phase_b5"
    assert snap["threshold"] == 0.75
    assert snap["threshold_raw"] == "0.75"
    assert snap["llm_model"] == "test-model"
    assert snap["llm_provider"] == "test-provider"

@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
def test_merge_candidate_not_emitted_on_approve_low_score(mock_emit, mock_llm_client):
    # 🚀 裝載標準彈藥：分數不達標 (Low Score)
    setup_mock_llm(mock_llm_client, {"decision": "approve", "score": 0.5, "reason": "maybe"})

    # Run the function with a higher threshold environment variable (implicitly default 0.75 > 0.5)
    res = run_llm_review("123", {})

    # Verify result
    assert res["decision"] == "approve"
    assert res["score"] == 0.5

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    
    assert "PR_LLM_REVIEW" in events
    assert "PR_LLM_REJECT" in events
    assert "PR_LLM_APPROVE" not in events
    assert "MERGE_CANDIDATE" not in events

@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
def test_merge_candidate_not_emitted_on_reject(mock_emit, mock_llm_client):
    # 🚀 裝載標準彈藥：明確拒絕 (Reject)
    setup_mock_llm(mock_llm_client, {"decision": "reject", "score": 0.2, "reason": "bad"})

    # Run the function
    res = run_llm_review("123", {})

    # Verify result
    assert res["decision"] == "reject"
    assert res["score"] == 0.2

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    
    assert "PR_LLM_REVIEW" in events
    assert "PR_LLM_REJECT" in events
    assert "MERGE_CANDIDATE" not in events

@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
def test_merge_candidate_not_emitted_on_invalid_schema(mock_emit, mock_llm_client):
    # 🚀 裝載標準彈藥：Schema 錯誤 (Invalid Schema)
    setup_mock_llm(mock_llm_client, {"bad": "schema"})

    # Run the function
    res = run_llm_review("123", {})

    # Verify result
    assert res["decision"] == "reject"

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    
    assert "PR_LLM_REVIEW" in events
    assert "PR_LLM_REJECT" in events
    assert "MERGE_CANDIDATE" not in events

@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
def test_merge_candidate_not_emitted_on_exception(mock_emit, mock_llm_client):
    # 🛡️ 模擬核心崩潰：不使用彈藥庫，直接掛載 Exception 炸彈
    mock_instance = MagicMock()
    mock_llm_client.return_value = mock_instance
    mock_instance.complete.side_effect = Exception("Boom")

    # Run the function
    res = run_llm_review("123", {})

    # Verify result
    assert res["decision"] == "reject"

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    
    assert "PR_LLM_REVIEW" in events
    assert "PR_LLM_EXCEPTION" in events
    assert "MERGE_CANDIDATE" not in events