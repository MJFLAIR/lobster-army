from typing import Dict, Any
import logging

from workflows.agents.base_agent import BaseAgent

from tools.llm_json_guard import LLMJSONGuard
from tools.llm_json_schemas import require_pm_schema


class PMAgent(BaseAgent):

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = """
You are a Product Manager AI.

You MUST output ONLY valid JSON.
Do NOT output markdown.
Do NOT output explanation.
Do NOT output code fences.
Do NOT output any text outside the JSON object.

The output MUST strictly follow this schema:

{
  "tasks": [
    {
      "title": "...",
      "description": "...",
      "priority": "low|medium|high"
    }
  ]
}

Rules:
- The "tasks" field MUST be a JSON array.
- Each task must contain title, description, priority.
- Priority must be low, medium, or high.
- No additional keys.
- No extra text.
"""

        prompt = f"""
Create a simplified implementation plan for the following task.

Task:
{context.get('description')}
"""

        response = self._call_llm(prompt, system_prompt)

        guard = LLMJSONGuard(allow_root_object=True, allow_root_array=False)

        raw = response["content"] if isinstance(response, dict) else str(response)

        parsed = guard.parse_object(raw, validator=require_pm_schema)

        if not parsed.ok:
            logging.warning("[PM_SCHEMA_ERROR] %s", parsed.error)

            return {
                "tasks": [],
                "error": f"schema_invalid: {parsed.error}"
            }

        return parsed.data