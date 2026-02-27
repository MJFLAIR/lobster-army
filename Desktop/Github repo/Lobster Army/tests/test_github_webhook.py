import pytest
import hmac
import hashlib
import json
from unittest.mock import patch, MagicMock
from google.api_core.exceptions import AlreadyExists
from runtime.app import create_app

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        "TESTING": True,
    })
    yield app

@pytest.fixture
def client(app):
    return app.test_client()

def generate_signature(secret: str, payload: bytes) -> str:
    hmac_gen = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256)
    return f"sha256={hmac_gen.hexdigest()}"

@patch("os.environ.get")
@patch("workflows.storage.db.DB.create_task")
def test_github_webhook_missing_signature(mock_create_task, mock_env, client):
    mock_env.return_value = "test_secret"
    
    response = client.post(
        "/api/webhook/github", 
        data=json.dumps({"action": "opened"}),
        headers={"Content-Type": "application/json"}
    )
    
    assert response.status_code == 401
    assert response.json == {"ok": False, "error": "bad_signature"}
    mock_create_task.assert_not_called()

@patch("os.environ.get")
@patch("workflows.storage.db.DB.create_task")
def test_github_webhook_invalid_signature(mock_create_task, mock_env, client):
    mock_env.return_value = "test_secret"
    payload = json.dumps({"action": "opened"}).encode('utf-8')
    
    response = client.post(
        "/api/webhook/github",
        data=payload,
        headers={
            "X-Hub-Signature-256": "sha256=invalid",
            "Content-Type": "application/json"
        }
    )
    
    assert response.status_code == 401
    assert response.json == {"ok": False, "error": "bad_signature"}
    mock_create_task.assert_not_called()

@patch("os.environ.get")
@patch("workflows.storage.db.DB.create_task")
def test_github_webhook_ignored_event(mock_create_task, mock_env, client):
    mock_env.return_value = "test_secret"
    payload = json.dumps({"action": "created"}).encode('utf-8')
    signature = generate_signature("test_secret", payload)
    
    response = client.post(
        "/api/webhook/github",
        data=payload,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "issue_comment",
            "Content-Type": "application/json"
        }
    )
    
    assert response.status_code == 200
    assert response.json == {"ok": True, "ignored": True}
    mock_create_task.assert_not_called()

@patch("os.environ.get")
@patch("workflows.storage.db.DB.create_task")
def test_github_webhook_ignored_action(mock_create_task, mock_env, client):
    mock_env.return_value = "test_secret"
    payload = json.dumps({"action": "closed"}).encode('utf-8')
    signature = generate_signature("test_secret", payload)
    
    response = client.post(
        "/api/webhook/github",
        data=payload,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json"
        }
    )
    
    assert response.status_code == 200
    assert response.json == {"ok": True, "ignored": True}
    mock_create_task.assert_not_called()

@patch("workflows.storage.db.DB.get_client")
@patch("os.environ.get")
@patch("workflows.storage.db.DB.create_task")
def test_github_webhook_success(mock_create_task, mock_env, mock_get_client, client):
    mock_env.return_value = "test_secret"
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db
    
    mock_doc_ref = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_doc_ref
    
    payload_dict = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Add cool feature",
            "html_url": "https://github.com/lobster/repo/pull/42",
            "head": {"sha": "headsha123", "ref": "feature-branch"},
            "base": {"ref": "main"}
        },
        "repository": {"full_name": "lobster/repo"},
        "sender": {"login": "test_user"}
    }
    payload = json.dumps(payload_dict).encode('utf-8')
    signature = generate_signature("test_secret", payload)
    
    response = client.post(
        "/api/webhook/github",
        data=payload,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json"
        }
    )
    
    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["pr"] == 42
    assert "task_id" in response.json
    
    mock_create_task.assert_called_once()
    task = mock_create_task.call_args[0][0]
    assert task.source == "github_pr"
    assert task.requester_id == "test_user"
    assert "Review PR #42: Add cool feature" in task.description
    assert task.meta_json["action"] == "opened"
    assert task.meta_json["pull_request"]["number"] == 42
    assert task.plan_json is None

@patch("workflows.storage.db.DB.get_client")
@patch("os.environ.get")
@patch("workflows.storage.db.DB.create_task")
def test_github_webhook_idempotency(mock_create_task, mock_env, mock_get_client, client):
    mock_env.return_value = "test_secret"
    
    mock_db = MagicMock()
    mock_get_client.return_value = mock_db
    
    mock_doc_ref = MagicMock()
    mock_doc_ref.create.side_effect = None
    mock_db.collection.return_value.document.return_value = mock_doc_ref
    
    payload_dict = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Add cool feature",
            "html_url": "https://github.com/lobster/repo/pull/42",
            "head": {"sha": "headsha123", "ref": "feature-branch"},
            "base": {"ref": "main"}
        },
        "repository": {"full_name": "lobster/repo"},
        "sender": {"login": "test_user"}
    }
    payload = json.dumps(payload_dict).encode('utf-8')
    signature = generate_signature("test_secret", payload)
    
    # 1. First webhook -> Create Task
    response1 = client.post(
        "/api/webhook/github",
        data=payload,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json"
        }
    )
    
    assert response1.status_code == 200
    assert response1.json["ok"] is True
    assert "task_id" in response1.json
    mock_create_task.assert_called_once()
    mock_doc_ref.create.assert_called_once()
    
    # 2. Duplicate webhook -> Ignored (AlreadyExists exception raised)
    mock_doc_ref.create.side_effect = AlreadyExists("Mock document already exists")
    
    response2 = client.post(
        "/api/webhook/github",
        data=payload,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json"
        }
    )
    
    assert response2.status_code == 200
    assert response2.json == {"ok": True, "ignored": True, "reason": "duplicate"}
    assert mock_create_task.call_count == 1
    
    # 3. Different head_sha webhook -> Create Task
    mock_doc_ref.create.side_effect = None
    payload_dict["pull_request"]["head"]["sha"] = "newsha456"
    payload3 = json.dumps(payload_dict).encode('utf-8')
    signature3 = generate_signature("test_secret", payload3)
    
    response3 = client.post(
        "/api/webhook/github",
        data=payload3,
        headers={
            "X-Hub-Signature-256": signature3,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json"
        }
    )
    
    assert response3.status_code == 200
    assert response3.json["ok"] is True
    assert "task_id" in response3.json
    assert mock_create_task.call_count == 2
