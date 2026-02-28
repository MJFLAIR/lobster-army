import pytest
from unittest.mock import patch, MagicMock
from workflows.actions.github_comment import try_post_pr_comment

@patch("workflows.actions.github_comment.DB.emit_event")
@patch("workflows.actions.github_comment.GitHubClient")
@patch("workflows.actions.github_comment.comment_already_posted")
@patch.dict('os.environ', {"GITHUB_COMMENT_ENABLED": "1"})
def test_comment_posts_when_enabled_and_not_posted(mock_already_posted, mock_client_class, mock_emit):
    mock_already_posted.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance
    mock_instance.post_pr_comment.return_value = {"id": 12345, "html_url": "https://github.com/test"}

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_post_pr_comment("task_1", meta_json, review)

    # Verify calls
    mock_instance.post_pr_comment.assert_called_once()
    assert "lobster review" in mock_instance.post_pr_comment.call_args[0][2].lower()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_COMMENT_POSTED" in events

@patch("workflows.actions.github_comment.DB.emit_event")
@patch("workflows.actions.github_comment.GitHubClient")
@patch("workflows.actions.github_comment.comment_already_posted")
@patch.dict('os.environ', {"GITHUB_COMMENT_ENABLED": "1"})
def test_comment_skips_when_already_posted(mock_already_posted, mock_client_class, mock_emit):
    mock_already_posted.return_value = True
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_post_pr_comment("task_1", meta_json, review)

    # Verify calls
    mock_instance.post_pr_comment.assert_not_called()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_COMMENT_POSTED" not in events

@patch("workflows.actions.github_comment.DB.emit_event")
@patch("workflows.actions.github_comment.GitHubClient")
@patch("workflows.actions.github_comment.comment_already_posted")
@patch.dict('os.environ', {"GITHUB_COMMENT_ENABLED": "0"})
def test_comment_skips_when_disabled(mock_already_posted, mock_client_class, mock_emit):
    mock_already_posted.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_post_pr_comment("task_1", meta_json, review)

    # Verify calls
    mock_instance.post_pr_comment.assert_not_called()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_COMMENT_POSTED" not in events


@patch("workflows.actions.github_comment.DB.emit_event")
@patch("workflows.actions.github_comment.GitHubClient")
@patch("workflows.actions.github_comment.comment_already_posted")
@patch.dict('os.environ', {"GITHUB_COMMENT_ENABLED": "1"})
def test_comment_emits_failure_on_exception(mock_already_posted, mock_client_class, mock_emit):
    mock_already_posted.return_value = False
    
    # Setup mock github client
    mock_instance = MagicMock()
    mock_client_class.return_value = mock_instance
    mock_instance.post_pr_comment.side_effect = Exception("API rate limit")

    # Run the function
    meta_json = {"repo": "my/repo", "pr_number": "1"}
    review = {"decision": "approve", "score": 0.9, "threshold": 0.75, "merge_key": "abc123key"}
    
    try_post_pr_comment("task_1", meta_json, review)

    # Verify calls
    mock_instance.post_pr_comment.assert_called_once()

    # Verify events
    calls = mock_emit.call_args_list
    events = [c[0][1] for c in calls]
    assert "GITHUB_COMMENT_FAILED" in events
    
    failure_call = [c for c in calls if c[0][1] == "GITHUB_COMMENT_FAILED"][0]
    payload = failure_call[0][2]
    assert payload["reason"] == "API rate limit"
    assert payload["merge_key"] == "abc123key"
