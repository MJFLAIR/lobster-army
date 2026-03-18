import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

# -----------------------------
# Configuration
# -----------------------------

# Only process this repo
TARGET_REPOS = (
    "MJFLAIR/lobster-army",
)

# Allowed PR events
ALLOWED_EVENTS = (
    "opened",
    "synchronize",
    "reopened",
)

# Ignore common bot accounts
IGNORED_BOTS = {
    "dependabot[bot]",
    "github-actions[bot]",
    "renovate[bot]",
}

# Branch prefixes that do NOT require AI pipeline
IGNORED_BRANCH_PREFIXES = (
    "docs/",
    "chore/",
    "dependabot/",
    "renovate/",
    "release/",
    "bump/",
)


# -----------------------------
# Core Filter Logic
# -----------------------------

def should_process_pr(payload: Dict[str, Any], action: str) -> bool:
    """
    Determine whether a GitHub PR webhook should trigger the AI pipeline.

    True  -> create Firestore task
    False -> skip silently
    """

    # 1️⃣ Validate action
    if action not in ALLOWED_EVENTS:
        log.info("[PR_FILTER_SKIP] unsupported action=%s", action)
        return False

    pr = payload.get("pull_request")
    if not pr:
        log.info("[PR_FILTER_SKIP] payload missing pull_request")
        return False

    # 2️⃣ Validate repository
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "")

    if repo_name not in TARGET_REPOS:
        log.info("[PR_FILTER_SKIP] repo not allowed repo=%s", repo_name)
        return False

    # 3️⃣ PR must be open
    state = pr.get("state")

    if state != "open":
        log.info("[PR_FILTER_SKIP] PR not open state=%s", state)
        return False

    # 4️⃣ Ignore bots
    user = pr.get("user", {})
    login = user.get("login", "")
    user_type = user.get("type", "")

    if user_type == "Bot" or login in IGNORED_BOTS:
        log.info("[PR_FILTER_SKIP] bot detected user=%s", login)
        return False

    # 5️⃣ Branch prefix filter (Pythonic tuple version)
    head = pr.get("head", {})
    branch = head.get("ref", "")

    if branch.startswith(IGNORED_BRANCH_PREFIXES):
        log.info(
            "[PR_FILTER_SKIP] ignored branch prefix branch=%s",
            branch,
        )
        return False

    # Passed all checks
    pr_number = pr.get("number")

    log.info(
        "[PR_FILTER_PASS] repo=%s pr=%s action=%s branch=%s",
        repo_name,
        pr_number,
        action,
        branch,
    )

    return True