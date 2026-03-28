from typing import Dict, Any
import logging
from tools.llm_adapter import LLMAdapter
from tools.cost_tracker import CostTracker


class BaseAgent:
    def __init__(self, llm: LLMAdapter, task_id: int):
        self.llm = llm
        self.task_id = task_id
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cost_tracker = CostTracker(task_id)

    def _call_llm(self, prompt: str, system_prompt: str, max_retries: int = 3, **kwargs) -> Dict[str, Any]:
        last_error = None

        # Initial budget check
        self.cost_tracker.check_budget()

        for attempt in range(max_retries):
            self.logger.info(f"Task {self.task_id}: Calling LLM (Attempt {attempt + 1}/{max_retries})...")
            try:
                response = self.llm.complete(prompt, system_prompt, task_id=self.task_id, **kwargs)

                # Track cost
                usage = response.get("usage", {})
                self.cost_tracker.track_usage(usage)

                content = response.get("content", {})

                # ✅ FIX 1: already parsed JSON (mock / adapter case)
                if isinstance(content, dict):
                    data = content
                else:
                    data = self._parse_json(content)

                # ✅ FIX 2: enforce schema
                self.validate_response(data)

                return data

            except Exception as e:
                self.logger.warning(f"LLM Call failed (Attempt {attempt + 1}): {e}")
                last_error = e

        self.logger.error(f"LLM Call failed after {max_retries} attempts")
        raise last_error or RuntimeError("Unknown LLM Error")

    def validate_response(self, data: Dict[str, Any]) -> None:
        """
        Subclasses must override.
        MUST raise ValueError if schema invalid.
        """
        pass

    def _parse_json(self, content: str) -> Dict[str, Any]:
        from llm.json_parser import safe_parse_json, JSONParseError

        # ✅ FIX 3: guard against non-string input
        if not isinstance(content, str):
            raise ValueError(f"Expected string content, got {type(content)}")

        try:
            return safe_parse_json(content)
        except JSONParseError:
            self.logger.error(f"Failed to parse JSON: {content}")
            raise ValueError("Invalid JSON response from LLM")
