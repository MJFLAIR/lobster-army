import os
import json
import time
import logging
from typing import Callable, Dict, Any, Optional
from tools.llm_adapter import LLMAdapter

class MockLLMAdapter(LLMAdapter):
    """Internal mock implementation for fallback."""
    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        sp = (system_prompt or "").lower()

        # Strict routing
        is_pm = "product manager" in sp
        is_review = "code reviewer" in sp
        is_code = "python engineer" in sp

        # ---- PM ----
        if is_pm:
            payload = {
                "plan": [
                    "mock-step-1",
                    "mock-step-2",
                ]
            }
        # ---- Review ----
        elif is_review:
            payload = {
                "status": "PASS",
                "score": 100,
            }
        # ---- Code ----
        else:
            payload = {
                "diff": "mock-diff-content"
            }

        return {
            "content": json.dumps(payload),
            "usage": {"total_tokens": 10},
        }

class LLMClient(LLMAdapter):
    """
    Dual-Mode LLMClient:
    - LLM_MODE=mock: always uses mock.
    - LLM_MODE=real: tries RealLLMClient, falls back to mock on any failure.
    Includes a Global Circuit Breaker for RealLLM calls to prevent runaway cost and latency.
    """

    # Class-level state for Circuit Breaker (process-local)
    _cb_failures = 0
    _cb_is_open = False
    _cb_opened_at = 0.0

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        event_emitter: Optional[Callable[[int, str, dict], None]] = None,
    ):
        # Determine mode
        mode = os.environ.get("LLM_MODE")
        if mode:
            mode = mode.lower()
        else:
            mode = "mock"
        
        self.mode = mode
        self.provider = (provider or "openai").lower()
        self.model = model or "gpt-4o-mini"
        self.mock_adapter = MockLLMAdapter()
        self.event_emitter = event_emitter
        
        # Load CB configs
        self.cb_fail_threshold = int(os.environ.get("LLM_CB_FAIL_THRESHOLD", "3"))
        self.cb_cooldown_s = float(os.environ.get("LLM_CB_COOLDOWN_S", "300"))
        
        self.real_adapter = None
        if self.mode == "real":
            try:
                from tools.real_llm_client import RealLLMClient
                self.real_adapter = RealLLMClient(provider=self.provider, model=self.model)
            except Exception as e:
                logging.warning(f"Failed to initialize RealLLMClient: {e}. Will fallback to mock.")

    @property
    def mock_mode(self):
        """Backward compatibility for existing code checking client.mock_mode directly"""
        return self.mode == "mock"

    def _emit_event(self, task_id: int, event_type: str, payload: dict):
        if task_id <= 0 or self.mode != "real" or not self.event_emitter:
            return
        try:
            self.event_emitter(task_id, event_type, payload)
        except Exception as e:
            logging.error(f"Event emission failed: {e}")

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        task_id = kwargs.get("task_id", -1)

        if self.mode == "real" and self.real_adapter:
            pass
        else:
            if self.mode == "real" and not self.real_adapter:
                self._emit_event(task_id, "LLM_FALLBACK", {"reason": "real_adapter_uninitialized"})
            return self.mock_adapter.complete(prompt, system_prompt, **kwargs)

        # Check Circuit Breaker
        now = time.time()
        if LLMClient._cb_is_open:
            if now - LLMClient._cb_opened_at >= self.cb_cooldown_s:
                # Cooldown expired, allow 1 probe request
                pass
            else:
                # Still within cooldown, skip real LLM immediately
                self._emit_event(task_id, "LLM_FALLBACK", {"reason": "circuit_breaker_open"})
                return self.mock_adapter.complete(prompt, system_prompt, **kwargs)

        # 1. Emit Request
        self._emit_event(task_id, "LLM_REQUEST", {
            "prompt_length": len(prompt),
            "system_prompt_length": len(system_prompt) if system_prompt else 0
        })

        try:
            result = self.real_adapter.complete(prompt, system_prompt, **kwargs)
            
            # If we get here, the call succeeded.
            if LLMClient._cb_is_open or LLMClient._cb_failures > 0:
                # Close the breaker and reset
                LLMClient._cb_is_open = False
                LLMClient._cb_failures = 0
                logging.info("[CircuitBreaker] Real LLM call succeeded. Breaker CLOSED and state reset.")
                self._emit_event(task_id, "LLM_CIRCUIT_CLOSE", {"reason": "probe_success"})

            # 2. Emit Success Response
            self._emit_event(task_id, "LLM_RESPONSE", {
                "usage": result.get("usage", {})
            })

            return result

        except Exception as e:
            # Record failure
            LLMClient._cb_failures += 1
            logging.error(f"Real LLM call failed: {e}. Falling back to Mock. (Failure {LLMClient._cb_failures}/{self.cb_fail_threshold})")
            
            # 3. Emit Error
            self._emit_event(task_id, "LLM_ERROR", {
                "error": str(e),
                "type": type(e).__name__
            })

            if LLMClient._cb_failures >= self.cb_fail_threshold and not LLMClient._cb_is_open:
                # Open the breaker
                LLMClient._cb_is_open = True
                LLMClient._cb_opened_at = now
                logging.warning(
                    f"[CircuitBreaker] OPENED! Threshold reached ({self.cb_fail_threshold}). "
                    f"Subsequent real calls skipped for {self.cb_cooldown_s}s."
                )
                self._emit_event(task_id, "LLM_CIRCUIT_OPEN", {
                    "failures": LLMClient._cb_failures,
                    "cooldown_s": self.cb_cooldown_s
                })
            elif LLMClient._cb_is_open:
                # Probe failed again, restart cooldown clock
                LLMClient._cb_opened_at = now
                logging.warning(
                    f"[CircuitBreaker] Probe call failed. Cooldown extended for another {self.cb_cooldown_s}s."
                )

            # 4. Emit Fallback
            self._emit_event(task_id, "LLM_FALLBACK", {"reason": "real_call_failed"})
            return self.mock_adapter.complete(prompt, system_prompt, **kwargs)
