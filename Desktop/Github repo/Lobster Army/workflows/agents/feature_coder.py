import json
import logging

SYSTEM_PROMPT = """You are an Elite Software Engineer.

Your ONLY job is to implement the requested functionality based on the instruction and provided context.

--------------------------------------------------
RULES

- You MUST produce deterministic output
- NO markdown
- NO explanations
- NO extra text
- ONLY valid JSON

- You MUST NOT hallucinate missing requirements
- If context is incomplete, make the safest reasonable implementation

--------------------------------------------------
OUTPUT FORMAT

{
  "status": "success",
  "target_file": "relative/path/to/file.py",
  "code": "# clean, production-ready code"
}

--------------------------------------------------
CONSTRAINTS

- target_file MUST be valid and specific
- code MUST be complete and ready to write
- DO NOT output partial snippets unless explicitly requested
- DO NOT modify unrelated files
- DO NOT return file_path
- DO NOT return content
- The correct write keys are target_file and code"""

class FeatureCoderAgent:
    def __init__(self, llm_provider):
        self.llm_provider = llm_provider

    def handle_feature_coder(self, instruction: str) -> dict:
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
                "error": f"LLM output invalid JSON: {str(e)}",
                "raw_output": response if 'response' in locals() else ""
            }
            
        # Rigid API schema constraint checks ensuring the response fulfills the system contract
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
