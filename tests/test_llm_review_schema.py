from workflows.models.llm_review import safe_parse_llm_review, clamp01

def test_clamp01_basic():
    assert clamp01(0.5) == 0.5
    assert clamp01(-1) == 0.0
    assert clamp01(2) == 1.0
    assert clamp01("bad") == 0.0

def test_safe_parse_valid():
    obj = {"decision": "approve", "score": 0.9, "reason": "ok"}
    res, err = safe_parse_llm_review(obj)
    assert err is None
    assert res is not None
    assert res.decision == "approve"
    assert res.score == 0.9
    assert res.reason == "ok"

def test_safe_parse_clamps_score():
    obj = {"decision": "approve", "score": 9, "reason": "ok"}
    res, err = safe_parse_llm_review(obj)
    assert err is None
    assert res.score == 1.0

def test_safe_parse_rejects_missing_keys():
    obj = {"decision": "approve", "score": 0.9}
    res, err = safe_parse_llm_review(obj)
    assert res is None
    assert err == "schema_invalid"

def test_safe_parse_rejects_not_dict():
    res, err = safe_parse_llm_review("not a dict")
    assert res is None
    assert err == "payload_not_dict"

def test_safe_parse_rejects_bad_decision():
    obj = {"decision": "maybe", "score": 0.9, "reason": "ok"}
    res, err = safe_parse_llm_review(obj)
    assert res is None
    assert err == "schema_invalid"
