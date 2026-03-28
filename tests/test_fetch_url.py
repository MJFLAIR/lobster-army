import pytest
from unittest.mock import patch, MagicMock
from tools.fetch_url import fetch_url

def test_fetch_url_whitelist_success():
    with patch('requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [b'{"name": "test"}']
        mock_get.return_value = mock_resp

        res = fetch_url("https://api.github.com/repos/test/test")
        assert res["status"] == "success"
        assert res["content"] == '{"name": "test"}'
        mock_get.assert_called_once()

def test_fetch_url_blocked_domain():
    res = fetch_url("https://example.com/api")
    assert res["status"] == "failed"
    assert "Domain not allowed: example.com" in res["error"]

def test_fetch_url_localhost():
    # Fails whitelist
    res = fetch_url("http://127.0.0.1:8080/admin")
    assert res["status"] == "failed"

    # Fails internal block despite passing whitelist
    res = fetch_url("https://api.github.com/?q=127.0.0.1")
    assert res["status"] == "failed"
    assert "Internal network access blocked" in res["error"]
    
    res = fetch_url("https://api.github.com/localhost")
    assert res["status"] == "failed"
    assert "Internal network access blocked" in res["error"]
    
    res = fetch_url("https://api.github.com/169.254.169.254")
    assert res["status"] == "failed"
    assert "Internal network access blocked" in res["error"]

def test_fetch_url_timeout():
    with patch('requests.get', side_effect=Exception("Timeout Error")):
        res = fetch_url("https://api.github.com/timeout")
        assert res["status"] == "failed"
        assert "Timeout Error" in res["error"]

def test_fetch_url_large_response():
    with patch('requests.get') as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # mock_resp needs an iter_content method for the new stream logic
        mock_resp.iter_content.return_value = [b"A" * 100_001]
        mock_get.return_value = mock_resp

        res = fetch_url("https://api.github.com/large")
        assert res["status"] == "failed"
        assert "Response size exceeded 100KB limit" in res["error"]
