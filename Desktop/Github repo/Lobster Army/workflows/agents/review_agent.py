from typing import Dict, Any
import logging

from workflows.agents.base_agent import BaseAgent

from tools.llm_json_guard import LLMJSONGuard
from tools.llm_json_schemas import require_review_schema


class ReviewAgent(BaseAgent):

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
  "approved": true or false,
  "comments": [
    {
      "file": "...",
      "line": number,
      "comment": "..."
    }
  ]
}

Rules:
- "approved" MUST be boolean.
- "comments" MUST be a list.
- Each comment must include file, line, and comment.
- No additional keys.
- No comments outside JSON.
"""

        prompt = f"""
Review the following implementation result:

{context}
"""

        response = self._call_llm(prompt, system_prompt)

        guard = LLMJSONGuard(allow_root_object=True, allow_root_array=False)

        # Robust response extraction (avoid KeyError and support multiple LLM formats)
        if isinstance(response, dict):
            raw = (
                response.get("content")
                or response.get("text")
                or response.get("output")
                or response.get("message")
                or ""
            )
        else:
            raw = str(response)

        parsed = guard.parse_object(raw, validator=require_review_schema)

        if not parsed.ok:
            logging.warning("[REVIEW_SCHEMA_ERROR] %s", parsed.error)

            return {
                "approved": False,
                "comments": [],
                "error": f"schema_invalid: {parsed.error}"
            }

        return parsed.data