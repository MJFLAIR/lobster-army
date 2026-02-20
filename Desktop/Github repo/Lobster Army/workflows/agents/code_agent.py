from typing import Dict, Any
from workflows.agents.base_agent import BaseAgent

class CodeAgent(BaseAgent):
    def validate_response(self, data: Dict[str, Any]) -> None:
        if "diff" not in data and "commits" not in data:
            raise ValueError("Schema Error: Must implement 'diff' or 'commits'")
        if "commits" in data and not isinstance(data["commits"], list):
             raise ValueError("Schema Error: 'commits' must be a list")

    def run(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = "You are a Senior Python Engineer. Output strictly JSON."
        prompt = f"Implement the following plan: {plan}"
        
        return self._call_llm(prompt, system_prompt)
