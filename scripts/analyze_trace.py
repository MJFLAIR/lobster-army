import sys
import os
import json
import argparse
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from workflows.analytics.trace_analyzer import validate_trace, analyze_trace, compute_score

logging.basicConfig(level=logging.INFO)

def run_analysis(trace_path: str):
    if not os.path.exists(trace_path):
        print(f"Error: Trace file not found at {trace_path}")
        sys.exit(1)
        
    with open(trace_path, 'r') as f:
        try:
            trace = json.load(f)
        except Exception as e:
            print(f"Error parse JSON from {trace_path}: {e}")
            sys.exit(1)
            
    try:
        validate_trace(trace)
    except Exception as e:
        print(f"Validation Error: {e}")
        sys.exit(1)
        
    metrics = analyze_trace(trace)
    score = compute_score(metrics)
    
    # Strictly formatted CLI output requested by user:
    print("=== METRICS ===")
    print(json.dumps(metrics, indent=2))
    print("\n=== SCORE ===")
    print(int(score))
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze an execution trace and compute a reliability score.")
    parser.add_argument("trace_path", help="Path to the JSON execution trace file")
    
    args = parser.parse_args()
    
    run_analysis(args.trace_path)
