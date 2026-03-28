import re
from pathlib import Path
from unittest.mock import patch

from llm.factory import get_llm_for_role
from tools.cost_tracker import CostTracker
from workflows.agents.base_agent import BaseAgent
from workflows.orchestration.execution_tracer import ExecutionTracer
from utils.identifier import normalize_identifier


def test_base_agent_has_no_telemetry_dependency():
    assert not hasattr(BaseAgent, "_record_model_usage")

    class DummyLLM:
        def complete(self, prompt, system_prompt, **kwargs):
            return {"content": {"ok": True}, "usage": {"total_tokens": 7}}

    class DummyAgent(BaseAgent):
        def validate_response(self, data):
            assert data["ok"] is True

    with patch.object(CostTracker, "check_budget", return_value=None), patch.object(
        CostTracker, "track_usage", return_value=None
    ):
        result = DummyAgent(DummyLLM(), task_id=1)._call_llm("p", "s", max_retries=1)

    assert result == {"ok": True}


def test_quartermaster_cannot_be_bypassed_in_core_flow():
    root = Path(__file__).resolve().parents[1]
    candidate_files = list((root / "workflows" / "orchestration").glob("*.py")) + [
        root / "workflows" / "task_manager.py",
        root / "workflows" / "agents" / "llm_review_gate.py",
    ]

    forbidden_direct_creation = re.compile(r"\bcreate_llm\(")
    offenders = []

    for file_path in candidate_files:
        content = file_path.read_text(encoding="utf-8")
        if forbidden_direct_creation.search(content):
            offenders.append(str(file_path))

    assert offenders == []


def test_identifier_normalization_helper():
    assert normalize_identifier("Feature_Coder") == "feature_coder"
    assert normalize_identifier("PMAgent") == "pm_agent"
    assert normalize_identifier("AutoFix-Medic") == "auto_fix_medic"
    assert normalize_identifier(" reviewer ") == "reviewer"
    assert normalize_identifier("") == ""
    assert normalize_identifier(None) == ""


def test_critical_points_use_normalization_helper():
    root = Path(__file__).resolve().parents[1]
    critical_files = [
        root / "llm" / "quartermaster.py",
        root / "workflows" / "orchestration" / "agent_dispatcher.py",
        root / "workflows" / "orchestration" / "execution_tracer.py",
    ]

    for file_path in critical_files:
        content = file_path.read_text(encoding="utf-8")
        assert "normalize_identifier" in content
        assert ".lower()" not in content


def test_telemetry_recorded_in_execution_layer(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    task_id = 998877
    tracer = ExecutionTracer(task_id)

    llm = get_llm_for_role("reviewer")
    llm.complete("Review payload", system_prompt="You are a Senior Code Reviewer AI.", task_id=task_id)

    model_usage = tracer.trace.get("model_usage", [])
    assert len(model_usage) >= 1
    assert model_usage[0]["role"] == "reviewer"
    assert model_usage[0]["model"] == "gemini-1.5-flash"
    assert isinstance(model_usage[0]["tokens"], int)

    tracer.finalize("SUCCESS")
