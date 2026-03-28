import re
from pathlib import Path

from llm.factory import get_llm_for_role
from llm.quartermaster import Quartermaster
from tools.llm_client import LLMClient


def test_quartermaster_base_routing():
    qm = Quartermaster()

    assert qm.get_equipment("feature_coder") == {"provider": "openai", "model": "gpt-4o"}
    assert qm.get_equipment("autofix_medic") == {"provider": "openai", "model": "gpt-4o"}
    assert qm.get_equipment("reviewer") == {"provider": "gemini", "model": "gemini-1.5-flash"}
    assert qm.get_equipment("pm_agent") == {"provider": "gemini", "model": "gemini-1.5-flash"}
    assert qm.get_equipment("summarizer") == {"provider": "openai", "model": "gpt-4o-mini"}
    assert qm.get_equipment("insight_agent") == {"provider": "openai", "model": "gpt-4o-mini"}
    assert qm.get_equipment("unknown_role") == {"provider": "openai", "model": "gpt-4o-mini"}


def test_quartermaster_complexity_override():
    qm = Quartermaster()

    assert qm.get_equipment("feature_coder", {"complexity": "high"}) == {
        "provider": "openai",
        "model": "gpt-4o",
    }
    assert qm.get_equipment("reviewer", {"complexity": "high"}) == {
        "provider": "gemini",
        "model": "gemini-1.5-pro",
    }


def test_quartermaster_context_missing_no_crash():
    qm = Quartermaster()
    equipment = qm.get_equipment("reviewer")
    assert equipment["provider"] == "gemini"
    assert equipment["model"] == "gemini-1.5-flash"


def test_factory_returns_valid_llm_instance():
    llm = get_llm_for_role("feature_coder", {"complexity": "high"})
    assert isinstance(llm, LLMClient)
    assert llm.provider == "openai"
    assert llm.model == "gpt-4o"


def test_handlers_do_not_use_hardcoded_model():
    root = Path(__file__).resolve().parents[1]
    orchestration_dir = root / "workflows" / "orchestration"
    pattern = re.compile(r"create_llm\(\s*['\"](openai|gemini)['\"]\s*,\s*['\"][^'\"]+['\"]\s*\)")

    offenders = []
    for py_file in orchestration_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if pattern.search(content):
            offenders.append(str(py_file))

    assert offenders == []
