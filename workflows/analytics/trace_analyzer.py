def validate_trace(trace: dict) -> None:
    """Validates the structure of the input execution trace."""
    if not isinstance(trace, dict):
        raise ValueError("Trace must be a dictionary")
        
    required_keys = ["task_id", "steps", "final_status"]
    for key in required_keys:
        if key not in trace:
            raise ValueError(f"Missing required key in trace: {key}")
            
    if not isinstance(trace["steps"], list):
        raise ValueError("Trace 'steps' must be a list")
        
    for i, step in enumerate(trace["steps"]):
        if not isinstance(step, dict):
            raise ValueError(f"Step {i} must be a dictionary")
        if "agent" not in step:
            raise ValueError(f"Step {i} missing required key: 'agent'")
        if "status" not in step:
            raise ValueError(f"Step {i} missing required key: 'status'")

def analyze_trace(trace: dict) -> dict:
    """Computes pure deterministic metrics from an execution trace."""
    validate_trace(trace)
    
    total_steps = len(trace["steps"])
    self_healing_cycles = 0
    agent_metrics = {}
    
    for step in trace["steps"]:
        agent = step["agent"]
        status = step["status"]
        
        if agent == "AutoFix_Medic":
            self_healing_cycles += 1
            
        if agent not in agent_metrics:
            agent_metrics[agent] = {"calls": 0, "failures": 0}
            
        agent_metrics[agent]["calls"] += 1
        if status == "failed":
            agent_metrics[agent]["failures"] += 1
            
    tool_metrics = {}
    for tool_action in trace.get("tool_actions", []):
        tool_name = tool_action.get("tool_name", "unknown")
        status = tool_action.get("status", "unknown")
        
        if tool_name not in tool_metrics:
            tool_metrics[tool_name] = {"calls": 0, "failures": 0}
            
        tool_metrics[tool_name]["calls"] += 1
        if status != "success" and status != "PASS":
            tool_metrics[tool_name]["failures"] += 1
            
    metrics = {
        "task_id": trace["task_id"],
        "final_status": trace["final_status"],
        "total_steps": total_steps,
        "self_healing_cycles": self_healing_cycles,
        "self_healing_triggered": trace.get("self_healing_triggered", False),
        "agent_metrics": agent_metrics,
        "tool_metrics": tool_metrics
    }
    
    return metrics

def compute_score(metrics: dict) -> float:
    """Computes a 0-100 reliability score based on trace metrics."""
    score = 100
    
    self_healing_cycles = metrics.get("self_healing_cycles", 0)
    score -= (self_healing_cycles * 15)
    
    tool_failures = 0
    for tool, stats in metrics.get("tool_metrics", {}).items():
        tool_failures += stats.get("failures", 0)
        
    score -= (tool_failures * 20)
    
    # Also deduct for unhealed agent failures
    # (Though specific formula requested only explicitly deducted healing cycles and tool failures)
    # Sticking strictly to the user's requested formula!
    
    return max(0.0, float(score))
