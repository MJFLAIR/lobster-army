import pytest
from unittest.mock import patch, MagicMock
from workflows.agents.llm_review_gate import run_llm_review, build_merge_key

@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
@patch("workflows.agents.llm_review_gate.merge_key_exists")
@patch.dict('os.environ', {
    "GATE_SCORE_THRESHOLD": "0.75",
    "LLM_REVIEW_MODEL": "test-model",
    "LLM_REVIEW_PROVIDER": "test-provider"
})
def test_idempotency_emits_on_first_pass(mock_exists, mock_emit, mock_llm_client):
    mock_exists.return_value = False
    
    # Setup mock LLM response
    mock_instance = MagicMock()
    mock_llm_client.return_value = mock_instance
    mock_instance.complete.return_value = {"decision": "approve", "score": 0.9, "reason": "looks good"}

    # Run the function
    res = run_llm_review("123", {})

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "MERGE_CANDIDATE" in events

@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
@patch("workflows.agents.llm_review_gate.merge_key_exists")
@patch.dict('os.environ', {
    "GATE_SCORE_THRESHOLD": "0.75",
    "LLM_REVIEW_MODEL": "test-model",
    "LLM_REVIEW_PROVIDER": "test-provider"
})
def test_idempotency_does_not_emit_on_duplicate(mock_exists, mock_emit, mock_llm_client):
    mock_exists.return_value = True
    
    # Setup mock LLM response
    mock_instance = MagicMock()
    mock_llm_client.return_value = mock_instance
    mock_instance.complete.return_value = {"decision": "approve", "score": 0.9, "reason": "looks good"}

    # Run the function
    res = run_llm_review("123", {})

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "MERGE_CANDIDATE" not in events


@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
@patch("workflows.agents.llm_review_gate.merge_key_exists")
@patch.dict('os.environ', {
    "GATE_SCORE_THRESHOLD": "0.50",
    "LLM_REVIEW_MODEL": "test-model",
    "LLM_REVIEW_PROVIDER": "test-provider"
})
def test_idempotency_emits_on_threshold_change(mock_exists, mock_emit, mock_llm_client):
    mock_exists.return_value = False
    
    # Setup mock LLM response
    mock_instance = MagicMock()
    mock_llm_client.return_value = mock_instance
    mock_instance.complete.return_value = {"decision": "approve", "score": 0.9, "reason": "looks good"}

    # Run the function
    res = run_llm_review("123", {})

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "MERGE_CANDIDATE" in events

@patch("llm.factory.create_llm")
@patch("workflows.agents.llm_review_gate.DB.emit_event")
@patch("workflows.agents.llm_review_gate.merge_key_exists")
@patch.dict('os.environ', {
    "GATE_SCORE_THRESHOLD": "0.75",
    "LLM_REVIEW_MODEL": "new-test-model",
    "LLM_REVIEW_PROVIDER": "test-provider"
})
def test_idempotency_emits_on_model_change(mock_exists, mock_emit, mock_llm_client):
    mock_exists.return_value = False
    
    # Setup mock LLM response
    mock_instance = MagicMock()
    mock_llm_client.return_value = mock_instance
    mock_instance.complete.return_value = {"decision": "approve", "score": 0.9, "reason": "looks good"}

    # Run the function
    res = run_llm_review("123", {})

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "MERGE_CANDIDATE" in events

def test_build_merge_key_deterministic():
    snapshot = {"policy_version": "phase_b5", "llm_model": "test-model"}
    key1 = build_merge_key("1", "approve", 0.9, 0.75, snapshot)
    key2 = build_merge_key("1", "approve", 0.9, 0.75, snapshot)
    assert key1 == key2

    key3 = build_merge_key("1", "approve", 0.9, 0.8, snapshot)
    assert key1 != key3

