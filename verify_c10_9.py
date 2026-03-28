import json
import logging
import time
from datetime import datetime, timezone
import sys
from io import StringIO

from workflows.strategy.incident_manager import process_incident
from workflows.strategy.incident_store import load_store, save_store
from workflows.strategy.dashboard_builder import build_dashboard_snapshot
from workflows.strategy.digest_builder import build_daily_digest
from workflows.strategy.incident_trend import classify_trend, compute_system_status

# Setup string IO intercept for logs
log_stream = StringIO()
logging.basicConfig(stream=log_stream, level=logging.INFO, force=True)

def print_header(title):
    print(f"\n{'='*50}\n# {title}\n{'='*50}")

save_store({"incidents": {}})

print_header("1️⃣ INCIDENT STORE SNAPSHOT CHECK")
inc_1 = process_incident({"failure_type": "database", "pipeline": "code_pipeline", "severity": "high", "error": "db timeout"})
store = load_store()
incident_hash = inc_1["incident_hash"]
inc_data = store["incidents"][incident_hash]
print(json.dumps({
    "incident_id": incident_hash,
    "count": inc_data["count"],
    "count_24h_snapshot": inc_data["count_24h_snapshot"],
    "snapshot_timestamp": inc_data["snapshot_timestamp"],
    "delta_24h": inc_data.get("delta_24h", 0),
    "trend": inc_data.get("trend", "stable")
}, indent=2))

print_header("2️⃣ TIME LOCK VALIDATION (CRITICAL)")
print("STEP A (Before):")
print(f"snapshot_timestamp: {inc_data['snapshot_timestamp']}")
print(f"count_24h_snapshot: {inc_data['count_24h_snapshot']}")
print(f"count: {inc_data['count']}")

process_incident({"failure_type": "database", "pipeline": "code_pipeline", "severity": "high", "error": "db timeout"})
store = load_store()
inc_data_after = store["incidents"][incident_hash]
print("\nSTEP B (After < 1 minute):")
print(f"snapshot_timestamp: {inc_data_after['snapshot_timestamp']}")
print(f"count_24h_snapshot: {inc_data_after['count_24h_snapshot']}")
print(f"count: {inc_data_after['count']}")

print_header("3️⃣ 24H ROLLOVER SIMULATION")
now = datetime.now(timezone.utc).timestamp()
inc_data_after["snapshot_timestamp"] = now - 86405
store["incidents"][incident_hash] = inc_data_after
save_store(store)
print("Before update (Shifted back 24h+):")
print(f"snapshot_timestamp: {inc_data_after['snapshot_timestamp']}")
print(f"count_24h_snapshot: {inc_data_after['count_24h_snapshot']}")
print(f"count: {inc_data_after['count']}")

process_incident({"failure_type": "database", "pipeline": "code_pipeline", "severity": "high", "error": "db timeout"})
store = load_store()
inc_data_rolled = store["incidents"][incident_hash]
print("\nAfter update (>24h):")
print(f"snapshot_timestamp: {inc_data_rolled['snapshot_timestamp']}")
print(f"count_24h_snapshot: {inc_data_rolled['count_24h_snapshot']}")
print(f"count: {inc_data_rolled['count']}")
print(f"delta_24h: {inc_data_rolled.get('delta_24h')}")

print_header("4️⃣ DELTA CORRECTNESS CHECK")
print("Case A (count == snapshot -> delta = 0)")
print(f"count: {inc_data_rolled['count']} / snapshot: {inc_data_rolled['count_24h_snapshot']} / delta: {inc_data_rolled.get('delta_24h')} / trend: {inc_data_rolled.get('trend')}")

print("\nCase B (count > snapshot -> small increase)")
for _ in range(3): process_incident({"failure_type": "database", "pipeline": "code_pipeline", "severity": "high", "error": "db timeout"})
store = load_store()
inc_case_b = store["incidents"][incident_hash]
print(f"count: {inc_case_b['count']} / snapshot: {inc_case_b['count_24h_snapshot']} / delta: {inc_case_b.get('delta_24h')} / trend: {inc_case_b.get('trend')}")

print("\nCase C (count >> snapshot -> large increase)")
for _ in range(8): process_incident({"failure_type": "database", "pipeline": "code_pipeline", "severity": "high", "error": "db timeout"})
store = load_store()
inc_case_c = store["incidents"][incident_hash]
print(f"count: {inc_case_c['count']} / snapshot: {inc_case_c['count_24h_snapshot']} / delta: {inc_case_c.get('delta_24h')} / trend: {inc_case_c.get('trend')}")

print_header("5️⃣ TREND CLASSIFICATION VALIDATION")
print("delta=15 ->", classify_trend(15))
print("delta=10 ->", classify_trend(10))
print("delta=5  ->", classify_trend(5))
print("delta=1  ->", classify_trend(1))
print("delta=0  ->", classify_trend(0))

print_header("6️⃣ SYSTEM STATUS VALIDATION")
sum_critical = {"top_incidents": [{"priority_level": "P1", "trend": "spiking"}]}
print("CASE 1 (P1 + spiking) ->", compute_system_status(sum_critical))

sum_degraded = {"top_incidents": [{"priority_level": "P1", "trend": "rising"}]}
print("CASE 2 (P1 + rising) ->", compute_system_status(sum_degraded))

sum_healthy = {"top_incidents": [{"priority_level": "P2", "trend": "spiking"}]}
print("CASE 3 (No P1) ->", compute_system_status(sum_healthy))

print_header("7️⃣ DASHBOARD OUTPUT CHECK")
snap = build_dashboard_snapshot()
print(json.dumps(snap, indent=2))

print_header("8️⃣ DIGEST OUTPUT CHECK")
digest = build_daily_digest()
print(digest["summary_text"])

print_header("9️⃣ LOGGING VERIFICATION")
logs = log_stream.getvalue()
for log in logs.split("\n"):
    if "INCIDENT_DELTA" in log or "INCIDENT_TREND" in log or "SYSTEM_STATUS_COMPUTED" in log:
        print(log)

