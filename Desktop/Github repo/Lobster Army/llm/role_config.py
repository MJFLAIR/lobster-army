import json
from pathlib import Path
from typing import Dict

# Resolve project root dynamically
PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = PROJECT_ROOT / "config" / "llm_role_config.json"

# Cache configuration after first load
_ROLE_CONFIG: Dict[str, dict] | None = None


def _load_config() -> Dict[str, dict]:
    global _ROLE_CONFIG

    if _ROLE_CONFIG is not None:
        return _ROLE_CONFIG

    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"LLM role config not found: {CONFIG_PATH}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _ROLE_CONFIG = json.load(f)

    return _ROLE_CONFIG


def get_role_config(role: str) -> Dict[str, str]:
    """
    Return provider and model configuration for a given role.

    Example:
        get_role_config("pm")

    Returns:
        {
            "provider": "...",
            "model": "..."
        }
    """

    config = _load_config()

    role = role.lower()

    role_map = config["roles"]
    providers = config["providers"]

    if role not in role_map:
        raise ValueError(f"Unknown LLM role: {role}")

    provider_key = role_map[role]

    if provider_key not in providers:
        raise ValueError(f"Unknown provider key: {provider_key}")

    return providers[provider_key]
