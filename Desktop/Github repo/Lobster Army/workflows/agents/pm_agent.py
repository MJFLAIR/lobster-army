from typing import Dict, Any
import logging

from workflows.agents.base_agent import BaseAgent

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

        response = self._call_llm(prompt, system_prompt, require_json=True)

        parsed = response

        try:
            valid_data = require_pm_schema(parsed)
            return valid_data
        except Exception as e:
            logging.warning("[PM_SCHEMA_ERROR] %s", e)

            return {
                "tasks": [],
                "error": f"schema_invalid: {e}"
            }