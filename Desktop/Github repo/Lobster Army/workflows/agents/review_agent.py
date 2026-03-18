from typing import Dict, Any
import logging

from workflows.agents.base_agent import BaseAgent

from tools.llm_json_schemas import require_review_schema


class ReviewAgent(BaseAgent):

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = """
You are a Senior Code Reviewer AI.

You MUST return ONLY a valid JSON object.
DO NOT include any explanation, text, markdown, or code fences.
DO NOT wrap JSON in ``` blocks.
Return raw JSON only.

You MUST follow exactly this schema:

{
  "approved": boolean,
  "comments": string[]
}

If you are unsure, return:
{
  "approved": false,
  "comments": ["Unable to evaluate"]
}

Rules:
- "approved" MUST be boolean.
- "comments" MUST be a list of strings.
- No additional keys.
- No comments outside JSON.

INVALID:
"Looks good overall."
"```json { ... } ```"

VALID:
{
  "approved": true,
  "comments": []
}
"""

        prompt = f"""
Review the following implementation result:

{context}
"""

        response = self._call_llm(prompt, system_prompt, require_json=True)

        parsed = response

        try:
            valid_data = require_review_schema(parsed)
            return valid_data
        except Exception as e:
            logging.warning("[REVIEW_SCHEMA_ERROR] %s", e)

            return {
                "approved": False,
                "comments": [],
                "error": f"schema_invalid: {e}"
            }