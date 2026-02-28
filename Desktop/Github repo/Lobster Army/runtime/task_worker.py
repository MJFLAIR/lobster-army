from workflows.task_manager import TaskManager
from workflows.storage.db import DB

import logging
import json

class TaskWorker:
    def run_task(self, task_id: int):
        task_obj = DB.get_task(task_id)
        if task_obj:
            task = task_obj.__dict__
            if task.get("source") == "github":
                meta_json = task.get("meta_json") or {}
                if not isinstance(meta_json, dict):
                    # tolerate JSON string; if parse fails, fallback to empty dict
                    if isinstance(meta_json, str):
                        try:
                            meta_json = json.loads(meta_json)
                        except Exception:
                            meta_json = {}
                    else:
                        meta_json = {}

                # IMPORTANT: even if json.loads succeeds, it might not be a dict
                if not isinstance(meta_json, dict):
                    meta_json = {}

                action = (
                    meta_json.get("action")
                    or meta_json.get("github_action")
                    or (meta_json.get("event") or {}).get("action")  # tolerate nested
                    or "unknown_action"
                )

                repo_val = (
                    meta_json.get("repository")
                    or meta_json.get("repo")
                    or meta_json.get("repository_full_name")
                    or (meta_json.get("event") or {}).get("repository")
                )

                repo = "unknown_repo"
                if isinstance(repo_val, dict):
                    repo = (
                        repo_val.get("full_name")
                        or (
                            f"{((repo_val.get('owner') or {}).get('login') or '').strip()}/"
                            f"{(repo_val.get('name') or '').strip()}"
                        ).strip("/")
                        or "unknown_repo"
                    )
                elif isinstance(repo_val, str):
                    repo = repo_val.strip() or "unknown_repo"

                pr_number = None

                pr_val = meta_json.get("pull_request") or (meta_json.get("event") or {}).get("pull_request")
                if isinstance(pr_val, dict):
                    pr_number = pr_val.get("number")
                elif isinstance(pr_val, int):
                    pr_number = pr_val
                elif isinstance(pr_val, str):
                    # tolerate numeric string
                    try:
                        pr_number = int(pr_val.strip())
                    except Exception:
                        pr_number = None

                if pr_number is None:
                    pr_number = (
                        meta_json.get("pull_request_number")
                        or meta_json.get("pr_number")
                        or meta_json.get("number")  # common in PR event root
                        or (meta_json.get("event") or {}).get("pull_request_number")
                        or (meta_json.get("event") or {}).get("pr_number")
                        or (meta_json.get("event") or {}).get("number")
                    )

                # final normalize to int or None
                if pr_number is not None and not isinstance(pr_number, int):
                    try:
                        pr_number = int(str(pr_number).strip())
                    except Exception:
                        pr_number = None

                keys_preview = []
                try:
                    keys_preview = list(meta_json.keys())[:30] if isinstance(meta_json, dict) else []
                except Exception:
                    keys_preview = []

                logging.info(
                    "[PR_META_KEYS] meta_type=%s keys=%s extracted_action=%s extracted_repo=%s extracted_pr=%s",
                    type(meta_json).__name__,
                    keys_preview,
                    action,
                    repo,
                    pr_number,
                )

                logging.info(f"[PR_EVENT] action={action} repo={repo} pr={pr_number}")
                logging.info(f"[PR_GATE_PRECHECK] repo={repo} pr={pr_number} action={action}")

                gate_actions = {"opened", "synchronize"}
                if action in gate_actions and pr_number is not None:
                    logging.info(
                        "[PR_GATE_TRIGGERED] repo=%s pr=%s action=%s",
                        repo,
                        pr_number,
                        action,
                    )

                    author = "unknown_author"

                    def _login(v):
                        if isinstance(v, dict):
                            return (v.get("login") or "").strip() or None
                        if isinstance(v, str):
                            return v.strip() or None
                        return None

                    pr_obj = meta_json.get("pull_request") or (meta_json.get("event") or {}).get("pull_request")
                    logging.info("[PR_AUTHOR_DEBUG] pull_request=%s", pr_obj)
                    sender_obj = meta_json.get("sender") or (meta_json.get("event") or {}).get("sender")
                    user_obj = meta_json.get("user") or (meta_json.get("event") or {}).get("user")

                    # pull_request.user.login (preferred)
                    if isinstance(pr_obj, dict):
                        u = pr_obj.get("user")
                        author = _login(u) or author

                    # sender.login fallback
                    if author == "unknown_author":
                        author = _login(sender_obj) or author

                    # user.login fallback
                    if author == "unknown_author":
                        author = _login(user_obj) or author

                    allowlist_users = {"MJFLAIR"}

                    if author in allowlist_users:
                        logging.info("[PR_GATE_PASS] repo=%s pr=%s action=%s author=%s", repo, pr_number, action, author)
                        
                        from workflows.agents.llm_review_gate import run_llm_review
                        review = run_llm_review(str(task_id), meta_json)
                        logging.info(
                            "[PR_LLM_RESULT] decision=%s score=%s",
                            review.get("decision"),
                            review.get("score"),
                        )
                        
                        from workflows.actions.github_comment import try_post_pr_comment
                        try_post_pr_comment(str(task_id), meta_json, review)

                        from workflows.actions.github_label import try_apply_pr_labels
                        try_apply_pr_labels(str(task_id), meta_json, review)

                        from workflows.actions.github_merge import try_merge_pr
                        try_merge_pr(str(task_id), meta_json, review)
                    else:
                        logging.info("[PR_GATE_BLOCK] repo=%s pr=%s action=%s author=%s", repo, pr_number, action, author)

        # 事件可以保留（可審計）
        DB.emit_event(task_id, "EXECUTION_STARTED", {"task_id": task_id})

        # 執行：建議讓 TaskManager.execute 回傳 result_summary / cost_json
        # 如果目前 execute 沒回傳，就先用 mock，至少先跑通閉環
        result = TaskManager().execute(task_id)

        # 若 TaskManager.execute 目前回傳 None，就先包成可存的結構
        if result is None:
            result_summary = {"message": "execution finished", "task_id": task_id}
            cost_json = {"model": "none", "input_tokens": 0, "output_tokens": 0, "estimated_usd": 0}
        else:
            # 若你之後讓 execute 回傳 dict（含 result/cost），就改用這裡接
            # 例如 result = {"result_summary": {...}, "cost_json": {...}}
            result_summary = result.get("result_summary", {"task_id": task_id})
            cost_json = result.get("cost_json", {"model": "unknown"})

        DB.emit_event(task_id, "EXECUTION_FINISHED", {"task_id": task_id})
        return result_summary, cost_json