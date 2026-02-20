import os
import sys
import re

def check_hard_rules(root_dir="."):
    """
    Scans the codebase for forbidden patterns and safety violations.
    Returns return code 1 if violations found, 0 otherwise.
    """
    violations = []
    
    # 1. Check for hardcoded secrets (Basic heuristics)
    secret_patterns = [
        r"sk-[a-zA-Z0-9]{32,}", # OpenAI key like
        r"ghp_[a-zA-Z0-9]{30,}", # GitHub Token
        r"AIza[0-9A-Za-z-_]{35}" # Google API Key
    ]
    
    # 2. Check for dangerous functions
    dangerous_patterns = [
        (r"subprocess\.run\(.*shell=True.*\)", "subprocess with shell=True"),
        (r"eval\(", "eval() usage"),
        (r"exec\(", "exec() usage"),
        (r"print\(", "print() usage (Use logging instead)") 
    ]
    
    # 3. Directories to scan (skip venv, .git, __pycache__)
    for dirpath, _, filenames in os.walk(root_dir):
        if any(x in dirpath for x in [".venv", ".git", "__pycache__", "tests"]):
            continue
            
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
                
            filepath = os.path.join(dirpath, filename)
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    
                    # Secrets Check
                    for pattern in secret_patterns:
                        if re.search(pattern, content):
                            violations.append(f"[SECRET] Potential secret in {filepath}")
                            
                    # Safety Check
                    for pattern, desc in dangerous_patterns:
                        if re.search(pattern, content):
                            # Allow print in scripts/
                            if "scripts/" in filepath and "print" in pattern:
                                continue
                            # Allow eval/exec in check_hard_rules.py (it checks for them!)
                            if "check_hard_rules.py" in filename:
                                continue
                            violations.append(f"[SAFETY] {desc} found in {filepath}")
                            
            except Exception as e:
                print(f"Skipping {filepath}: {e}")

    # 4. Requirements check
    if not os.path.exists("requirements.txt"):
        violations.append("[CONFIG] requirements.txt missing")
        
    if violations:
        print("Hard Rules Violations Found:")
        for v in violations:
            print(f"  - {v}")
        return 1
    else:
        print("Hard Rules Check Passed.")
        return 0

if __name__ == "__main__":
    sys.exit(check_hard_rules())
