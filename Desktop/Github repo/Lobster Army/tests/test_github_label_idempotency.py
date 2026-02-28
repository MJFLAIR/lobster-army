import pytest
from unittest.mock import patch, MagicMock
from workflows.actions.github_label import try_apply_pr_labels

@patch("workflows.actions.github_label.DB.emit_event")
@patch("workflows.actions.github_label.GitHubClient")
@patch("workflows.actions.github_label.label_already_applied")
@patch.dict('os.environ', {"GITHUB_LABEL_ENABLED": "1", "GITHUB_LABELS": "lobster:merge-candidate"})
def test_label_applied_when_enabled_and_not_applied(mock_already_applied, mock_client_class, mock_emit):
    mock_already_applied.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance
    mock_instance.add_issue_labels.return_value = [{"name": "lobster:merge-candidate"}]

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_apply_pr_labels("task_1", meta_json, review)

    # Verify calls
    mock_instance.add_issue_labels.assert_called_once_with("my/repo", 1, ["lobster:merge-candidate"])

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_LABEL_APPLIED" in events

@patch("workflows.actions.github_label.DB.emit_event")
@patch("workflows.actions.github_label.GitHubClient")
@patch("workflows.actions.github_label.label_already_applied")
@patch.dict('os.environ', {"GITHUB_LABEL_ENABLED": "1", "GITHUB_LABELS": "lobster:merge-candidate"})
def test_label_skips_when_already_applied(mock_already_applied, mock_client_class, mock_emit):
    mock_already_applied.return_value = True
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_apply_pr_labels("task_1", meta_json, review)

    # Verify calls
    mock_instance.add_issue_labels.assert_not_called()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_LABEL_APPLIED" not in events

@patch("workflows.actions.github_label.DB.emit_event")
@patch("workflows.actions.github_label.GitHubClient")
@patch("workflows.actions.github_label.label_already_applied")
@patch.dict('os.environ', {"GITHUB_LABEL_ENABLED": "0", "GITHUB_LABELS": "lobster:merge-candidate"})
def test_label_skips_when_disabled(mock_already_applied, mock_client_class, mock_emit):
    mock_already_applied.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_apply_pr_labels("task_1", meta_json, review)

    # Verify calls
    mock_instance.add_issue_labels.assert_not_called()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_LABEL_APPLIED" not in events

@patch("workflows.actions.github_label.DB.emit_event")
@patch("workflows.actions.github_label.GitHubClient")
@patch("workflows.actions.github_label.label_already_applied")
@patch.dict('os.environ', {"GITHUB_LABEL_ENABLED": "1", "GITHUB_LABELS": "lobster:merge-candidate"})
def test_label_emits_failure_on_exception(mock_already_applied, mock_client_class, mock_emit):
    mock_already_applied.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance
    mock_instance.add_issue_labels.side_effect = Exception("API rate limit")

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_apply_pr_labels("task_1", meta_json, review)

    # Verify calls
    mock_instance.add_issue_labels.assert_called_once()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_LABEL_FAILED" in events
    
    failure_call = [c for c in calls if c[0][1] == "GITHUB_LABEL_FAILED"][0]
    payload = failure_call[0][2]
    assert payload["reason"] == "API rate limit"
    assert payload["merge_key"] == "abc123key"
