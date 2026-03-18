import os
import logging
from tools.llm_client import LLMClient
from llm.role_config import get_role_config

def create_llm(provider: str, model: str) -> LLMClient:
    """
    Creates an LLMClient with explicit provider/model binding.
    """
    return LLMClient(provider=provider, model=model)

def get_llm_for_role(role: str) -> LLMClient:
    try:
        config = get_role_config(role)
        provider = config["provider"]
        model = config["model"]

        logging.info(
            f"[LLM_ROLE_MAPPING] role={role} provider={provider} model={model}"
        )
    except Exception as e:
        provider = os.getenv("LLM_PROVIDER", "openai")
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        logging.warning(
            f"[LLM_ROLE_MAPPING_FALLBACK] role={role} provider={provider} model={model} error={e}"
        )

    return create_llm(provider=provider, model=model)
