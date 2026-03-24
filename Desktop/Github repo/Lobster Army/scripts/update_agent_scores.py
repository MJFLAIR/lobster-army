#!/usr/bin/env python3
"""
Update Agent Scores Script
Loads sample metrics, updates the performance store, and prints the leaderboard.
"""
import sys
import os

# Ensure the project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from workflows.analytics.performance_store import PerformanceStore, rank_agents

def main():
    store = PerformanceStore()
    
    # Sample metrics combining multiple hypothetical task traces
    sample_metrics = [
        {
            "agent_metrics": {
                "Reviewer": {"calls": 10, "failures": 1},
                "Feature_Coder": {"calls": 5, "failures": 1},
                "AutoFix_Medic": {"calls": 2, "failures": 1},
                "Unknown_Agent": {"calls": 2, "failures": 0}  # Malformed unknown entry
            }
        },
        {
            "agent_metrics": {
                "Reviewer": {"calls": 5, "failures": 0},
                "Feature_Coder": {"calls": 5, "failures": 1},
                "AutoFix_Medic": {"calls": 2, "failures": 0}
            }
        }
    ]
    
    for metrics in sample_metrics:
        store.update_agent_performance(metrics)
        
    leaderboard = rank_agents(store)
    
    print("=== AGENT LEADERBOARD ===")
    for rank, (agent_name, stats) in enumerate(leaderboard, 1):
        print(f"{rank}. {agent_name:<15} success_rate={stats['success_rate']:<5.2f} total_calls={stats['total_calls']} total_failures={stats['total_failures']}")

if __name__ == "__main__":
    main()
