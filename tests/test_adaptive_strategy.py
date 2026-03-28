import pytest
from unittest.mock import patch, MagicMock

from workflows.strategy.adaptive_strategy import decide_retry_strategy
from workflows.strategy.self_healing_loop import self_healing_execute

def test_fail_fast_schema_invalid():
    decision = decide_retry_strategy("schema_invalid")
    assert decision["should_retry"] is False

def test_fail_fast_scope_violation():
    decision = decide_retry_strategy("scope_violation")
    assert decision["should_retry"] is False

def test_retry_json_parse_error():
    decision = decide_retry_strategy("json_parse_error")
    assert decision["should_retry"] is True
    assert decision["template_override"] == "JSON_FORMAT_ERROR"

def test_template_override_mapping():
    decision_git = decide_retry_strategy("git_apply_check_failed")
    assert decision_git["should_retry"] is True
    assert decision_git["template_override"] == "DIFF_FORMAT_ERROR"
    
    decision_invalid_llm = decide_retry_strategy("invalid_llm_output")
    assert decision_invalid_llm["template_override"] == "JSON_FORMAT_ERROR"

@patch("workflows.strategy.self_healing_loop.run_auto_fix_for_incident")
@patch("workflows.strategy.self_healing_loop.ErrorFeedbackBuilder.build")
@patch("workflows.strategy.failure_pattern_tracker.record_failure_event")
def test_integration_skip_retry(mock_record, mock_build, mock_run):
    mock_run.return_value = {"status": "BLOCKED", "reason": "schema_invalid"}
    
    incident = {"incident_hash": "inc-123"}
    repo_mock = MagicMock()
    llm_mock = MagicMock()
    
    result = self_healing_execute(incident, repo_mock, llm_mock, "/path")
    
    assert mock_run.call_count == 1
    assert result["status"] == "BLOCKED"

@patch("workflows.strategy.self_healing_loop.run_auto_fix_for_incident")
@patch("workflows.strategy.self_healing_loop.ErrorFeedbackBuilder.build")
@patch("workflows.strategy.failure_pattern_tracker.record_failure_event")
def test_integration_retry_allowed(mock_record, mock_build, mock_run):
    mock_run.side_effect = [
        {"status": "FAILED", "reason": "json_parse_error"},
        {"status": "PATCH_READY", "reason": "NONE"}
    ]
    mock_build.return_value = ("Fix this", "JSON_FORMAT_ERROR")
    
    incident = {"incident_hash": "inc-456"}
    repo_mock = MagicMock()
    llm_mock = MagicMock()
    
    result = self_healing_execute(incident, repo_mock, llm_mock, "/path")
    
    assert mock_run.call_count == 2
    assert result["status"] == "PATCH_READY"

@patch('workflows.strategy.adaptive_strategy.get_failure_stats')
def test_dynamic_low_samples(mock_stats):
    mock_stats.return_value = {"json_parse_error": {"attempts": 7, "successes": 0}}
    decision = decide_retry_strategy("json_parse_error")
    assert decision["should_retry"] is True

@patch('workflows.strategy.adaptive_strategy.get_failure_stats')
def test_dynamic_low_success_rate(mock_stats):
    mock_stats.return_value = {"json_parse_error": {"attempts": 10, "successes": 1}}
    decision = decide_retry_strategy("json_parse_error")
    assert decision["should_retry"] is False
    assert "Success rate 10.0%" in decision["reason"]

@patch('workflows.strategy.adaptive_strategy.get_failure_stats')
def test_dynamic_high_success_rate(mock_stats):
    mock_stats.return_value = {"json_parse_error": {"attempts": 10, "successes": 5}}
    decision = decide_retry_strategy("json_parse_error")
    assert decision["should_retry"] is True

@patch('workflows.strategy.adaptive_strategy.get_failure_stats')
def test_dynamic_zero_success_hard_fail(mock_stats):
    mock_stats.return_value = {"json_parse_error": {"attempts": 8, "successes": 0}}
    decision = decide_retry_strategy("json_parse_error")
    assert decision["should_retry"] is False
    assert "Zero successes after 8 attempts" in decision["reason"]
