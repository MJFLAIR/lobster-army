import os
import sys

def audit_env():
    merge_enabled = os.environ.get("GITHUB_MERGE_ENABLED", "false").strip().lower()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    
    print(f"GITHUB_MERGE_ENABLED: {merge_enabled}")
    if merge_enabled != "false":
        print("FAIL: GITHUB_MERGE_ENABLED is not 'false'")
        sys.exit(1)
        
    print(f"GITHUB_TOKEN length: {len(token)}")
    if not token:
        print("FAIL: GITHUB_TOKEN is empty or missing")
        sys.exit(1)

    print("PASS: Environment variables are configured correctly for shadow mode.")

if __name__ == "__main__":
    audit_env()
