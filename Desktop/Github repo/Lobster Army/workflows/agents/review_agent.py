from typing import Dict, Any
from workflows.agents.base_agent import BaseAgent

class ReviewAgent(BaseAgent):
    def validate_response(self, data: Dict[str, Any]) -> None:
        if "status" not in data:
            raise ValueError("Schema Error: Missing 'status'")
        if data["status"] not in ["PASS", "FAIL", "REQUEST_CHANGES"]:
            raise ValueError(f"Schema Error: Invalid status {data['status']}")
        if "score" not in data:
            raise ValueError("Schema Error: Missing 'score'")
        if not isinstance(data["score"], (int, float)):
             raise ValueError("Schema Error: 'score' must be a number")

    def run(self, diff_data: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = "You are a Code Reviewer. Output strictly JSON. Rate correctness 0-100."
        prompt = f"Review this code change: {diff_data}"
        
        return self._call_llm(prompt, system_prompt)
