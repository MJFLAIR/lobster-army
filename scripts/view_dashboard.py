#!/usr/bin/env python3
import sys
import os
import json

# Add project root to path for workflow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from workflows.strategy.failure_pattern_tracker import summarize_failure_stats

# ANSI Colors
C_RESET = "\033[0m"
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"

def load_events(log_path="logs/failure_patterns.jsonl"):
    events = []
    if not os.path.exists(log_path):
        return events
        
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events

def print_header(title):
    print(f"\n{C_CYAN}{C_BOLD}=== {title} ==={C_RESET}")

def render_dashboard():
    log_path = "logs/failure_patterns.jsonl"
    events = load_events(log_path)
    
    if not events:
        print(f"{C_YELLOW}No observability data found at {log_path}. Dashboard empty.{C_RESET}")
        return
        
    stats = summarize_failure_stats(events)
    total_events = stats['total_events']
    
    # Calculate template specific success rates manually
    template_stats = {}
    ftype_stats = {}
    
    for e in events:
        t_used = e.get("template_used", "NONE")
        if t_used not in template_stats:
            template_stats[t_used] = {"used": 0, "success": 0}
            
        template_stats[t_used]["used"] += 1
        if e.get("retry_success"):
            template_stats[t_used]["success"] += 1
            
        ft = e.get("initial_failure_type", "unknown")
        if ft not in ftype_stats:
            ftype_stats[ft] = {"total": 0, "attempted": 0, "success": 0}
            
        ftype_stats[ft]["total"] += 1
        if e.get("retry_triggered"):
            ftype_stats[ft]["attempted"] += 1
            if e.get("retry_success"):
                ftype_stats[ft]["success"] += 1
            
    print(f"\n{C_BOLD}🦞 LOBSTER ARMY SELF-HEALING DASHBOARD 🦞{C_RESET}")
    
    print_header("SYSTEM OVERVIEW")
    rate_str = f"{stats['retry_success_rate']*100:.1f}%" if stats['total_retry_triggered'] > 0 else "0.0%"
    color_rate = C_GREEN if stats['retry_success_rate'] > 0 else C_YELLOW
    print(f"Total Events:         {stats['total_events']}")
    print(f"Retries Triggered:    {stats['total_retry_triggered']}")
    print(f"Retries Succeeded:    {stats['total_retry_success']}")
    print(f"Retry Success Rate:   {color_rate}{rate_str}{C_RESET}")
    
    print_header("FAILURE DISTRIBUTION")
    sorted_failures = sorted(stats["failures_by_type"].items(), key=lambda x: x[1], reverse=True)
    for f_type, count in sorted_failures:
        perc = (count / total_events * 100) if total_events > 0 else 0.0
        print(f"  {f_type}: {count} ({perc:.1f}%)")
        
    print_header("RETRY EFFECTIVENESS (BY TYPE)")
    sorted_ftypes = sorted(ftype_stats.items(), key=lambda x: x[1]["total"], reverse=True)
    for ft, data in sorted_ftypes:
        print(f"  {C_BOLD}{ft}{C_RESET}:")
        print(f"    total: {data['total']}")
        print(f"    retry_attempted: {data['attempted']}")
        print(f"    retry_success: {data['success']}")
        
        attempted = data["attempted"]
        rate = (data["success"] / attempted * 100.0) if attempted > 0 else 0.0
        c_col = C_GREEN if rate >= 70 else C_YELLOW if rate >= 40 else C_RED
        print(f"    success_rate: {c_col}{rate:.1f}%{C_RESET}")
        
    print_header("TEMPLATE EFFECTIVENESS")
    sorted_templates = sorted(template_stats.items(), key=lambda x: x[1]["used"], reverse=True)
    for t_used, data in sorted_templates:
        if t_used == "NONE":
            continue
        used = data["used"]
        succ = data["success"]
        rate = (succ / used * 100) if used > 0 else 0.0
        c_color = C_GREEN if rate >= 70 else C_YELLOW if rate >= 40 else C_RED
        print(f"  {C_BOLD}{t_used}{C_RESET}:")
        print(f"    used: {used}")
        print(f"    success: {succ}")
        print(f"    success_rate: {c_color}{rate:.1f}%{C_RESET}")
        
    print_header("SYSTEM HEALTH SIGNAL")
    total_triggered = stats['total_retry_triggered']
    overall_rate = (stats['retry_success_rate'] * 100.0) if total_triggered > 0 else 0.0
    
    if overall_rate >= 70:
        health_status = "🟢 HEALTHY"
    elif overall_rate >= 40:
        health_status = "🟡 WARNING"
    else:
        health_status = "🔴 CRITICAL"
        
    print(f"  Overall Retry Success Rate: {overall_rate:.1f}%")
    print(f"  System Status: {health_status}")
    
    print_header("RECENT TREND (LAST 10)")
    recent_10 = events[-10:]
    trend_counts = {}
    for r in recent_10:
        st = r.get("final_status", "unknown")
        trend_counts[st] = trend_counts.get(st, 0) + 1
        
    for st, count in sorted(trend_counts.items(), key=lambda x: x[1], reverse=True):
        color = C_GREEN if st in ["PATCH_READY", "PR_READY", "DRAFT_PR_READY"] else C_RED
        print(f"  {color}{st}{C_RESET}: {count}")
        
    print("")

if __name__ == "__main__":
    render_dashboard()
