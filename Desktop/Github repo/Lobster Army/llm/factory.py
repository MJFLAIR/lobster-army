from tools.llm_client import LLMClient

def create_llm(provider: str, model: str) -> LLMClient:
    """
    Creates an LLMClient with explicit provider/model binding.
    """
    return LLMClient(provider=provider, model=model)
