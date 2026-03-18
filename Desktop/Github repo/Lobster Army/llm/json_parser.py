import json
import re
import logging

logger = logging.getLogger(__name__)


class JSONParseError(Exception):
    pass


def safe_parse_json(text: str) -> dict | list:
    """
    Production-safe JSON parser for LLM outputs.

    Supports:
    - pure JSON
    - ```json markdown blocks
    - ``` blocks
    - text + JSON
    - JSON objects {...}
    - JSON lists [...]

    Logs fallback usage for debugging.
    """

    if not text:
        raise JSONParseError("Empty LLM output")

    text = text.strip()

    # 1️⃣ direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    clean_text = text

    # 2️⃣ markdown ```json block
    if "```json" in clean_text:
        try:
            clean_text = clean_text.split("```json", 1)[1].split("```", 1)[0].strip()
            return json.loads(clean_text)
        except (IndexError, json.JSONDecodeError):
            pass

    # 3️⃣ markdown ``` block
    if "```" in clean_text:
        try:
            clean_text = clean_text.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(clean_text)
        except (IndexError, json.JSONDecodeError):
            pass

    # 4️⃣ fallback regex extraction
    logger.warning("[PARSER_GUARD_FALLBACK] Falling back to regex extraction")

    # JSON object
    obj_match = re.search(r"\{.*?\}", clean_text, re.DOTALL)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except json.JSONDecodeError:
            pass

    # JSON list
    list_match = re.search(r"\[.*?\]", clean_text, re.DOTALL)
    if list_match:
        try:
            return json.loads(list_match.group(0))
        except json.JSONDecodeError:
            pass

    raise JSONParseError(
        f"Failed to parse JSON from LLM output: {clean_text[:300]}"
    )