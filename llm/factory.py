import inspect
import logging
from tools.llm_client import LLMClient
from llm.quartermaster import Quartermaster
from utils.identifier import normalize_identifier

def create_llm(provider: str, model: str) -> LLMClient:
    """
    Creates an LLMClient with explicit provider/model binding.
    """
    caller_module = inspect.currentframe().f_back.f_globals.get("__name__", "")
    if caller_module != __name__ and not caller_module.startswith("tests"):
        logging.warning(
            f"[LLM_CREATE_BYPASS] direct create_llm call from={caller_module} provider={provider} model={model}"
        )
    return LLMClient(provider=provider, model=model)

def get_llm_for_role(role: str, context: dict = None) -> LLMClient:
    equipment = Quartermaster().get_equipment(role, context)
    provider = equipment["provider"]
    model = equipment["model"]

    logging.info(
        f"[LLM_ROLE_MAPPING] role={role} provider={provider} model={model}"
    )

    llm = create_llm(provider=provider, model=model)
    setattr(llm, "_quartermaster_role", normalize_identifier(role))

    return llm
