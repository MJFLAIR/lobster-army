from typing import Dict, Any
from workflows.agents.base_agent import BaseAgent

class PMAgent(BaseAgent):
    def validate_response(self, data: Dict[str, Any]) -> None:
        if "plan" not in data:
            raise ValueError("Schema Error: Missing 'plan' field")
        if not isinstance(data["plan"], list):
            raise ValueError("Schema Error: 'plan' must be a list")

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = "You are a Product Manager. Output strictly JSON."
        prompt = f"Create a simplified implementation plan for task: {context.get('description')}"
        
        # _call_llm handles retry and validation now
        return self._call_llm(prompt, system_prompt)
