import json
import os
import logging
from uuid import uuid4

LEARNINGS_PATH = "config/agent_learnings.json"

def extract_recoveries(diff_json: dict) -> list:
    """Extracts only steps marked as RECOVERED from a diff report."""
    if not isinstance(diff_json, dict):
        return []
    step_diffs = diff_json.get("step_diffs", [])
    return [step for step in step_diffs if step.get("type") == "RECOVERED"]

def _build_reflection_prompt(step_diff: dict) -> str:
    return f"""You are the Reflection Agent. Analyze this recovery diff and extract a generalized rule.

Agent: {step_diff.get("agent")}
Step Order: {step_diff.get("step_order")}
Original Status: {step_diff.get("from")}
Replay Status: {step_diff.get("to")}
Diff Type: {step_diff.get("type")}

Return STRICT JSON matching:
{{
  "target_agent": "{step_diff.get("agent")}",
  "failure_pattern": "short description of what failed",
  "fix_pattern": "short description of what fixed it",
  "new_rule": "actionable rule to prevent this in the future",
  "confidence_score": float between 0.0 and 1.0 (e.g. 0.85)
}}
"""

def generate_learning_from_diff(step_diff: dict, llm_provider) -> dict:
    """Generates a learning rule from a recovered step using LLM."""
    prompt = _build_reflection_prompt(step_diff)
    
    try:
        raw_output = llm_provider.complete(prompt=prompt)
        raw_output = raw_output.strip()
        if raw_output.startswith("```json"):
            raw_output = raw_output[7:]
        if raw_output.startswith("```"):
            raw_output = raw_output[3:]
        if raw_output.endswith("```"):
            raw_output = raw_output[:-3]
            
        return json.loads(raw_output.strip())
    except Exception as e:
        logging.error(f"[REFLECTION_AGENT_ERROR] Failed to generate/parse learning: {e}")
        return {}

def validate_learning(learning: dict) -> bool:
    """Validates the structure and quality of an extracted learning rule."""
    if not isinstance(learning, dict):
        return False
        
    required_keys = ["target_agent", "failure_pattern", "fix_pattern", "new_rule", "confidence_score"]
    for key in required_keys:
        if key not in learning:
            return False
            
        val = learning[key]
        if isinstance(val, str) and not val.strip():
            return False
            
    try:
        conf = float(learning["confidence_score"])
        if conf < 0.7:
            return False
    except (ValueError, TypeError):
        return False
        
    new_rule = learning.get("new_rule", "")
    if not isinstance(new_rule, str) or len(new_rule.strip()) < 10:
        return False
        
    return True

def update_knowledge_base(learning: dict, db_path: str = LEARNINGS_PATH):
    """Saves or merges a validated learning into the JSON knowledge base."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    db = []
    if os.path.exists(db_path):
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
        except json.JSONDecodeError:
            pass
            
    if not isinstance(db, list):
        db = []
        
    target_agent = learning["target_agent"]
    failure_pattern = learning["failure_pattern"]
    
    # Merge logic
    merged = False
    for existing in db:
        if existing.get("target_agent") == target_agent and existing.get("failure_pattern") == failure_pattern:
            # Found duplicate, merge it
            count = existing.get("occurrence_count", 1) + 1
            existing["occurrence_count"] = count
            
            # small confidence bump, max 1.0
            old_conf = float(existing.get("confidence_score", learning["confidence_score"]))
            new_conf = min(1.0, old_conf + 0.05)
            existing["confidence_score"] = float(round(new_conf, 3))
            
            # update rule and fix pattern to the newest insights
            existing["new_rule"] = learning["new_rule"]
            existing["fix_pattern"] = learning["fix_pattern"]
            merged = True
            break
            
    if not merged:
        learning["occurrence_count"] = 1
        learning["confidence_score"] = float(learning["confidence_score"])
        db.append(learning)
        
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
        
    logging.info("[REFLECTION_LEARNING_EXTRACTED]", extra={
        "agent": target_agent,
        "confidence": learning["confidence_score"]
    })

def process_diff_for_learnings(diff_json: dict, llm_provider, db_path: str = LEARNINGS_PATH) -> int:
    """Main pipeline to extract, generate, validate, and store learning rules."""
    recoveries = extract_recoveries(diff_json)
    if not recoveries:
        return 0
        
    learnings_added = 0
    for rec in recoveries:
        learning = generate_learning_from_diff(rec, llm_provider)
        if validate_learning(learning):
            update_knowledge_base(learning, db_path)
            learnings_added += 1
            
    return learnings_added
