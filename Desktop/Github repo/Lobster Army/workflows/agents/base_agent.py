from typing import Dict, Any
import json
import logging
from tools.llm_adapter import LLMAdapter
from tools.cost_tracker import CostTracker

class BaseAgent:
    def __init__(self, llm: LLMAdapter, task_id: int):
        self.llm = llm
        self.task_id = task_id
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cost_tracker = CostTracker(task_id)

    def _call_llm(self, prompt: str, system_prompt: str, max_retries: int = 3) -> Dict[str, Any]:
        last_error = None
        
        # Initial budget check
        self.cost_tracker.check_budget()

        for attempt in range(max_retries):
            self.logger.info(f"Task {self.task_id}: Calling LLM (Attempt {attempt + 1}/{max_retries})...")
            try:
                response = self.llm.complete(prompt, system_prompt)
                
                # Track cost (and check budget again)
                usage = response.get("usage", {})
                self.cost_tracker.track_usage(usage)

                content = response.get("content", "{}")
                data = self._parse_json(content)
                
                # Enforce Schema Validation
                self.validate_response(data)
                
                return data

            except Exception as e:
                self.logger.warning(f"LLM Call failed (Attempt {attempt + 1}): {e}")
                last_error = e
                # Check budget usage even on failure if tokens were consumed? 
                
        self.logger.error(f"LLM Call failed after {max_retries} attempts")
        raise last_error or RuntimeError("Unknown LLM Error")

    def validate_response(self, data: Dict[str, Any]) -> None:
        """
        Subclasses should override to enforce strict schema.
        Raises ValueError if invalid.
        """
        pass

    def _parse_json(self, content: str) -> Dict[str, Any]:
        try:
            # Simple cleanup for markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            return json.loads(content)
        except json.JSONDecodeError:
            self.logger.error(f"Failed to parse JSON: {content}")
            raise ValueError("Invalid JSON response from LLM")
