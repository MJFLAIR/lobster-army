from typing import Dict, Any
from workflows.agents.base_agent import BaseAgent


class CodeAgent(BaseAgent):
    def validate_response(self, data: Dict[str, Any]) -> None:
        if "diff" not in data and "commits" not in data:
            raise ValueError("Schema Error: Must implement 'diff' or 'commits'")
        
        if "diff" in data and not isinstance(data["diff"], str):
            raise ValueError("Schema Error: 'diff' must be a string")
        
        if "commits" in data and not isinstance(data["commits"], list):
            raise ValueError("Schema Error: 'commits' must be a list")

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = """
You are a Senior Python Engineer AI.

You MUST output ONLY valid JSON.
Do NOT output markdown.
Do NOT output explanation.
Do NOT output code fences.
Do NOT output any text outside the JSON object.

You MUST follow exactly one of these schemas:

Option 1:
{
  "diff": "unified diff string"
}

Option 2:
{
  "commits": [
    {
      "message": "commit message",
      "diff": "unified diff string"
    }
  ]
}

Rules:
- Output ONLY one JSON object.
- No additional keys.
- No comments.
- No extra text.
- If modifying files, use unified diff format.
"""

        prompt = f"""
Implement the following plan:

{context}

Return strictly the JSON object as defined above.
"""

        return self._call_llm(prompt, system_prompt)