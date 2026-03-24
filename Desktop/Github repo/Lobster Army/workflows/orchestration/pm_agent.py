import json
import logging

AVAILABLE_AGENTS = {
    "AutoFix_Medic": "Fixes CI/CD and patch errors",
    "Feature_Coder": "Implements or modifies code",
    "Reviewer": "Reviews code quality and logic",
    "Terminal_Operator": "Reads files and system state" # Kept for compatibility if needed, though prompt only mentions Feature_Coder and Reviewer
}

def _build_system_prompt() -> str:
    return """You are an Elite Technical Project Manager.

Your job is to break down the user's request into a strict, minimal, and deterministic JSON execution plan.

You DO NOT execute tasks.
You ONLY plan them.

You command a team of agents:
- Feature_Coder
- Reviewer

--------------------------------------------------
AVAILABLE TOOLS (TRIGGERED BY JSON KEYS)

1. Read File (Eyes)
- Trigger: "file_path": "<relative/path>"
- Use ONLY when existing code must be read or modified

2. Fetch URL (Network)
- Trigger: "url": "<https://...>"
- Use ONLY when external data is strictly required

3. Write File (Hands)
- Automatically handled by Feature_Coder
- You must clearly instruct what to build

--------------------------------------------------
STRICT TOOL USAGE RULES (CRITICAL)

- DO NOT include "url" unless absolutely necessary
- DO NOT include "file_path" unless reading existing code is required
- NEVER include both unless truly required

- MINIMIZE tool usage
- Each tool call has cost, latency, and failure risk

--------------------------------------------------
PLANNING STRATEGY

- Simple task -> 1 step (Feature_Coder only)

- Medium or Complex task ->
  Step 1: Feature_Coder (build)
  Step 2: Reviewer (audit)

- CRITICAL SYSTEM RULE:
  Do NOT schedule the AutoFix_Medic.
  The AutoFix_Medic is an emergency responder triggered ONLY by the system (C12 Self-Healing).
  It must NEVER appear in the execution plan.

- Always use the MINIMUM number of steps required

--------------------------------------------------
FAIL-SAFE STRATEGY (C12 COMPATIBLE)

- Assume tools may fail
- Avoid chaining too many dependencies
- Prefer smaller, isolated steps when external data is required
- Instructions must remain valid even with partial data

--------------------------------------------------
OUTPUT FORMAT (STRICT JSON ONLY)

You MUST output valid JSON.

NO markdown  
NO explanation  
NO extra text  

Schema:

{
  "execution_plan": [
    {
      "step_order": 1,
      "agent": "Feature_Coder",
      "instruction": "Clear and specific instruction",
      "file_path": "src/main.py",
      "url": "https://api.github.com/..."
    }
  ]
}

Rules:
- Omit "file_path" if not needed
- Omit "url" if not needed
- DO NOT use placeholder values like "optional/path"
- Only include real, meaningful values

--------------------------------------------------
NON-NEGOTIABLE RULES

- You NEVER execute tools
- You ONLY plan
- You MUST stay deterministic
- You MUST minimize steps
- You MUST minimize tool usage
- You MUST output clean JSON only
"""

def _fallback_plan() -> dict:
    return {
        "execution_plan": [
            {
                "step_order": 1,
                "agent": "Feature_Coder",
                "instruction": "Analyze task and gather context"
            }
        ]
    }

def _validate_plan(plan: dict) -> tuple[bool, str]:
    if not isinstance(plan, dict):
        return False, "invalid_root_type"
        
    execution_plan = plan.get("execution_plan")
    if not isinstance(execution_plan, list) or len(execution_plan) == 0:
        return False, "empty_execution_plan"
        
    valid_agents = ["Feature_Coder", "Reviewer", "Terminal_Operator", "AutoFix_Medic"]

    for step in execution_plan:
        if not isinstance(step, dict):
            return False, "invalid_step_structure"
            
        step_order = step.get("step_order")
        # Ensure it is strictly an integer, not a string or float masquerading as one.
        if type(step_order) is not int:
            return False, "invalid_step_order"
            
        agent = step.get("agent")
        if agent not in valid_agents:
            # We strictly enforce the agents mentioned
            return False, f"invalid_agent: {agent}"
            
        instruction = step.get("instruction")
        if not isinstance(instruction, str) or len(instruction.strip()) == 0:
            return False, "invalid_instruction"

        # AutoFix_Medic should NOT be planned
        if agent == "AutoFix_Medic":
            return False, "autofix_medic_not_allowed"
            
    return True, "valid"

def normalize_plan(plan: dict) -> dict:
    MAX_STEPS = 5
    MAX_INSTRUCTION_CHARS = 2000

    execution_plan = plan.get("execution_plan") or []

    # Step limit
    execution_plan = execution_plan[:MAX_STEPS]

    # 1. Sort steps by step_order ascending
    sorted_steps = sorted(execution_plan, key=lambda x: x.get("step_order", 999))
    
    cleaned_plan = []
    # 2. Reindex step_order to 1..N and discard extra keys
    for i, step in enumerate(sorted_steps, start=1):
        if not isinstance(step, dict):
            continue

        instruction = step.get("instruction", "")
        if not isinstance(instruction, str):
            instruction = str(instruction)

        cleaned_step = {
            "step_order": i,
            "agent": str(step.get("agent")),
            "instruction": instruction.strip()[:MAX_INSTRUCTION_CHARS],
        }
        
        # Optional routing keys
        if "file_path" in step and isinstance(step["file_path"], str) and step["file_path"].strip():
            cleaned_step["file_path"] = step["file_path"].strip()
            
        if "url" in step and isinstance(step["url"], str) and step["url"].strip():
            cleaned_step["url"] = step["url"].strip()
            
        if "output_path" in step and isinstance(step["output_path"], str) and step["output_path"].strip():
            cleaned_step["output_path"] = step["output_path"].strip()
            
        cleaned_plan.append(cleaned_step)
        
    return {
        "execution_plan": cleaned_plan
    }

def generate_execution_plan(task_description: str, llm_provider) -> dict:
    system_prompt = _build_system_prompt()
    user_prompt = f"TASK:\n{task_description}"
    
    try:
        raw_output = llm_provider.complete(prompt=f"{system_prompt}\n\n{user_prompt}")
        
        # Parse JSON safely
        try:
            raw_output = raw_output.strip()
            if raw_output.startswith("```json"):
                raw_output = raw_output[7:]
            if raw_output.startswith("```"):
                raw_output = raw_output[3:]
            if raw_output.endswith("```"):
                raw_output = raw_output[:-3]
                
            raw_plan = json.loads(raw_output.strip())
        except Exception as e:
            logging.info(f"[PM_AGENT_FALLBACK] json_parse_error: {str(e)}")
            return _fallback_plan()
            
        # Extract only execution_plan
        extracted_plan = {"execution_plan": raw_plan.get("execution_plan", [])}
            
        # Validate raw plan
        is_valid, reason = _validate_plan(extracted_plan)
        if not is_valid:
            logging.info(f"[PM_AGENT_FALLBACK] {reason}")
            return _fallback_plan()
            
        # Normalize plan
        normalized_plan = normalize_plan(extracted_plan)
        
        # Validate normalized plan again
        is_valid_norm, reason_norm = _validate_plan(normalized_plan)
        if not is_valid_norm:
            logging.info(f"[PM_AGENT_FALLBACK] post_normalization_validation_failed: {reason_norm}")
            return _fallback_plan()
            
        # Success logging
        logging.info("[PM_AGENT_PLAN_GENERATED]", extra={"plan": normalized_plan})
        return normalized_plan
        
    except Exception as e:
        logging.info(f"[PM_AGENT_FALLBACK] unexpected_error: {str(e)}")
        return _fallback_plan()

