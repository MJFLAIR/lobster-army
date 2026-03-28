import json
import logging
import os

def enrich_instruction_with_learnings(
    agent_name: str,
    base_instruction: str,
    db_path: str = "config/agent_learnings.json",
    override_path: str = "config/human_overrides.json",
    max_rules: int = 5
) -> str:
    """
    Injects high-confidence learnings into agent instructions dynamically.
    Fail-safe: Returns base_instruction on ANY failure organically isolating LLM paths.
    """
    try:
        combined_rules = {}
        
        def load_rules(filepath, is_override=False):
            if not os.path.exists(filepath):
                return
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        return
                    
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                            
                        target = item.get("target_agent")
                        if target != agent_name:
                            continue
                            
                        # Normalize keys flexibly between standard and C14 specs
                        rule_text = item.get("rule", item.get("new_rule"))
                        confidence = item.get("confidence", item.get("confidence_score"))
                        
                        if not rule_text or confidence is None:
                            continue
                            
                        try:
                            conf_float = float(confidence)
                        except (ValueError, TypeError):
                            continue
                            
                        if conf_float < 0.75:
                            continue
                            
                        rule_clean = str(rule_text).strip()
                        if not rule_clean:
                            continue
                            
                        combined_rules[rule_clean] = conf_float
            except Exception:
                pass # Silently skip logic natively shielding the orchestrator

        # Enforce Overrides via dict merging sequential priority
        load_rules(db_path, is_override=False)
        load_rules(override_path, is_override=True)
        
        if not combined_rules:
            return base_instruction
            
        final_rules = [{"rule": r, "confidence": c} for r, c in combined_rules.items()]
        final_rules = sorted(final_rules, key=lambda x: x["confidence"], reverse=True)[:max_rules]
        
        if not final_rules:
            return base_instruction
            
        injection_lines = [
            base_instruction,
            "",
            "---",
            "",
            "⚠️ SYSTEM MEMORY (HIGH CONFIDENCE RULES)",
            "",
            "You MUST follow these rules:",
            ""
        ]
        
        for idx, rule in enumerate(final_rules, 1):
            injection_lines.append(f"{idx}. {rule['rule']} (Confidence: {rule['confidence']})")
            
        logging.info("[LEARNINGS_INJECTED]", extra={
            "agent": agent_name,
            "rules": len(final_rules),
            "source": "json_merge"
        })
        
        return "\\n".join(injection_lines)
        
    except Exception:
        # Absolute structural fail-safe fallback
        return base_instruction
