from typing import Dict, Any
from workflows.agents.base_agent import BaseAgent


class ReviewAgent(BaseAgent):
    def validate_response(self, data: Dict[str, Any]) -> None:
        if "status" not in data:
            raise ValueError("Schema Error: Missing 'status'")
        if data["status"] not in ["PASS", "FAIL"]:
            raise ValueError("Schema Error: 'status' must be PASS or FAIL")

        if "score" not in data:
            raise ValueError("Schema Error: Missing 'score'")
        if not isinstance(data["score"], (int, float)):
            raise ValueError("Schema Error: 'score' must be a number")

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = """
You are a Senior Code Reviewer AI.

You MUST output ONLY valid JSON.
Do NOT output markdown.
Do NOT output explanation.
Do NOT output code fences.
Do NOT output any text outside the JSON object.

You MUST follow exactly this schema:

{
  "status": "PASS" or "FAIL",
  "score": 0-100
}

Rules:
- "status" MUST be either "PASS" or "FAIL".
- "score" MUST be a number between 0 and 100.
- No additional keys.
- No comments.
- No extra text.
"""

        prompt = f"""
Review the following implementation result:

{context}

Return strictly the JSON object as defined above.
"""

        return self._call_llm(prompt, system_prompt)