"""
Agent Registry
Minimal deterministic registry listing known agents to keep ranking stable.
"""

KNOWN_AGENTS = {
    "PMAgent",
    "Feature_Coder",
    "Reviewer",
    "AutoFix_Medic"
}

def is_known_agent(agent_name: str) -> bool:
    """Check if the given agent name is in the known registry."""
    return agent_name in KNOWN_AGENTS
