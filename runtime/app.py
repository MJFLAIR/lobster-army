import os
import vertexai
import openai
from flask import Flask, jsonify, request
from runtime.cron_tick import handle_tick
from workflows.storage.db import DB
from workflows.models.task import Task
from datetime import datetime
from tools.github_webhook import GitHubWebhook
from google.cloud import firestore
from google.api_core.exceptions import AlreadyExists
import logging

# 🛡️ 引入我們的智商稅攔截網
from gateway.pr_filter import should_process_pr

# ✅ 1. 統一使用專屬 Logger，捨棄 root logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app() -> Flask:
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")

    # 1. Support Firestore multi-database
    DB._client = firestore.Client(
        project=project_id,
        database=os.environ.get("FIRESTORE_DB_NAME", "lobster-main")
    )

    # 2. Ensure Vertex AI uses IAM (no API key needed, defaults to application credentials)
    vertexai.init(
        project=project_id,
        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    )

    # 3. Ensure OpenAI key comes from env var OPENAI_API_KEY
    openai.api_key = os.environ.get("OPENAI_API_KEY")

    app = Flask(__name__)

    # 4. Add /health endpoint
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "gateway", "version": "1.0.9"}), 200

    @app.post("/cron/tick")
    def cron_tick():
        return handle_tick()

    @app.post("/tasks")
    def create_task():
        try:
            data = request.get_json(silent=True)

            if not data:
                return jsonify({"ok": False, "error": "Missing JSON body"}), 400

            source = data.get("source")
            requester_id = data.get("requester_id")
            description = data.get("description")

            if not source or not requester_id or not description:
                return jsonify({
                    "ok": False,
                    "error": "source, requester_id, description required"
                }), 400

            task_id = int(datetime.utcnow().timestamp() * 1000)

            task = Task(
                task_id=task_id,
                source=source,
                requester_id=requester_id,
                description=description
            )

            DB.create_task(task)

            return jsonify({
                "ok": True,
                "task_id": task_id
            }), 200

        except Exception as e:
            logger.error(f"Error creating task: {e}")
            return jsonify({
                "ok": False,
                "error": str(e)
            }), 500

    @app.post("/api/webhook/github")
    def github_webhook():
        try:
            # 1. Verify Signature
            raw_body = request.get_data()
            signature_header = request.headers.get("X-Hub-Signature-256", "")
            
            if not GitHubWebhook.verify_signature(raw_body, signature_header):
                logger.warning("GitHub Webhook signature verification failed.")
                return jsonify({"ok": False, "error": "bad_signature"}), 401

            # 2. Check Event Type & Log Delivery ID
            event_type = request.headers.get("X-GitHub-Event", "")
            logger.info(
                "[GITHUB_WEBHOOK] event=%s delivery=%s",
                event_type,
                request.headers.get("X-GitHub-Delivery", "unknown")
            )
            
            if event_type != "pull_request":
                return jsonify({"ok": True, "ignored": True}), 200

            # 3. Parse JSON & Check Action
            data = request.get_json(silent=True)
            if not data:
                return jsonify({"ok": False, "error": "Missing JSON body"}), 400

            action = data.get("action", "")

            # 🛡️ 啟動智商稅攔截網 (PR Filter)
            if not should_process_pr(data, action):
                return jsonify({"ok": True, "ignored": True, "reason": "filtered_by_pr_filter"}), 200

            # Extract necessary payload details
            pr_data = data.get("pull_request", {})
            repo_data = data.get("repository", {})
            sender_data = data.get("sender", {})
            head_data = pr_data.get("head", {})
            base_data = pr_data.get("base", {})

            pr_number = pr_data.get("number")
            pr_title = pr_data.get("title", "Untitled PR")
            pr_html_url = pr_data.get("html_url", "")
            
            repo_full_name = repo_data.get("full_name", "unknown/repo")
            sender_login = sender_data.get("login", "unknown_user")
            
            head_sha = head_data.get("sha", "")
            head_ref = head_data.get("ref", "")
            base_ref = base_data.get("ref", "")

            # ✅ 2. 保護 head_sha：確保 dedup_key 絕對安全
            if not head_sha:
                logger.error("[GITHUB_WEBHOOK] Missing head_sha in payload. Aborting task creation.")
                return jsonify({"ok": False, "error": "missing head sha"}), 400

            # Default PR info description
            description = f"Review PR #{pr_number}: {pr_title}"

            # Prepare subset of payload for task
            payload_subset = {
                "repository": {"full_name": repo_full_name},
                "pull_request": {
                    "number": pr_number,
                    "title": pr_title,
                    "html_url": pr_html_url,
                    "head": {"sha": head_sha, "ref": head_ref},
                    "base": {"ref": base_ref}
                },
                "sender": {"login": sender_login},
                "action": action
            }

            task_id = int(datetime.utcnow().timestamp() * 1000)

            # Idempotency check using atomic create-only
            dedup_key = f"{repo_full_name}:{pr_number}:{head_sha}".replace("/", "_")
            dedup_ref = DB.get_client().collection("pr_dedup").document(dedup_key)
            
            try:
                dedup_ref.create({
                    "task_id": task_id,
                    "repo": repo_full_name,
                    "pr_number": pr_number,
                    "head_sha": head_sha,
                    "pr_html_url": pr_html_url,
                    "sender_login": sender_login,
                    "created_at": firestore.SERVER_TIMESTAMP
                })
            except AlreadyExists:
                logger.info(f"[GITHUB_WEBHOOK] Duplicate webhook received for dedup_key={dedup_key}")
                return jsonify({"ok": True, "ignored": True, "reason": "duplicate"}), 200

            # Store payload_subset in meta_json, and set plan_json to None
            task = Task(
                task_id=task_id,
                source="github_pr",
                requester_id=sender_login,
                description=description,
                meta_json=payload_subset,
                plan_json=None
            )

            DB.create_task(task)
            
            logger.info(f"[GITHUB_WEBHOOK] Successfully created task_id={task_id} for PR #{pr_number}")

            return jsonify({
                "ok": True,
                "task_id": task_id,
                "pr": pr_number
            }), 200

        except Exception as e:
            logger.error(f"Error processing GitHub Webhook: {e}")
            return jsonify({
                "ok": False,
                "error": str(e)
            }), 500

    return app

app = create_app()