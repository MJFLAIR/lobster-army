import pytest
from unittest.mock import patch, MagicMock
from workflows.actions.github_merge import try_merge_pr, get_merge_method

@patch("workflows.actions.github_merge.DB.emit_event")
@patch("workflows.actions.github_merge.GitHubClient")
@patch("workflows.actions.github_merge.merge_already_executed")
@patch.dict('os.environ', {"GITHUB_MERGE_ENABLED": "false"})
def test_merge_skips_when_disabled_default(mock_already_executed, mock_client_class, mock_emit):
    mock_already_executed.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_merge_pr("task_1", meta_json, review)

    # Verify calls
    mock_instance.merge_pull_request.assert_not_called()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_MERGE_SKIPPED" in events

@patch("workflows.actions.github_merge.DB.emit_event")
@patch("workflows.actions.github_merge.GitHubClient")
@patch("workflows.actions.github_merge.merge_already_executed")
@patch.dict('os.environ', {"GITHUB_MERGE_ENABLED": "true"})
def test_merge_executes_when_enabled(mock_already_executed, mock_client_class, mock_emit):
    mock_already_executed.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance
    mock_instance.merge_pull_request.return_value = {"sha": "1234abcd", "merged": True, "message": "Merged"}

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_merge_pr("task_1", meta_json, review)

    # Verify calls
    mock_instance.merge_pull_request.assert_called_once_with("my/repo", 1, merge_method="squash")

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_MERGE_EXECUTED" in events

@patch("workflows.actions.github_merge.DB.emit_event")
@patch("workflows.actions.github_merge.GitHubClient")
@patch("workflows.actions.github_merge.merge_already_executed")
@patch.dict('os.environ', {"GITHUB_MERGE_ENABLED": "true"})
def test_merge_skips_when_already_executed(mock_already_executed, mock_client_class, mock_emit):
    mock_already_executed.return_value = True
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_merge_pr("task_1", meta_json, review)

    # Verify calls
    mock_instance.merge_pull_request.assert_not_called()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_MERGE_EXECUTED" not in events
    assert "GITHUB_MERGE_SKIPPED" not in events

@patch("workflows.actions.github_merge.DB.emit_event")
@patch("workflows.actions.github_merge.GitHubClient")
@patch("workflows.actions.github_merge.merge_already_executed")
@patch.dict('os.environ', {"GITHUB_MERGE_ENABLED": "true"})
def test_merge_emits_failure_on_exception(mock_already_executed, mock_client_class, mock_emit):
    mock_already_executed.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance
    mock_instance.merge_pull_request.side_effect = Exception("Merge conflict")

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_merge_pr("task_1", meta_json, review)

    # Verify calls
    mock_instance.merge_pull_request.assert_called_once()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_MERGE_FAILED" in events
    
    failure_call = [c for c in calls if c[0][1] == "GITHUB_MERGE_FAILED"][0]
    payload = failure_call[0][2]
    assert payload["reason"] == "Merge conflict"
    assert payload["merge_key"] == "abc123key"


@patch.dict('os.environ', {"GITHUB_MERGE_METHOD": "invalid_method"})
def test_get_merge_method_fallback():
    method = get_merge_method()
    assert method == "squash"

@patch.dict('os.environ', {"GITHUB_MERGE_METHOD": "REBASE"})
def test_get_merge_method_supported():
    method = get_merge_method()
    assert method == "rebase"
