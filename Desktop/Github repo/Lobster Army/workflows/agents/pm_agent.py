from typing import Dict, Any
from workflows.agents.base_agent import BaseAgent


class PMAgent(BaseAgent):
    def validate_response(self, data: Dict[str, Any]) -> None:
        if "plan" not in data:
            raise ValueError("Schema Error: Missing 'plan' field")
        if not isinstance(data["plan"], list):
            raise ValueError("Schema Error: 'plan' must be a list")
        for item in data["plan"]:
            if not isinstance(item, str):
                raise ValueError("Schema Error: Each plan item must be a string")

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
  "plan": [
    "step 1",
    "step 2",
    "step 3"
  ]
}

Rules:
- The "plan" field MUST be a JSON array (list).
- Each item in the list MUST be a string.
- No additional keys are allowed.
- No comments.
- No extra text.
- Only a single valid JSON object.

If you fail to follow the schema exactly, the response will be rejected.
"""

        prompt = f"""
Create a simplified implementation plan for the following task.

Task:
{context.get('description')}

Return strictly the JSON object as defined above.
"""

        return self._call_llm(prompt, system_prompt)