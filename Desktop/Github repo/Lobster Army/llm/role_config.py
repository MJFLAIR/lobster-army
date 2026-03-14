import os
from typing import Dict

def get_role_config(role: str) -> Dict[str, str]:
    """
    Reads role-specific LLM configuration from the environment.
    Fallback to default: provider=openai, model=gpt-4o-mini
    
    Env vars used:
    {ROLE}_LLM_PROVIDER (e.g. PM_LLM_PROVIDER)
    {ROLE}_LLM_MODEL    (e.g. PM_LLM_MODEL)
    """
    prefix = role.upper()
    provider_key = f"{prefix}_LLM_PROVIDER"
    model_key = f"{prefix}_LLM_MODEL"
    
    provider = os.getenv(provider_key, "openai")
    model = os.getenv(model_key, "gpt-4o-mini")
    
    return {
        "provider": provider,
        "model": model
    }
