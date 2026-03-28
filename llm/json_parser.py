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

    # 1️⃣ direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    clean_text = text

    # 2️⃣ ```json block
    if "```json" in clean_text:
        try:
            clean_text = clean_text.split("```json", 1)[1].split("```", 1)[0].strip()
            return json.loads(clean_text)
        except Exception:
            pass

    # 3️⃣ ``` block
    if "```" in clean_text:
        try:
            clean_text = clean_text.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(clean_text)
        except Exception:
            pass

    # 4️⃣ fallback (C25 終極防爆版：GPT 正則 + 參謀長度排序法)
    logger.warning("[PARSER_GUARD_FALLBACK] Falling back to regex extraction")

    # 👉 融合 GPT 的 [\s\S]* 貪婪匹配，無視任何換行阻礙
    obj_match = re.search(r"\{[\s\S]*\}", clean_text)
    list_match = re.search(r"\[[\s\S]*\]", clean_text)

    candidates = []
    if obj_match:
        candidates.append(obj_match.group(0))
    if list_match:
        candidates.append(list_match.group(0))

    # 👉 戰術核心：依字串長度排序（最長的最先解析，絕對不讓內層 List 綁架外層 Object！）
    candidates = sorted(candidates, key=len, reverse=True)

    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue

    # ✅ 最終防線：確保必定觸發 Medic 自癒，絕對不允許掉出 None！
    raise JSONParseError(
        f"Failed to parse JSON from LLM output: {clean_text[:300]}"
    )