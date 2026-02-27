import pytest
import json
from unittest.mock import patch, MagicMock
from workflows.models.task import Task
from tools.github_pr_labeler import GitHubPRLabeler
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

def test_decide_labels_approved_by_status():
    labeler = GitHubPRLabeler()
    labels = labeler.decide_labels({"status": "PASS"})
    assert "lobster:reviewed" in labels
    assert "lobster:approved" in labels
    assert "lobster:changes-requested" not in labels

def test_decide_labels_changes_by_status():
    labeler = GitHubPRLabeler()
    labels = labeler.decide_labels({"status": "FAIL"})
    assert "lobster:reviewed" in labels
    assert "lobster:changes-requested" in labels
    assert "lobster:approved" not in labels

def test_decide_labels_by_score_threshold():
    labeler = GitHubPRLabeler()
    labels_pass = labeler.decide_labels({"score": 0.85})
    assert "lobster:approved" in labels_pass
    
    labels_fail = labeler.decide_labels({"score": 0.7})
    assert "lobster:changes-requested" in labels_fail
    
    labels_default = labeler.decide_labels({"no_status": True})
    assert "lobster:changes-requested" in labels_default

@patch("os.environ.get")
def test_labeler_disabled_or_missing_token_no_network_call(mock_env, mock_task):
    mock_env.side_effect = lambda k, d="": "0" if k == "GITHUB_LABELER_ENABLED" else d
    labeler = GitHubPRLabeler()
    res = labeler.post_labels("lobster/repo", 42, ["test"])
    assert res == {"ok": False, "skipped": True, "reason": "labeler_disabled"}

    def mock_env_enabled_no_token(k, d=""):
        if k == "GITHUB_LABELER_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return ""
        return d
    
    mock_env.side_effect = mock_env_enabled_no_token
    labeler_no_token = GitHubPRLabeler()
    res2 = labeler_no_token.post_labels("lobster/repo", 42, ["test"])
    assert res2 == {"ok": False, "skipped": True, "reason": "missing_token"}

@patch("os.environ.get")
@patch("tools.github_pr_labeler.NetworkClient.request")
def test_post_labels_builds_correct_request(mock_request, mock_env):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_LABELER_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    mock_request.return_value = b'{"success": true}'
    
    labeler = GitHubPRLabeler()
    res = labeler.post_labels("lobster/repo", 42, ["lobster:reviewed", "lobster:approved"])
    
    assert res["ok"] is True
    mock_request.assert_called_once()
    kwargs = mock_request.call_args[1]
    assert kwargs["url"] == "https://api.github.com/repos/lobster/repo/issues/42/labels"
    assert kwargs["headers"]["Authorization"] == "Bearer mock_token"
    assert json.loads(kwargs["body"].decode()) == {"labels": ["lobster:reviewed", "lobster:approved"]}

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_run_hook_dedup_already_exists_skips_post(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_LABELER_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        return d
    mock_env.side_effect = mock_env_vars
    
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    
    # Simulate AlwaysExists when inserting the FIRST label
    mock_doc_ref = MagicMock()
    mock_doc_ref.create.side_effect = AlreadyExists("Duplicate")
    mock_db_client.collection.return_value.document.return_value = mock_doc_ref
    
    labeler = GitHubPRLabeler()
    labeler.network_client = MagicMock()
    
    labeler.run_hook(mock_task, {"status": "PASS"})
    
    labeler.network_client.request.assert_not_called()
    assert mock_emit.call_count == 2  # Once for "lobster:reviewed", once for "lobster:approved"
    assert mock_emit.call_args_list[0][0][1] == "GITHUB_PR_LABELER_SKIPPED"
    assert mock_emit.call_args_list[1][0][1] == "GITHUB_PR_LABELER_SKIPPED"

def test_run_hook_skip_non_pr_source(mock_task):
    mock_task.source = "discord_slash"
    labeler = GitHubPRLabeler()
    
    with patch("workflows.storage.db.DB.get_client") as mock_db:
        labeler.run_hook(mock_task, {"status": "PASS"})
        mock_db.assert_not_called()
