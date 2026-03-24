"""
Performance Store
In-memory layer for aggregating and ranking individual agent performance.
"""
from workflows.analytics.agent_registry import is_known_agent

class PerformanceStore:
    def __init__(self):
        # Internal shape:
        # {
        #   "Feature_Coder": {
        #     "total_calls": int,
        #     "total_failures": int,
        #     "success_rate": float
        #   }
        # }
        self.store = {}

    def update_agent_performance(self, metrics: dict):
        """
        Updates agent performance from metrics accurately and deterministically.
        metrics shape expected: {"agent_metrics": {"AgentName": {"calls": int, "failures": int, ...}, ...}}
        """
        agent_metrics = metrics.get("agent_metrics", {})
        for agent_name, stats in agent_metrics.items():
            # Reject unknown agents to keep ranking stable
            if not is_known_agent(agent_name):
                continue
                
            if agent_name not in self.store:
                self.store[agent_name] = {
                    "total_calls": 0,
                    "total_failures": 0,
                    "success_rate": 0.0
                }
            
            calls = stats.get("calls", 0)
            failures = stats.get("failures", 0)
            
            self.store[agent_name]["total_calls"] += calls
            self.store[agent_name]["total_failures"] += failures
            
            # Recompute success rate deterministically
            total_calls = self.store[agent_name]["total_calls"]
            total_failures = self.store[agent_name]["total_failures"]
            
            if total_calls > 0:
                success_rate = ((total_calls - total_failures) / total_calls) * 100.0
                # Clamp between 0 and 100
                success_rate = max(0.0, min(100.0, success_rate))
            else:
                success_rate = 0.0
                
            self.store[agent_name]["success_rate"] = success_rate

def rank_agents(store: PerformanceStore) -> list:
    """
    Ranks agents deterministically based on their individual performance.
    
    Sort by:
    1. success_rate DESC
    2. total_calls DESC (tie-breaker for experience)
    3. agent_name ASC (final deterministic tie-breaker)
    
    Returns a list of tuples: [(agent_name, dict_of_stats), ...]
    """
    def sort_key(item):
        agent_name, stats = item
        return (
            -stats["success_rate"],
            -stats["total_calls"],
            agent_name
        )
        
    return sorted(store.store.items(), key=sort_key)
