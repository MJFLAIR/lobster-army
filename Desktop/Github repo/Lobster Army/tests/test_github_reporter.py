import pytest
import json
from unittest.mock import patch, MagicMock
from workflows.models.task import Task
from tools.github_reporter import GitHubReporter, REPORTER_VERSION
from tools.network_client import NetworkPolicyError
from google.api_core.exceptions import AlreadyExists

@pytest.fixture
def mock_task():
    return Task(
        task_id=123,
        source="github_pr",
        description="test",
        meta_json={
            "pull_request": {
                "number": 42,
                "head": {"sha": "sha123"}
            },
            "repository": {
                "full_name": "lobster/repo"
            }
        }
    )

def test_github_reporter_render_comment(mock_task):
    reporter = GitHubReporter()
    payload = {
        "status": "PASS",
        "score": 100,
        "comments": "Great code!"
    }
    
    body = reporter.render_review_comment(mock_task, payload)
    assert "**Status:** PASS" in body
    assert "**Score:** 100" in body
    assert "**Comments:**\nGreat code!" in body
    assert f"Lobster Army Review Bot v{REPORTER_VERSION}" in body
    assert "task_id: 123" in body
    assert "commit: sha123" in body  # "sha123" is less than 7 chars, so it returns "sha123"
    assert "generated_at:" in body

def test_render_comment_missing_head_sha():
    reporter = GitHubReporter()
    task = Task(
        task_id=999,
        source="github_pr",
        description="test",
        meta_json={}
    )
    payload = {"status": "PASS", "score": 90, "comments": "OK"}
    body = reporter.render_review_comment(task, payload)
    assert "commit: unknown" in body
    assert "task_id: 999" in body
    assert "generated_at:" in body

@patch("os.environ.get")
def test_github_reporter_disabled_or_missing_token(mock_env, mock_task):
    # Disabled test
    mock_env.side_effect = lambda k, d="": "0" if k == "GITHUB_REPORTER_ENABLED" else d
    reporter = GitHubReporter()
    res = reporter.post_pr_comment(42, "test body")
    assert res == {"ok": False, "skipped": True, "reason": "reporter_disabled"}

    # Enabled but missing token
    def mock_env_enabled_no_token(k, d=""):
        if k == "GITHUB_REPORTER_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return ""
        return d
        
    mock_env.side_effect = mock_env_enabled_no_token
    reporter_no_token = GitHubReporter()
    res2 = reporter_no_token.post_pr_comment(42, "test body")
    assert res2 == {"ok": False, "skipped": True, "reason": "missing_token"}

@patch("os.environ.get")
@patch("tools.github_reporter.NetworkClient.request")
def test_github_reporter_success_post(mock_request, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_REPORTER_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_REPO": return "lobster/repo"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    mock_request.return_value = b'{"id": 999}'
    
    reporter = GitHubReporter()
    res = reporter.post_pr_comment(42, "test body")
    
    assert res["ok"] is True
    assert res["response"] == {"id": 999}
    
    mock_request.assert_called_once()
    kwargs = mock_request.call_args[1]
    assert kwargs["url"] == "https://api.github.com/repos/lobster/repo/issues/42/comments"
    assert kwargs["headers"]["Authorization"] == "Bearer mock_token"
    assert json.loads(kwargs["body"].decode()) == {"body": "test body"}

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
@patch("tools.github_reporter.NetworkClient")
def test_github_reporter_run_hook_already_exists(mock_network, mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_REPORTER_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        return d
    mock_env.side_effect = mock_env_vars
    
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    
    mock_doc_ref = MagicMock()
    mock_doc_ref.create.side_effect = AlreadyExists("Duplicate")
    mock_db_client.collection.return_value.document.return_value = mock_doc_ref
    
    reporter = GitHubReporter()
    # Mock network client inside reporter so it doesn't get called
    reporter.network_client = MagicMock()
    
    reporter.run_hook(mock_task, {"status": "PASS"})
    
    # Should be skipped due to dedup
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0] == 123
    assert mock_emit.call_args[0][1] == "GITHUB_REPORTER_SKIPPED"
    assert mock_emit.call_args[0][2]["reason"] == "duplicate"
    
    reporter.network_client.request.assert_not_called()

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_github_reporter_run_hook_success(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_REPORTER_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        return d
    mock_env.side_effect = mock_env_vars
    
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    
    mock_doc_ref = MagicMock()
    mock_doc_ref.create.side_effect = None
    mock_db_client.collection.return_value.document.return_value = mock_doc_ref
    
    reporter = GitHubReporter()
    reporter.network_client = MagicMock()
    reporter.network_client.request.return_value = b'{"id": 999}'
    
    reporter.run_hook(mock_task, {"status": "PASS"})
    
    # Create should be called
    mock_doc_ref.create.assert_called_once()
    
    # Network request should be fired
    reporter.network_client.request.assert_called_once()
    
    # POSTED event should be emitted
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_REPORTER_POSTED"
    assert mock_emit.call_args[0][2]["pr_number"] == 42
    assert mock_emit.call_args[0][2]["repo"] == "lobster/repo"

def test_github_reporter_run_hook_skip_non_pr(mock_task):
    mock_task.source = "discord_slash"
    reporter = GitHubReporter()
    
    with patch("workflows.storage.db.DB.get_client") as mock_db:
        reporter.run_hook(mock_task, {"status": "PASS"})
        mock_db.assert_not_called()
