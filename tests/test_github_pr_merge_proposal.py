import pytest
import json
from unittest.mock import patch, MagicMock
from workflows.models.task import Task
from tools.github_pr_merge_proposal import GitHubPRMergeProposal, PROPOSAL_VERSION
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

def test_decide_gate_outcome_pass_by_status():
    proposal = GitHubPRMergeProposal()
    assert proposal.decide_gate_outcome({"status": "PASS"}) == "PASS"
    assert proposal.decide_gate_outcome({"status": "approved"}) == "PASS"

def test_decide_gate_outcome_block_by_status():
    proposal = GitHubPRMergeProposal()
    assert proposal.decide_gate_outcome({"status": "fail"}) == "BLOCK"

def test_decide_gate_outcome_pass_by_score():
    proposal = GitHubPRMergeProposal()
    assert proposal.decide_gate_outcome({"score": 0.85}) == "PASS"
    assert proposal.decide_gate_outcome({"score": 0.7}) == "BLOCK"
    assert proposal.decide_gate_outcome({}) == "BLOCK"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_disabled_or_missing_token_no_network_call(mock_emit, mock_db, mock_env, mock_task):
    mock_env.side_effect = lambda k, d="": "0" if k == "GITHUB_MERGE_PROPOSAL_ENABLED" else d
    
    proposal = GitHubPRMergeProposal()
    proposal.network_client = MagicMock()
    proposal.run_hook(mock_task, {"status": "PASS"})
    
    proposal.network_client.request.assert_not_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_MERGE_PROPOSAL_SKIPPED"
    assert mock_emit.call_args[0][2]["reason"] == "disabled"

@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_run_hook_skip_non_pr_source(mock_emit, mock_db, mock_task):
    mock_task.source = "discord_slash"
    proposal = GitHubPRMergeProposal()
    proposal.network_client = MagicMock()
    
    proposal.run_hook(mock_task, {"status": "PASS"})
    proposal.network_client.request.assert_not_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_MERGE_PROPOSAL_SKIPPED"
    assert mock_emit.call_args[0][2]["reason"] == "non_pr_source"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_run_hook_missing_pr_metadata_skips(mock_emit, mock_db, mock_env, mock_task):
    mock_env.side_effect = lambda k, d="": "1" if k == "GITHUB_MERGE_PROPOSAL_ENABLED" else ("mock_token" if k == "GITHUB_TOKEN" else d)
    
    # Intentionally ruin metadata
    mock_task.meta_json = {}
    
    proposal = GitHubPRMergeProposal()
    proposal.network_client = MagicMock()
    proposal.run_hook(mock_task, {"status": "PASS"})
    
    proposal.network_client.request.assert_not_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_MERGE_PROPOSAL_SKIPPED"
    assert mock_emit.call_args[0][2]["reason"] == "missing_pr_metadata"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_pass_adds_label_with_correct_request(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_MERGE_PROPOSAL_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    mock_db_client.collection.return_value.document.return_value.create.side_effect = None
    
    proposal = GitHubPRMergeProposal()
    proposal.network_client = MagicMock()
    proposal.network_client.request.return_value = b'{"success": True}'
    
    proposal.run_hook(mock_task, {"status": "PASS"})
    
    proposal.network_client.request.assert_called_once()
    kwargs = proposal.network_client.request.call_args[1]
    assert kwargs["method"] == "POST"
    assert kwargs["url"] == "https://api.github.com/repos/lobster/repo/issues/42/labels"
    assert json.loads(kwargs["body"].decode())["labels"] == ["lobster:merge-candidate"]
    
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_MERGE_PROPOSAL_POSTED"
    assert mock_emit.call_args[0][2]["label"] == "lobster:merge-candidate"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_pass_dedup_already_exists_skips_post(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_MERGE_PROPOSAL_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        return d
    mock_env.side_effect = mock_env_vars
    
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    mock_db_client.collection.return_value.document.return_value.create.side_effect = AlreadyExists("Duplicate")
    
    proposal = GitHubPRMergeProposal()
    proposal.network_client = MagicMock()
    
    proposal.run_hook(mock_task, {"status": "PASS"})
    
    proposal.network_client.request.assert_not_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_MERGE_PROPOSAL_SKIPPED"
    assert mock_emit.call_args[0][2]["reason"] == "duplicate"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_block_removes_label_delete_called(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_MERGE_PROPOSAL_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    
    proposal = GitHubPRMergeProposal()
    proposal.network_client = MagicMock()
    proposal.network_client.request.return_value = b'{}'
    
    proposal.run_hook(mock_task, {"status": "fail"})
    
    proposal.network_client.request.assert_called_once()
    kwargs = proposal.network_client.request.call_args[1]
    assert kwargs["method"] == "DELETE"
    assert "lobster%3Amerge-candidate" in kwargs["url"]
    
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_MERGE_PROPOSAL_REMOVED"
    assert mock_emit.call_args[0][2]["label"] == "lobster:merge-candidate"
