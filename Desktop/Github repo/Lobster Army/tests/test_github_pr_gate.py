import pytest
import json
from unittest.mock import patch, MagicMock
from workflows.models.task import Task
from tools.github_pr_gate import GitHubPRGate, GATE_VERSION
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

def test_decide_gate_pass_by_status():
    gate = GitHubPRGate()
    label, reason, basis = gate.decide_gate({"status": "PASS"})
    assert label == "lobster:gate-pass"
    assert reason == "status=PASS"
    assert basis == "status"
    
    label2, reason2, basis2 = gate.decide_gate({"status": "approved"})
    assert label2 == "lobster:gate-pass"
    assert basis2 == "status"

def test_decide_gate_block_by_status():
    gate = GitHubPRGate()
    label, reason, basis = gate.decide_gate({"status": "fail"})
    assert label == "lobster:gate-block"
    assert reason == "status=fail"
    assert basis == "status"

def test_decide_gate_pass_by_score():
    gate = GitHubPRGate()
    label, reason, basis = gate.decide_gate({"score": 0.85})
    assert label == "lobster:gate-pass"
    assert reason == "score=0.85"
    assert basis == "score"

def test_decide_gate_block_default_no_fields():
    gate = GitHubPRGate()
    label, reason, basis = gate.decide_gate({})
    assert label == "lobster:gate-block"
    assert reason == "no_status_or_score"
    assert basis == "none"
    
    label2, reason2, basis2 = gate.decide_gate({"score": 0.7})
    assert label2 == "lobster:gate-block"
    assert reason2 == "score=0.7"
    assert basis2 == "score"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_gate_disabled_or_missing_token_no_network_call(mock_emit, mock_db, mock_env, mock_task):
    mock_env.side_effect = lambda k, d="": "0" if k == "GITHUB_GATE_ENABLED" else d
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    gate.run_hook(mock_task, {"status": "PASS"})
    
    gate.network_client.request.assert_not_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_GATE_SKIPPED"
    assert mock_emit.call_args[0][2]["reason"] == "disabled"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_gate_missing_token_no_network_call(mock_emit, mock_db, mock_env, mock_task):
    mock_env.side_effect = lambda k, d="": "1" if k == "GITHUB_GATE_ENABLED" else ("" if k == "GITHUB_TOKEN" else d)
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    gate.run_hook(mock_task, {"status": "PASS"})
    
    gate.network_client.request.assert_not_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][1] == "GITHUB_PR_GATE_SKIPPED"
    assert mock_emit.call_args[0][2]["reason"] == "missing_token"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_run_hook_dedup_already_exists_skips_post(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_GATE_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        return d
    mock_env.side_effect = mock_env_vars
    
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    
    mock_doc_ref = MagicMock()
    mock_doc_ref.create.side_effect = AlreadyExists("Duplicate")
    mock_db_client.collection.return_value.document.return_value = mock_doc_ref
    
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    gate.run_hook(mock_task, {"status": "PASS"})
    
    gate.network_client.request.assert_not_called()
    assert mock_emit.call_count == 2
    
    # First call is the policy snapshot
    assert mock_emit.call_args_list[0][0][1] == "PR_GATE_POLICY_SNAPSHOT"
    
    # Second call is the skip event
    assert mock_emit.call_args_list[1][0][1] == "GITHUB_PR_GATE_SKIPPED"
    assert mock_emit.call_args_list[1][0][2]["reason"] == "duplicate_label"

@patch("os.environ.get")
@patch("tools.github_pr_gate.NetworkClient.request")
def test_post_gate_label_builds_correct_request(mock_request, mock_env):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_GATE_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    mock_request.return_value = b'{"success": true}'
    
    gate = GitHubPRGate()
    res = gate.post_gate_label("lobster/repo", 42, "lobster:gate-pass")
    
    assert res["ok"] is True
    mock_request.assert_called_once()
    kwargs = mock_request.call_args[1]
    assert kwargs["url"] == "https://api.github.com/repos/lobster/repo/issues/42/labels"
    assert kwargs["headers"]["Authorization"] == "Bearer mock_token"
    assert json.loads(kwargs["body"].decode()) == {"labels": ["lobster:gate-pass"]}

def test_note_disabled_default_no_comment_call(mock_task):
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    res = gate.maybe_post_gate_note(mock_task, "lobster/repo", 42, "sha123", "lobster:gate-pass", "status=PASS")
    assert res == {"ok": False, "skipped": True, "reason": "note_disabled"}
    gate.network_client.request.assert_not_called()

@patch("os.environ.get")
@patch("tools.github_pr_gate.NetworkClient.request")
def test_note_enabled_posts_comment_request(mock_request, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_GATE_NOTE_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    mock_request.return_value = b'{"success": true}'
    
    gate = GitHubPRGate()
    res = gate.maybe_post_gate_note(mock_task, "lobster/repo", 42, "sha123", "lobster:gate-pass", "status=PASS")
    
    assert res["ok"] is True
    mock_request.assert_called_once()
    kwargs = mock_request.call_args[1]
    assert kwargs["url"] == "https://api.github.com/repos/lobster/repo/issues/42/comments"
    
    body = json.loads(kwargs["body"].decode())["body"]
    assert "Gate Decision: PASS" in body
    assert "label: lobster:gate-pass" in body
    assert "reason: status=PASS" in body
    assert "task_id: 123" in body
    assert "commit: sha123" in body
    assert f"Lobster Army Gate v{GATE_VERSION}" in body

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_gate_note_dedup_includes_outcome(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_GATE_ENABLED": return "1"
        if k == "GITHUB_GATE_NOTE_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    
    mock_doc_ref = MagicMock()
    mock_doc_ref.create.side_effect = None
    mock_db_client.collection.return_value.document.return_value = mock_doc_ref
    
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    gate.run_hook(mock_task, {"status": "PASS"})
    
    # Second collection call was for the note doc:
    note_col_call = mock_db_client.collection.call_args_list[1]
    assert note_col_call[0][0] == "pr_gate_note_dedup"
    note_doc_call = mock_db_client.collection().document.call_args_list[1]
    doc_id = note_doc_call[0][0]
    
    assert "lobster:gate-pass" in doc_id
    assert GATE_VERSION in doc_id

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
def test_mutual_exclusion_removes_opposite_label(mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        if k == "GITHUB_GATE_ENABLED": return "1"
        if k == "GITHUB_TOKEN": return "mock_token"
        if k == "GITHUB_API_BASE": return "https://api.github.com"
        return d
    
    mock_env.side_effect = mock_env_vars
    mock_db_client = MagicMock()
    mock_db.return_value = mock_db_client
    mock_db_client.collection.return_value.document.return_value.create.side_effect = None
    
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    gate.run_hook(mock_task, {"status": "PASS"})
    
    # We expect 2 network calls now:
    # 1) DELETE lobster:gate-block
    # 2) POST lobster:gate-pass
    assert gate.network_client.request.call_count == 2
    
    delete_call = gate.network_client.request.call_args_list[0]
    assert delete_call[1]["method"] == "DELETE"
    assert "lobster%3Agate-block" in delete_call[1]["url"]

    post_call = gate.network_client.request.call_args_list[1]
    assert post_call[1]["method"] == "POST"
    assert json.loads(post_call[1]["body"].decode())["labels"] == ["lobster:gate-pass"]

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_snapshot_emitted_contains_minimal_fields(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        return "1" if k == "GITHUB_GATE_ENABLED" else ("mock_token" if k == "GITHUB_TOKEN" else d)
    mock_env.side_effect = mock_env_vars
    
    mock_db.return_value = MagicMock()
    mock_db.return_value.collection.return_value.document.return_value.create.side_effect = None
    
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    review_payload = {"status": "pass", "issues": [{"id": 1}, {"id": 2}]}
    gate.run_hook(mock_task, review_payload)
    
    # Check that emit_event was called with PR_GATE_POLICY_SNAPSHOT
    snapshot_calls = [c for c in mock_emit.call_args_list if c[0][1] == "PR_GATE_POLICY_SNAPSHOT"]
    assert len(snapshot_calls) == 1
    
    payload = snapshot_calls[0][0][2]
    assert payload["policy_version"] == GATE_VERSION
    assert payload["decision"] == "PASS"
    assert payload["decision_basis"] == "status"
    assert payload["threshold"] == 0.8
    assert isinstance(payload["status_allowlist"], list)
    
    summary = payload["input_summary"]
    assert summary["repo"] == "lobster/repo"
    assert summary["pr_number"] == 42
    assert summary["head_sha"] == "sha123"
    assert summary["review_status"] == "pass"
    assert summary["issue_count"] == 2
    assert summary["task_id"] == 123
    assert summary["score"] is None

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_snapshot_decision_basis_score(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        return "1" if k == "GITHUB_GATE_ENABLED" else ("mock_token" if k == "GITHUB_TOKEN" else d)
    mock_env.side_effect = mock_env_vars
    
    mock_db.return_value = MagicMock()
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    gate.run_hook(mock_task, {"score": 0.81})
    
    snapshot_calls = [c for c in mock_emit.call_args_list if c[0][1] == "PR_GATE_POLICY_SNAPSHOT"]
    assert len(snapshot_calls) == 1
    
    payload = snapshot_calls[0][0][2]
    assert payload["decision"] == "PASS"
    assert payload["decision_basis"] == "score"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.get_client")
@patch("workflows.storage.db.DB.emit_event")
def test_snapshot_decision_basis_none(mock_emit, mock_db, mock_env, mock_task):
    def mock_env_vars(k, d=""):
        return "1" if k == "GITHUB_GATE_ENABLED" else ("mock_token" if k == "GITHUB_TOKEN" else d)
    mock_env.side_effect = mock_env_vars
    
    mock_db.return_value = MagicMock()
    gate = GitHubPRGate()
    gate.network_client = MagicMock()
    
    gate.run_hook(mock_task, {})
    
    snapshot_calls = [c for c in mock_emit.call_args_list if c[0][1] == "PR_GATE_POLICY_SNAPSHOT"]
    assert len(snapshot_calls) == 1
    
    payload = snapshot_calls[0][0][2]
    assert payload["decision"] == "BLOCK"
    assert payload["decision_basis"] == "none"

@patch("os.environ.get")
def test_env_override_threshold(mock_env):
    mock_env.side_effect = lambda k, d="": "0.9" if k == "GATE_SCORE_THRESHOLD" else d
    gate = GitHubPRGate()
    assert gate.gate_threshold == 0.9

@patch("os.environ.get")
def test_env_invalid_threshold_fallback(mock_env):
    mock_env.side_effect = lambda k, d="": "abc" if k == "GATE_SCORE_THRESHOLD" else d
    gate = GitHubPRGate()
    assert gate.gate_threshold == 0.8

@patch("os.environ.get")
def test_env_override_allowlist(mock_env):
    mock_env.side_effect = lambda k, d="": "pass,strong-pass " if k == "GATE_STATUS_ALLOWLIST" else d
    gate = GitHubPRGate()
    assert gate.status_allowlist == {"pass", "strong-pass"}

@patch("os.environ.get")
def test_env_empty_allowlist_fallback(mock_env):
    mock_env.side_effect = lambda k, d="": "  ,  " if k == "GATE_STATUS_ALLOWLIST" else d
    gate = GitHubPRGate()
    assert gate.status_allowlist == {"pass", "passed", "approve", "approved", "ok"}

@patch("os.environ.get")
def test_threshold_clamped_high(mock_env):
    mock_env.side_effect = lambda k, d="": "2.5" if k == "GATE_SCORE_THRESHOLD" else d
    gate = GitHubPRGate()
    assert gate.gate_threshold == 1.0

@patch("os.environ.get")
def test_threshold_clamped_low(mock_env):
    mock_env.side_effect = lambda k, d="": "-0.5" if k == "GATE_SCORE_THRESHOLD" else d
    gate = GitHubPRGate()
    assert gate.gate_threshold == 0.0
