import os
import json
import time
import logging
from typing import Callable, Dict, Any, Optional
from tools.llm_adapter import LLMAdapter
from utils.identifier import normalize_identifier

class MockLLMAdapter(LLMAdapter):
    """Internal mock implementation for fallback."""
    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        sp = (system_prompt or "").lower()
        prompt_l = (prompt or "").lower()

        # Strict routing
        is_pm = "product manager" in sp
        is_review = "code reviewer" in sp
        is_code = "python engineer" in sp

        case_a = "sandbox/fib.py" in prompt_l
        case_b = "sandbox/fib_broken.py" in prompt_l
        case_c = "../outside.py" in prompt_l

        # ---- PM ----
        if is_pm:
            if case_a:
                payload = {
                    "plan": [
                        {
                            "step_order": 1,
                            "agent": "feature_coder",
                            "instruction": "Generate fibonacci script and save to sandbox/fib.py",
                            "target_file": "sandbox/fib.py"
                        }
                    ]
                }
            elif case_b:
                payload = {
                    "plan": [
                        {
                            "step_order": 1,
                            "agent": "feature_coder",
                            "instruction": "Generate fibonacci script and save to sandbox/fib_broken.py",
                            "target_file": "sandbox/fib_broken.py",
                            "mock_case": "review_fail_then_heal"
                        }
                    ]
                }
            elif case_c:
                payload = {
                    "plan": [
                        {
                            "step_order": 1,
                            "agent": "feature_coder",
                            "instruction": "Generate fibonacci script and save to ../outside.py",
                            "target_file": "../outside.py"
                        }
                    ]
                }
            else:
                payload = {
                    "plan": [
                        "mock-step-1",
                        "mock-step-2",
                    ]
                }
        # ---- Review ----
        elif is_review:
            if case_b or "review_fail_then_heal" in prompt_l:
                payload = {
                    "approved": False,
                    "comments": [
                        {
                            "file": "sandbox/fib_broken.py",
                            "line": 1,
                            "comment": "Algorithm does not satisfy large-n and edge-case requirements."
                        }
                    ]
                }
            else:
                payload = {
                    "approved": True,
                    "status": "PASS",
                    "score": 100,
                    "comments": []
                }
        # ---- Code ----
        else:
            if case_a:
                payload = {
                    "diff": "mock-diff-content",
                    "target_file": "sandbox/fib.py",
                    "code": "def fib(n):\n    a, b = 0, 1\n    out = []\n    for _ in range(n):\n        out.append(a)\n        a, b = b, a + b\n    return out\n\nif __name__ == '__main__':\n    print(fib(10))\n"
                }
            elif case_b:
                payload = {
                    "diff": "mock-diff-content",
                    "target_file": "sandbox/fib_broken.py",
                    "code": "def fib(n):\n    return [0, 1]\n",
                    "mock_case": "review_fail_then_heal"
                }
            elif case_c:
                payload = {
                    "diff": "mock-diff-content",
                    "target_file": "../outside.py",
                    "code": "print('outside sandbox')\n"
                }
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
        print(f"[LLM_INIT] provider={self.provider} model={self.model}")
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

    def _record_model_usage(self, task_id: int, usage: Dict[str, Any]) -> None:
        if task_id <= 0:
            return

        try:
            from workflows.orchestration.execution_tracer import ExecutionTracer
            tracer = ExecutionTracer.get_active_tracer(task_id)
            if tracer is None or not hasattr(tracer, "record_model_usage"):
                return

            total_tokens = usage.get("total_tokens", 0)
            if not total_tokens:
                total_tokens = (usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0)

            role = normalize_identifier(getattr(self, "_quartermaster_role", "unknown"))
            tracer.record_model_usage(role=role, model=self.model, tokens=int(total_tokens or 0))
        except Exception as e:
            logging.debug(f"[MODEL_USAGE_TRACE_SKIP] {e}")

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        task_id = kwargs.get("task_id", -1)

        if self.mode == "real" and self.real_adapter:
            pass
        else:
            if self.mode == "real" and not self.real_adapter:
                self._emit_event(task_id, "LLM_FALLBACK", {"reason": "real_adapter_uninitialized"})
            result = self.mock_adapter.complete(prompt, system_prompt, **kwargs)
            self._record_model_usage(task_id, result.get("usage", {}))
            return result

        # Check Circuit Breaker
        now = time.time()
        if LLMClient._cb_is_open:
            if now - LLMClient._cb_opened_at >= self.cb_cooldown_s:
                # Cooldown expired, allow 1 probe request
                pass
            else:
                # Still within cooldown, skip real LLM immediately
                self._emit_event(task_id, "LLM_FALLBACK", {"reason": "circuit_breaker_open"})
                result = self.mock_adapter.complete(prompt, system_prompt, **kwargs)
                self._record_model_usage(task_id, result.get("usage", {}))
                return result

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
            self._record_model_usage(task_id, result.get("usage", {}))

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
            result = self.mock_adapter.complete(prompt, system_prompt, **kwargs)
            self._record_model_usage(task_id, result.get("usage", {}))
            return result
