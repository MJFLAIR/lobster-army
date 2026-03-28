from typing import Dict, Any
from workflows.agents.base_agent import BaseAgent
from tools.llm_json_schemas import require_review_schema


class ReviewAgent(BaseAgent):

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = """
You are a Senior Code Reviewer AI.

You MUST return JSON in the following exact format:

{
  "approved": boolean,
  "comments": [
    {
      "file": string,
      "line": number,
      "comment": string
    }
  ]
}

Rules:
- comments MUST be a list of objects (dict), NOT strings
- Each comment MUST include: file, line, comment
- If no issues, return: "comments": []
- DO NOT return explanations outside JSON
- DO NOT wrap JSON in markdown
- Output must be valid JSON only
"""

        prompt = f"""
Review the following implementation result:

{context}
"""

        # ✅ 正確：交給 BaseAgent 處理 retry / parse / validate
        data = self._call_llm(prompt, system_prompt, require_json=True)

        return data

    def validate_response(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ValueError("Schema Error: response must be dict")

        # ✅ 嚴格 schema 驗證（不通過就 raise → retry → fail）
        require_review_schema(data)