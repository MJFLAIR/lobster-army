from typing import Dict, Any
import logging

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

        response = self._call_llm(prompt, system_prompt, require_json=True)

        parsed = response

        def normalize_comments(comments):
            normalized = []
            if not isinstance(comments, list):
                return []
            for c in comments:
                if isinstance(c, str):
                    normalized.append({
                        "file": "unknown",
                        "line": 0,
                        "comment": c
                    })
                elif isinstance(c, dict):
                    normalized.append({
                        "file": c.get("file", "unknown"),
                        "line": c.get("line", 0),
                        "comment": c.get("comment", "")
                    })
            return normalized

        if isinstance(parsed, dict) and "comments" in parsed:
            parsed["comments"] = normalize_comments(parsed.get("comments", []))

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