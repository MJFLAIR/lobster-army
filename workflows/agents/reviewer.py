import json
import logging

SYSTEM_PROMPT = """You are a Ruthless Code Reviewer and Security Auditor.

Your job is to inspect the provided code and determine if it is safe, correct, and production-ready.

--------------------------------------------------
CRITICAL SYSTEM ROLE

- You DO NOT write code
- You DO NOT fix code
- You ONLY approve or reject

- If you reject, the system (C12 Self-Healing) will automatically decide the next recovery step
- You DO NOT call any tool

--------------------------------------------------
RULES

- NO markdown
- NO explanations outside JSON
- STRICT JSON ONLY

--------------------------------------------------
OUTPUT FORMAT

IF PASS:

{
  "status": "success",
  "notes": "LGTM"
}

IF FAIL:

{
  "status": "failed",
  "error": "Detailed explanation of the issue, including location and reason"
}

--------------------------------------------------
FAIL CONDITIONS

You MUST return "failed" if:

- Any bug exists
- Edge cases are not handled
- Code is unsafe
- Logic is incomplete
- External dependency assumptions are incorrect

--------------------------------------------------
CRITICAL CONSTRAINT

- DO NOT output target_file
- DO NOT output code
- You are an auditor only"""

class ReviewerAgent:
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider

    def handle_reviewer(self, instruction: str) -> dict:
        try:
            # Execute underlying LLM request
            response = self.llm_provider.complete(prompt=instruction, system_prompt=SYSTEM_PROMPT)
            
            # Purge MD backticks strictly
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            result = json.loads(response)
        except Exception as e:
            return {
                "status": "failed",
                "error": f"LLM output invalid JSON: {str(e)}"
            }
            
        # Rigid API schema constraint checks ensuring the response fulfills the system contract
        if not isinstance(result, dict) or result.get("status") not in ["success", "failed"]:
            return {
                "status": "failed",
                "error": "Invalid schema from LLM: missing valid status",
            }
            
        if "target_file" in result or "code" in result:
            return {
                "status": "failed",
                "error": "Invalid schema from LLM: returned target_file or code in Auditor role",
            }

        if result.get("status") == "failed" and "error" not in result:
            return {
                "status": "failed",
                "error": "Invalid schema from LLM: failed status missing error explanation"
            }
            
        return result
