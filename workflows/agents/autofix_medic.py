import json
import logging

SYSTEM_PROMPT = """You are AutoFix_Medic, an elite debugging and recovery agent.

You are ONLY triggered when a failure occurs.

You will receive:
- Error message
- Existing code
- Execution context

--------------------------------------------------
ROLE

- Diagnose the failure
- Fix the code
- Return a fully corrected version

--------------------------------------------------
RULES

- NO markdown
- NO explanations outside JSON
- STRICT JSON ONLY

--------------------------------------------------
OUTPUT FORMAT

{
  "status": "success",
  "target_file": "relative/path/to/file.py",
  "code": "# fully corrected code",
  "notes": "What was fixed and why"
}

--------------------------------------------------
CONSTRAINTS

- Fix ONLY what is broken
- Preserve working logic
- DO NOT introduce unrelated features
- DO NOT return file_path
- DO NOT return content
- The correct write keys are target_file and code"""

class AutoFixMedicAgent:
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider

    def handle_autofix_medic(self, instruction: str) -> dict:
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
            
        # Rigid API schema constraint checks
        if not isinstance(result, dict) or result.get("status") not in ["success", "failed"]:
            return {
                "status": "failed",
                "error": "Invalid schema from LLM: missing valid status",
            }
            
        if result.get("status") == "success":
            if "target_file" not in result or "code" not in result:
                return {
                    "status": "failed",
                    "error": "Invalid schema from LLM: missing target_file or code",
                }
            if "file_path" in result or "content" in result:
                return {
                    "status": "failed",
                    "error": "Invalid schema from LLM: returned file_path or content instead of target_file and code",
                }
            
        return result
