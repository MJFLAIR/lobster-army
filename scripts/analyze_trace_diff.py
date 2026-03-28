import json
import argparse
import sys
from collections import defaultdict

LOG_PATH = "logs/orchestration_traces.jsonl"

def analyze_diff(original_id, print_cli=True, log_path=LOG_PATH):
    original = None
    replays = []
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("incident_id") == original_id:
                        original = event
                    elif event.get("parent_incident_id") == original_id:
                        replays.append(event)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
        
    if not original:
        raise ValueError(f"Original incident {original_id} not found.")
        
    # Sort replays by timestamp ascending (earliest first, latest last)
    replays.sort(key=lambda x: x.get("timestamp", ""))
    
    latest_replay = replays[-1] if replays else None
    
    # Diff logic
    step_diffs = []
    agent_stats = defaultdict(lambda: {"recovered": 0, "regressed": 0, "unchanged": 0})
    
    recovered_count = 0
    regressed_count = 0
    
    orig_trace = {s["step_order"]: dict(s) for s in original.get("execution_trace", [])}
    replay_trace = {}
    if latest_replay:
        replay_trace = {s["step_order"]: dict(s) for s in latest_replay.get("execution_trace", [])}
        
    for order, orig_step in orig_trace.items():
        agent = orig_step.get("agent", "unknown")
        orig_status = orig_step.get("status", "skipped")
        
        if latest_replay and order in replay_trace:
            new_status = replay_trace[order].get("status", "skipped")
            
            diff_type = "UNCHANGED"
            if orig_status in ["failed", "skipped"] and new_status == "success":
                diff_type = "RECOVERED"
                recovered_count += 1
                agent_stats[agent]["recovered"] += 1
            elif orig_status == "success" and new_status in ["failed", "skipped"]:
                diff_type = "REGRESSED"
                regressed_count += 1
                agent_stats[agent]["regressed"] += 1
            else:
                agent_stats[agent]["unchanged"] += 1
                
            step_diffs.append({
                "step_order": order,
                "agent": agent,
                "from": orig_status,
                "to": new_status,
                "type": diff_type
            })

    # Sort step_diffs ascending natively 
    step_diffs.sort(key=lambda x: x["step_order"])
    
    result_json = {
        "original_incident_id": original_id,
        "replay_incident_id": latest_replay.get("incident_id") if latest_replay else None,
        "recovered_steps": recovered_count,
        "regressed_steps": regressed_count,
        "step_diffs": step_diffs,
        "agent_stats": dict(agent_stats)
    }
    
    if print_cli:
        print("EXECUTION DIFF REPORT\\n")
        print(f"Original: [{original_id}] {original.get('final_status')}")
        if latest_replay:
            print(f"Replay:   [{latest_replay.get('incident_id')}] {latest_replay.get('final_status')}\\n")
            for diff in step_diffs:
                orig_s = diff['from'].upper()
                new_s = diff['to'].upper()
                print(f"Step {diff['step_order']} [{diff['agent']}]: {orig_s} -> {new_s} ({diff['type']})")
                
            print(f"\\nRecovered Steps: {recovered_count}")
        else:
            print("Replay:   No replays found.\\n")
            
    return result_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deterministic Execution Diff Analyzer")
    parser.add_argument("incident_id", help="Original Incident ID to diff")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()
    
    res = analyze_diff(args.incident_id, print_cli=not args.json)
    if args.json:
        print(json.dumps(res, indent=2))
