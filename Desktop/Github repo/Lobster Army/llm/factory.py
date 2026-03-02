import os
import contextlib
from typing import Dict, Any
from tools.llm_client import LLMClient

@contextlib.contextmanager
def temporary_env_set(env_vars: Dict[str, str]):
    """Temporarily set environment variables."""
    old_env = {}
    for key, val in env_vars.items():
        old_env[key] = os.environ.get(key)
        os.environ[key] = val
        
    try:
        yield
    finally:
        for key, old_val in old_env.items():
            if old_val is None:
                del os.environ[key]
            else:
                os.environ[key] = old_val

def create_llm(provider: str, model: str) -> LLMClient:
    """
    Creates an LLMClient configured using the existing environment variables.
    Currently, tools.real_llm_client.py consumes `LLM_MODEL`.
    There is no global `LLM_PROVIDER` natively parsed by the client yet 
    (it defaults to OpenAI if openai is installed). 
    We set LLM_MODEL temporarily so RealLLMClient.__init__ picks it up without
    affecting the global process env.
    """
    env_updates = {
        "LLM_MODEL": model,
        # RealLLMClient doesn't currently use a provider key, but providing it for future proofing 
        # or if it gets updated to use litellm.
        "LLM_PROVIDER": provider, 
        
        # We also set the review specific ones to keep backward compatibility with snapshots
        # during task initialization if not already set, though these are technically read at 
        # execution time in llm_review_gate.py
    }
    
    with temporary_env_set(env_updates):
        client = LLMClient()
        
    return client
