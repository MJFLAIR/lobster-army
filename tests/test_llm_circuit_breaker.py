import os
import pytest
from unittest.mock import patch
import time

# Force environment for this test explicitly


from tools.llm_client import LLMClient

@pytest.fixture(autouse=True)
def reset_cb_state():
    """Reset the circuit breaker class state before each test."""
    LLMClient._cb_failures = 0
    LLMClient._cb_is_open = False
    LLMClient._cb_opened_at = 0.0
    yield
    LLMClient._cb_failures = 0
    LLMClient._cb_is_open = False
    LLMClient._cb_opened_at = 0.0

def test_llm_circuit_breaker_threshold_and_cooldown():
    os.environ["LLM_MODE"] = "real"
    os.environ["LLM_CB_FAIL_THRESHOLD"] = "3"
    os.environ["LLM_CB_COOLDOWN_S"] = "300"
    client = LLMClient(provider="openai", model="gpt-4o-mini")
    assert client.mode == "real"
    
    # 1. Simulate repeated failures to trip the breaker
    with patch('workflows.storage.db.DB.emit_event') as mock_emit, patch.object(client.real_adapter, 'complete', side_effect=ValueError("Simulated Real LLM Error")) as mock_real_complete:
        
        # Call 1: Fails (Failures = 1)
        res1 = client.complete("test 1")
        assert "diff" in res1["content"] # Falling back to mock
        assert LLMClient._cb_failures == 1
        assert not LLMClient._cb_is_open
        
        # Call 2: Fails (Failures = 2)
        res2 = client.complete("test 2")
        assert "diff" in res2["content"]
        assert LLMClient._cb_failures == 2
        assert not LLMClient._cb_is_open
        
        # Call 3: Fails (Failures = 3 -> Trips breaker)
        with patch('time.time', return_value=1000.0):
            res3 = client.complete("test 3")
            assert "diff" in res3["content"]
            assert LLMClient._cb_failures == 3
            assert LLMClient._cb_is_open is True
            assert LLMClient._cb_opened_at == 1000.0
            
        # Verify RealLLM was actually called 3 times
        assert mock_real_complete.call_count == 3
        
        # 2. Call while breaker OPEN and within cooldown
        with patch('time.time', return_value=1100.0): # Only 100s passed (Cooldown is 300s)
            res4 = client.complete("test 4")
            assert "diff" in res4["content"]
            # RealLLM should NOT be called again
            assert mock_real_complete.call_count == 3
            
        # 3. Call after cooldown expires (Probe request)
        with patch('time.time', return_value=1301.0): # 301s passed
            res5 = client.complete("test 5 (probe)")
            assert "diff" in res5["content"]
            # The probe is allowed to hit the real API
            assert mock_real_complete.call_count == 4
            
            # Since the real API still throws an error, the breaker stays open and time resets
            assert LLMClient._cb_is_open is True
            assert LLMClient._cb_opened_at == 1301.0
            assert LLMClient._cb_failures == 4 # Failures keep incrementing
            
    # 4. Probe SUCCESS resets the breaker
    with patch('workflows.storage.db.DB.emit_event'), patch.object(client.real_adapter, 'complete', return_value={"content": '{"diff":"real-json"}', "usage": {"total_tokens": 5}}) as mock_real_success:
        with patch('time.time', return_value=1602.0): # After another cooldown
            res6 = client.complete("test 6 (probe success)")
            
            # Real LLM should be called
            assert mock_real_success.call_count == 1
            
            # Breaker should be CLOSED
            assert LLMClient._cb_is_open is False
            assert LLMClient._cb_failures == 0
            
            # Correct payload is returned
            assert "real-json" in res6["content"]
