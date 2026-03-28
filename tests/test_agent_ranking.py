import pytest
from workflows.analytics.performance_store import PerformanceStore, rank_agents

def test_aggregation():
    """Test 1 — Aggregation: Multiple metrics inputs update correctly, calls and failures accumulate."""
    store = PerformanceStore()
    m1 = {
        "agent_metrics": {
            "Feature_Coder": {"calls": 5, "failures": 1}
        }
    }
    m2 = {
        "agent_metrics": {
            "Feature_Coder": {"calls": 5, "failures": 1}
        }
    }
    store.update_agent_performance(m1)
    store.update_agent_performance(m2)
    
    stats = store.store["Feature_Coder"]
    assert stats["total_calls"] == 10
    assert stats["total_failures"] == 2

def test_success_rate_math():
    """Test 2 — Success Rate Math: Exact percentage math is correct."""
    store = PerformanceStore()
    m = {
        "agent_metrics": {
            "Reviewer": {"calls": 15, "failures": 1}
        }
    }
    store.update_agent_performance(m)
    assert round(store.store["Reviewer"]["success_rate"], 2) == 93.33

def test_ranking_order():
    """Test 3 — Ranking Order: High success rate ranks above lower success rate."""
    store = PerformanceStore()
    m = {
        "agent_metrics": {
            "Feature_Coder": {"calls": 10, "failures": 2}, # 80.00%
            "Reviewer": {"calls": 10, "failures": 1} # 90.00%
        }
    }
    store.update_agent_performance(m)
    ranked = rank_agents(store)
    assert ranked[0][0] == "Reviewer"
    assert ranked[1][0] == "Feature_Coder"

def test_tie_breaker_calls():
    """Test 4 — Tie Breaker: Same success rate → more calls wins."""
    store = PerformanceStore()
    m = {
        "agent_metrics": {
            "Feature_Coder": {"calls": 10, "failures": 2}, # 80%
            "PMAgent": {"calls": 5, "failures": 1} # 80%
        }
    }
    store.update_agent_performance(m)
    ranked = rank_agents(store)
    assert ranked[0][0] == "Feature_Coder"
    assert ranked[1][0] == "PMAgent"

def test_tie_breaker_alpha():
    """Test 5 — Final Determinism: Same success rate + same calls → alphabetical agent name wins."""
    store = PerformanceStore()
    m = {
        "agent_metrics": {
            "Reviewer": {"calls": 10, "failures": 0}, # 100%
            "PMAgent": {"calls": 10, "failures": 0} # 100%
        }
    }
    store.update_agent_performance(m)
    ranked = rank_agents(store)
    # 'P' comes before 'R' in alphabet, so PMAgent should be first
    assert ranked[0][0] == "PMAgent"
    assert ranked[1][0] == "Reviewer"

def test_unknown_agents_rejected():
    """Ensure agent registry properly filters malformed unknown entries."""
    store = PerformanceStore()
    m = {
        "agent_metrics": {
            "Unknown_Hacker_Agent": {"calls": 10, "failures": 0}
        }
    }
    store.update_agent_performance(m)
    assert "Unknown_Hacker_Agent" not in store.store
    assert len(store.store) == 0
